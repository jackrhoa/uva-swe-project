import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MessageForm, StartConversationForm, TeamMessageForm
from .models import (
    Conversation,
    ConversationRead,
    Message,
    TeamConversation,
    TeamMessage,
)


def get_allowed_users(current_user):
    current_profile = current_user.profile

    if current_profile.is_exec():
        return User.objects.exclude(pk=current_user.pk).exclude(profile__role='admin').select_related('profile')

    return User.objects.filter(
        profile__team=current_profile.team
    ).exclude(pk=current_user.pk).exclude(profile__role='admin').select_related('profile')


def _display_name(user):
    if not user:
        return 'Deleted User'
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.email or user.username


def _avatar_letters(user):
    if not user:
        return '?'
    first = (user.first_name or '')[:1]
    last = (user.last_name or '')[:1]
    letters = (first + last).upper()
    if letters:
        return letters
    fallback = (user.username or user.email or '?')[:1].upper()
    return fallback


def _avatar_url(user):
    if not user:
        return ''
    try:
        if user.profile.avatar:
            return user.profile.avatar.url
    except Exception:
        return ''
    return ''


@login_required
def message_list(request):
    if request.user.profile.is_admin():
        return redirect('admin_dashboard')
    conversation_qs = Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).select_related('user1', 'user2').prefetch_related('messages').order_by('-updated_at')

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

        last_msg = active_conversation.messages.order_by('-id').first()
        if last_msg:
            ConversationRead.objects.update_or_create(
                user=request.user,
                conversation=active_conversation,
                defaults={'last_read_message_id': last_msg.id},
            )

    read_map = {
        cr.conversation_id: cr.last_read_message_id
        for cr in ConversationRead.objects.filter(user=request.user)
    }

    conversations = []
    for conversation in conversation_qs:
        other_user = conversation.user2 if conversation.user1 == request.user else conversation.user1
        last_message = conversation.messages.order_by('-created_at').first()
        last_read_id = read_map.get(conversation.id, 0)
        has_unread = (
            last_message is not None
            and not last_message.is_deleted
            and last_message.sender_id != request.user.id
            and last_message.id > last_read_id
        )
        conversations.append({
            'conversation': conversation,
            'other_user': other_user,
            'last_message': last_message,
            'has_unread': has_unread,
        })

    allowed_users = get_allowed_users(request.user)
    start_form = StartConversationForm(allowed_users=allowed_users)

    is_exec = request.user.profile.is_exec()
    recipient_options_json = json.dumps([
        {
            'value': str(u.pk),
            'name': f"{u.first_name} {u.last_name}".strip() or u.email,
            'email': u.email,
            'team': u.profile.team.name if is_exec and u.profile.team else '',
        }
        for u in allowed_users
    ])

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

            recipient = (
                conversation.user2
                if conversation.user1 == request.user
                else conversation.user1
            )
            if recipient:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"user_{recipient.id}",
                    {
                        "type": "chat.message",
                        "message": {
                            "id": message.id,
                            "content": message.content,
                            "attachment_url": message.attachment.url if message.attachment else '',
                            "attachment_name": message.attachment.name.split('/')[-1] if message.attachment else '',
                            "created_at_iso": message.created_at.isoformat(),
                            "conversation_id": conversation.id,
                            "sender_id": request.user.id,
                            "sender_name": _display_name(request.user),
                            "sender_initials": _avatar_letters(request.user),
                            "sender_avatar_url": _avatar_url(request.user),
                            "sender_email": request.user.email,
                        },
                    }
                )

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


@login_required
def delete_message(request, message_id):
    message = get_object_or_404(Message, id=message_id, sender=request.user)

    if request.method == 'POST':
        conversation_id = message.conversation_id
        message.is_deleted = True
        message.content = ''
        message.attachment = None
        message.save()

        conversation = message.conversation
        recipient = (
            conversation.user2
            if conversation.user1 == request.user
            else conversation.user1
        )
        if recipient:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{recipient.id}",
                {
                    "type": "message.deleted",
                    "message_id": message.id,
                    "conversation_id": conversation_id,
                }
            )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect(f'/messages/?conversation={conversation_id}')

    return JsonResponse({'ok': False}, status=405)


@login_required
def mark_read(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    conversation = get_object_or_404(
        Conversation.objects.filter(
            Q(user1=request.user) | Q(user2=request.user)
        ),
        id=conversation_id
    )
    last_msg = conversation.messages.order_by('-id').first()
    if last_msg:
        ConversationRead.objects.update_or_create(
            user=request.user,
            conversation=conversation,
            defaults={'last_read_message_id': last_msg.id},
        )
    return JsonResponse({'ok': True})


@login_required
def team_chat(request):
    profile = request.user.profile

    if profile.is_admin():
        return redirect('admin_dashboard')

    if not profile.team:
        messages.error(request, 'You are not assigned to a team.')
        return redirect('home')

    team_conversation, created = TeamConversation.objects.get_or_create(team=profile.team)
    team_messages = team_conversation.messages.select_related('sender').order_by('created_at')
    form = TeamMessageForm()

    context = {
        'team': profile.team,
        'team_conversation': team_conversation,
        'team_messages': team_messages,
        'message_form': form,
    }
    return render(request, 'team_chat.html', context)


@login_required
def delete_team_message(request, message_id):
    message = get_object_or_404(TeamMessage, id=message_id, sender=request.user)

    if request.method == 'POST':
        team_conversation = message.team_conversation
        message.is_deleted = True
        message.content = ''
        message.attachment = None
        message.save()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"team_{team_conversation.team_id}",
            {
                "type": "team.message.deleted",
                "message_id": message.id,
            }
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect('team_chat')

    return JsonResponse({'ok': False}, status=405)


@login_required
def send_team_message(request, team_conversation_id):
    profile = request.user.profile

    team_conversation = get_object_or_404(
        TeamConversation,
        id=team_conversation_id,
        team=profile.team
    )

    if request.method == 'POST':
        form = TeamMessageForm(request.POST, request.FILES)
        if form.is_valid():
            message = form.save(commit=False)
            message.team_conversation = team_conversation
            message.sender = request.user
            message.save()
            team_conversation.save()

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"team_{team_conversation.team_id}",
                {
                    "type": "team.message",
                    "message": {
                        "id": message.id,
                        "content": message.content,
                        "attachment_url": message.attachment.url if message.attachment else '',
                        "attachment_name": message.attachment.name.split('/')[-1] if message.attachment else '',
                        "created_at_iso": message.created_at.isoformat(),
                        "sender_id": request.user.id,
                        "sender_name": _display_name(request.user),
                        "sender_initials": _avatar_letters(request.user),
                        "sender_avatar_url": _avatar_url(request.user),
                    },
                }
            )

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
                        'sender_name': _display_name(request.user),
                        'sender_initials': _avatar_letters(request.user),
                        'sender_avatar_url': _avatar_url(request.user),
                    }
                })

            return redirect('team_chat')

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'ok': False,
                'error': form.errors.as_json()
            }, status=400)

    messages.error(request, 'Could not send team message.')
    return redirect('team_chat')