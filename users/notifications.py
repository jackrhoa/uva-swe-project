from django.core.mail import send_mail
from django.conf import settings
 
 
# ── helpers ──────────────────────────────────────────────────────────────────
 
def _site_name():
    return getattr(settings, 'SITE_NAME', 'CIO Manager')
 
 
def _email_enabled():
    return bool(getattr(settings, 'EMAIL_HOST_USER', ''))


def _from_addr():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
 
 
# ── 1. New announcement ───────────────────────────────────────────────────────
 
def notify_announcement(announcement):
    """
    Call this right after an Announcement is saved.
    Emails every user who can see the announcement.

    Usage in views.py (exec_dashboard POST):
        ann = Announcement.objects.create(...)
        ann.target_teams.set(...)
        from .notifications import notify_announcement
        notify_announcement(ann)
    """
    if not _email_enabled():
        return
    from django.contrib.auth.models import User
    from django.db.models import Q
 
    if announcement.target == 'all':
        recipients = User.objects.filter(is_active=True).exclude(email='')
    else:
        # Only users whose team is in target_teams
        recipients = User.objects.filter(
            is_active=True,
            profile__team__in=announcement.target_teams.all(),
        ).exclude(email='').distinct()
 
    sender_name = (
        announcement.sent_by.get_full_name()
        or announcement.sent_by.username
        if announcement.sent_by
        else _site_name()
    )
 
    subject = f"[{_site_name()}] New announcement from {sender_name}"
    body_preview = (
        announcement.body[:300] + '…'
        if len(announcement.body) > 300
        else announcement.body
    )
    message = (
        f"Hi,\n\n"
        f"There's a new announcement for you from {sender_name}:\n\n"
        f"---\n{body_preview}\n---\n\n"
        f"Log in to {_site_name()} to see the full announcement.\n"
    )
 
    for user in recipients:
        # Don't email the person who sent it
        if announcement.sent_by and user == announcement.sent_by:
            continue
        send_mail(
            subject=subject,
            message=message,
            from_email=_from_addr(),
            recipient_list=[user.email],
            fail_silently=True,
        )
 
 
# ── 2. Task completed ─────────────────────────────────────────────────────────
 
def notify_task_completed(task):
    if not _email_enabled():
        return
    from django.contrib.auth.models import User
 
    # Build recipient list: support both a single assigned_to user
    # and a many-to-many assigned_to (adapt field name as needed).
    recipients = []
 
    # Case A: task.assigned_to is a single User FK (nullable)
    if hasattr(task, 'assigned_to') and task.assigned_to is not None:
        if hasattr(task.assigned_to, 'email') and task.assigned_to.email:
            recipients.append(task.assigned_to)
 
    # Case B: task.assigned_users is a M2M of User
    if hasattr(task, 'assigned_users'):
        for u in task.assigned_users.filter(is_active=True).exclude(email=''):
            if u not in recipients:
                recipients.append(u)
 
    subject = f"[{_site_name()}] Task completed: {task.name}"
    message = (
        f"Hi,\n\n"
        f"The task \"{task.name}\" has been marked as completed"
        + (f" in team {task.team.name}" if hasattr(task, 'team') and task.team else "")
        + ".\n\n"
        f"Log in to {_site_name()} to review it.\n"
    )
 
    for user in recipients:
        send_mail(
            subject=subject,
            message=message,
            from_email=_from_addr(),
            recipient_list=[user.email],
            fail_silently=True,
        )
 
 
# ── 3. Direct message FROM an exec ───────────────────────────────────────────
 
def notify_exec_direct_message(sender, recipient, message_body):
    if not _email_enabled():
        return
    # Guard: only email when the sender is an exec
    try:
        if not sender.profile.is_exec():
            return
    except AttributeError:
        return  # No profile → not an exec, skip
 
    if not recipient or not recipient.email:
        return
 
    sender_name = sender.get_full_name() or sender.username
    subject = f"[{_site_name()}] Message from {sender_name} (exec)"
    preview = (
        message_body[:300] + '…'
        if len(message_body) > 300
        else message_body
    )
    message = (
        f"Hi {recipient.get_full_name() or recipient.username},\n\n"
        f"{sender_name} (exec) sent you a message:\n\n"
        f"---\n{preview}\n---\n\n"
        f"Log in to {_site_name()} to reply.\n"
    )
 
    send_mail(
        subject=subject,
        message=message,
        from_email=_from_addr(),
        recipient_list=[recipient.email],
        fail_silently=True,
    )