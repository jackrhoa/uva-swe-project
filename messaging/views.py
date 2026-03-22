import json
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.db.models import Q
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MessageForm, StartConversationForm
from .models import Conversation


def get_allowed_users(current_user):
    current_profile = current_user.profile

    if current_profile.is_exec():
        return User.objects.exclude(pk=current_user.pk).select_related('profile')

    return User.objects.filter(
        profile__team=current_profile.team
    ).exclude(pk=current_user.pk).select_related('profile')


@login_required
def message_list(request):
    conversation_qs = Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).select_related('user1', 'user2').prefetch_related('messages').order_by('-updated_at')

    conversations = []
    for conversation in conversation_qs:
        other_user = conversation.user2 if conversation.user1 == request.user else conversation.user1
        conversations.append({
            'conversation': conversation,
            'other_user': other_user,
        })

    allowed_users = get_allowed_users(request.user)
    start_form = StartConversationForm(allowed_users=allowed_users)

    is_exec = request.user.profile.is_exec()
    recipient_options_json = json.dumps([
        {
            'value': str(u.pk),
            'name': f"{u.first_name} {u.last_name}".strip() or u.email,
            'email': u.email,
            'team': u.profile.team.name if is_exec else '',
        }
        for u in allowed_users
    ])

    active_conversation = None
    active_other_user = None
    message_form = MessageForm()

    conversation_id = request.GET.get('conversation')
    if conversation_id:
        active_conversation = get_object_or_404(
            conversation_qs,
            id=conversation_id
        )
        active_other_user = (
            active_conversation.user2
            if active_conversation.user1 == request.user
            else active_conversation.user1
        )

    context = {
        'conversations': conversations,
        'active_conversation': active_conversation,
        'active_other_user': active_other_user,
        'start_form': start_form,
        'message_form': message_form,
        'is_exec': is_exec,
        'recipient_options_json': recipient_options_json,
    }
    return render(request, 'messages.html', context)


@login_required
def start_conversation(request):
    allowed_users = get_allowed_users(request.user)

    if request.method == 'POST':
        form = StartConversationForm(request.POST, allowed_users=allowed_users)
        if form.is_valid():
            recipient = form.cleaned_data['recipient']
            conversation = Conversation.get_or_create_conversation(request.user, recipient)
            return redirect(f'/messages/?conversation={conversation.id}')

    messages.error(request, 'Could not start conversation.')
    return redirect('message_list')


@login_required
def send_message(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.filter(
            Q(user1=request.user) | Q(user2=request.user)
        ),
        id=conversation_id
    )

    if request.method == 'POST':
        form = MessageForm(request.POST, request.FILES)
        if form.is_valid():
            message = form.save(commit=False)
            message.conversation = conversation
            message.sender = request.user
            message.save()
            conversation.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'ok': True,
                    'message': {
                        'id': message.id,
                        'content': message.content,
                        'attachment_url': message.attachment.url if message.attachment else '',
                        'attachment_name': message.attachment.name.split('/')[-1] if message.attachment else '',
                        'created_at_iso': message.created_at.isoformat(),
                        'is_self': True,
                    }
                })

            return redirect(f'/messages/?conversation={conversation.id}')

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'ok': False,
                'error': form.errors.as_json()
            }, status=400)

    messages.error(request, 'Could not send message.')
    return redirect(f'/messages/?conversation={conversation.id}')


def message_stream(request, conversation_id):
    if not request.user.is_authenticated:
        return StreamingHttpResponse(status=401)

    conversation = get_object_or_404(
        Conversation.objects.filter(
            Q(user1=request.user) | Q(user2=request.user)
        ),
        id=conversation_id
    )
    since_id = int(request.GET.get('since_id', 0))

    def event_stream():
        from django.utils import timezone
        last_id = since_id
        last_check = timezone.now()
        while True:
            close_old_connections()
            now = timezone.now()

            new_messages = (
                conversation.messages
                .filter(id__gt=last_id, is_deleted=False)
                .exclude(sender=request.user)
                .select_related('sender')
            )
            for msg in new_messages:
                payload = json.dumps({
                    'id': msg.id,
                    'content': msg.content,
                    'attachment_url': msg.attachment.url if msg.attachment else '',
                    'attachment_name': msg.attachment.name.split('/')[-1] if msg.attachment else '',
                    'created_at_iso': msg.created_at.isoformat(),
                    'is_self': False,
                })
                yield f'data: {payload}\n\n'
                last_id = msg.id

            deleted_messages = conversation.messages.filter(
                updated_at__gt=last_check,
                is_deleted=True,
            )
            for msg in deleted_messages:
                payload = json.dumps({'id': msg.id})
                yield f'event: deleted\ndata: {payload}\n\n'

            last_check = now
            time.sleep(1)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
def delete_message(request, message_id):
    from .models import Message
    message = get_object_or_404(Message, id=message_id, sender=request.user)

    if request.method == 'POST':
        conversation_id = message.conversation_id
        message.is_deleted = True
        message.content = ''
        message.attachment = None
        message.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect(f'/messages/?conversation={conversation_id}')

    return JsonResponse({'ok': False}, status=405)
