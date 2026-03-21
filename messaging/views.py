from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MessageForm, StartConversationForm
from .models import Conversation


def get_allowed_users(current_user):
    current_profile = current_user.profile

    if current_profile.is_exec():
        return User.objects.select_related('profile').all()

    return User.objects.filter(
        profile__team=current_profile.team
    ).select_related('profile')


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
                        'content': message.content,
                        'attachment_url': message.attachment.url if message.attachment else '',
                        'attachment_name': message.attachment.name.split('/')[-1] if message.attachment else '',
                        'created_at_label': message.created_at.strftime('%b %d, %Y %-I:%M %p'),
                        'created_at_minute': message.created_at.strftime('%Y-%m-%d %H:%M'),
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
