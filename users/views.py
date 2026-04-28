import os
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db import IntegrityError, models
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.management import call_command
from .models import (
    Team, UserProfile, Task, Announcement, AnnouncementRead,
    get_announcement_for_user, get_announcements_for_user,
    AttendanceSession, AttendanceAttempt, _generate_code,
)
from .forms import ProfileNameForm
import json


@login_required
def home(request):
    profile = request.user.profile
    if profile.is_admin():
        return redirect('admin_dashboard')
    if profile.is_exec():
        return redirect('exec_dashboard')
    return redirect('member_dashboard')


@login_required
def admin_dashboard(request):
    if not request.user.profile.is_admin():
        return redirect('home')
    return render(request, 'admin_dashboard.html')

@login_required
def exec_dashboard(request):
    if not request.user.profile.is_exec():
        return redirect('member_dashboard')

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        team_ids = request.POST.getlist('target_teams')

        if body:
            if '__all__' in team_ids:
                ann = Announcement.objects.create(
                    body=body,
                    sent_by=request.user,
                    target=Announcement.TARGET_ALL,
                )
                from .notifications import notify_announcement
                notify_announcement(ann)
            else:
                ann = Announcement.objects.create(
                    body=body,
                    sent_by=request.user,
                    target=Announcement.TARGET_SPECIFIC,
                )
                valid_ids = [tid for tid in team_ids if tid.isdigit()]
                ann.target_teams.set(Team.objects.filter(id__in=valid_ids))
                from .notifications import notify_announcement
                notify_announcement(ann)

        return redirect('exec_dashboard')

    all_teams = Team.objects.all().order_by('name')
    active_session = AttendanceSession.get_active()
    unread_announcements = get_announcements_for_user(request.user).exclude(
        reads__user=request.user
    )

    return render(request, 'exec_dashboard.html', {
        'profile': request.user.profile,
        'unread_announcements': unread_announcements,
        'all_teams': all_teams,
        'active_session': active_session,
    })

@login_required
def member_dashboard(request):
    if request.user.profile.is_exec():
        return redirect('exec_dashboard')

    unread_announcements = get_announcements_for_user(request.user).exclude(
        reads__user=request.user
    )
    active_session = AttendanceSession.get_active()

    member_checked_off = False
    if active_session:
        member_checked_off = active_session.attempts.filter(
            user=request.user, success=True
        ).exists()

    return render(request, 'member_dashboard.html', {
        'profile': request.user.profile,
        'unread_announcements': unread_announcements,
        'active_session': active_session,
        'member_checked_off': member_checked_off,
    })

@login_required
def send_team_announcement(request, team_id):
    """Exec only: create an announcement targeted at a specific team."""
    if not request.user.profile.is_exec():
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'ok': False, 'error': 'Empty body'}, status=400)
    team = get_object_or_404(Team, id=team_id)
    ann = Announcement.objects.create(
        body=body,
        sent_by=request.user,
        target=Announcement.TARGET_SPECIFIC,
    )
    ann.target_teams.set([team])
    sender_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
    return JsonResponse({
        'ok': True,
        'announcement': {
            'id': ann.id,
            'body': ann.body,
            'sent_at_iso': ann.sent_at.isoformat(),
            'sender_name': sender_name,
            'team_name': team.name,
        },
    })


@login_required
def mark_announcement_read(request, announcement_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    announcement = get_object_or_404(Announcement, id=announcement_id)
    AnnouncementRead.objects.get_or_create(user=request.user, announcement=announcement)
    return JsonResponse({'ok': True})


@login_required
def mark_all_announcements_read(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    if request.user.profile.is_exec():
        announcements = Announcement.objects.all()
    else:
        announcements = get_announcements_for_user(request.user)
    already_read = set(
        AnnouncementRead.objects.filter(user=request.user)
        .values_list('announcement_id', flat=True)
    )
    new_reads = [
        AnnouncementRead(user=request.user, announcement=ann)
        for ann in announcements
        if ann.id not in already_read
    ]
    AnnouncementRead.objects.bulk_create(new_reads, ignore_conflicts=True)
    return JsonResponse({'ok': True})


@login_required
def unmark_announcement_read(request, announcement_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    AnnouncementRead.objects.filter(user=request.user, announcement_id=announcement_id).delete()
    return JsonResponse({'ok': True})


@login_required
def announcement_history(request):
    if request.user.profile.is_exec():
        announcements = Announcement.objects.all().order_by('-sent_at')
    else:
        announcements = get_announcements_for_user(request.user)
    read_ann_ids = set(
        AnnouncementRead.objects.filter(user=request.user).values_list('announcement_id', flat=True)
    )
    return render(request, 'announcement_history.html', {
        'announcements': announcements,
        'read_ann_ids': read_ann_ids,
    })

@login_required
def profile(request):
    prof = request.user.profile
    if prof.is_admin():
        return redirect('admin_dashboard')
    return render(request, 'profile.html', {
        'profile': prof,
        'picture': prof.avatar.url if prof.avatar else '',
    })

@login_required
def manage_roles(request):
    if not request.user.profile.is_admin():
        return redirect('home')
    users = UserProfile.objects.select_related('user', 'team').exclude(user__is_superuser=True)
    return render(request, 'manage_roles.html', {'users': users})

@login_required
def change_role(request, user_id):
    if not request.user.profile.is_admin():
        return redirect('home')

    if request.method == 'POST':
        if request.user.id == user_id:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'ok': False})
            return redirect('manage_roles')

        profile = get_object_or_404(UserProfile, user__id=user_id)
        new_role = request.POST.get('role')

        if new_role in ['exec', 'member']:
            profile.role = new_role
            profile.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'ok': True, 'role': new_role})

    return redirect('manage_roles')


@login_required
def manage_teams(request):
    if not request.user.profile.is_exec():
        return redirect('home')
    teams = Team.objects.all()
    users = UserProfile.objects.select_related('user').exclude(role='admin').exclude(user__is_superuser=True)
    return render(request, 'manage_teams.html', {'users': users, 'teams': teams})

@login_required
def change_team(request, user_id):
    if not request.user.profile.is_exec():
        return redirect('home')
    if request.method == 'POST':
        profile = get_object_or_404(UserProfile, user__id=user_id)
        new_team_id = request.POST.get('team')
        if new_team_id:
            new_team = get_object_or_404(Team, id=new_team_id)
            profile.team = new_team
            profile.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'ok': True, 'team': new_team.name})
    return redirect('manage_teams')

@login_required
def add_team(request):
    if not request.user.profile.is_exec():
        return redirect('home')
    if request.method == 'POST':
        team_name = request.POST.get('team_name')
        if team_name:
            Team.objects.get_or_create(name=team_name)
    return redirect('manage_teams')

@login_required
def delete_team(request, team_id):
    if not request.user.profile.is_exec():
        return redirect('home')
    team = get_object_or_404(Team, id=team_id)
    team.delete()
    return redirect('manage_teams')

@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = ProfileNameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
        prof = request.user.profile
        if request.POST.get('remove_avatar'):
            prof.avatar.delete(save=True)
        else:
            avatar_file = request.FILES.get('avatar')
            if avatar_file:
                import os
                allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                ext = os.path.splitext(avatar_file.name)[1].lower()
                if ext not in allowed_extensions:
                    from django.contrib import messages
                    messages.error(request, f'Unsupported file type "{ext}". Please upload a JPEG, PNG, GIF, or WEBP image.')
                    return render(request, 'edit_profile.html', {
                        'form': ProfileNameForm(request.POST, instance=request.user),
                        'profile': prof,
                    })
                prof.avatar = avatar_file
                prof.save()
        return redirect('profile')
    else:
        form = ProfileNameForm(instance=request.user)

    return render(request, 'edit_profile.html', {
        'form': form,
        'profile': request.user.profile,
    })

@login_required
def exec_edit_user(request, user_id):
    if not request.user.profile.is_exec():
        return redirect('home')

    target_profile = get_object_or_404(UserProfile, user__id=user_id)
    if target_profile.is_admin():
        return redirect('manage_teams')

    if request.method == 'POST':
        form = ProfileNameForm(request.POST, instance=target_profile.user)
        if form.is_valid():
            form.save()
        if request.POST.get('remove_avatar'):
            target_profile.avatar.delete(save=True)
        else:
            avatar_file = request.FILES.get('avatar')
            if avatar_file:
                import os
                allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                ext = os.path.splitext(avatar_file.name)[1].lower()
                if ext not in allowed_extensions:
                    from django.contrib import messages
                    messages.error(request, f'Unsupported file type "{ext}". Please upload a JPEG, PNG, GIF, or WEBP image.')
                    return render(request, 'exec_edit_user.html', {
                        'form': ProfileNameForm(request.POST, instance=target_profile.user),
                        'target_profile': target_profile,
                    })
                target_profile.avatar = avatar_file
                target_profile.save()
        return redirect('manage_teams')

    form = ProfileNameForm(instance=target_profile.user)
    return render(request, 'exec_edit_user.html', {
        'form': form,
        'target_profile': target_profile,
    })


@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        logout(request)
        user.delete()
        return redirect('account_login')
    return redirect('profile')

@login_required
def tasks(request):
    if request.user.profile.is_admin():
        return redirect('admin_dashboard')
    team = request.user.profile.team
    from django.db.models import Q

    all_tasks = Task.objects.filter(team=team)

    if request.user.profile.is_exec():
        visible = all_tasks
    else:
        visible = all_tasks.filter(
            Q(whole_team=True) | Q(active_users=request.user)
        ).distinct()

    uncompleted_tasks = (
        visible
        .filter(actions_completed__lt=models.F('total_actions'))
        .order_by('-priority', 'name')
    )
    completed_tasks = (
        visible
        .filter(actions_completed__gte=models.F('total_actions'))
        .order_by('-priority', 'name')
    )

    team_members = User.objects.filter(profile__team=team).exclude(profile__role='admin').exclude(is_superuser=True)
    now = timezone.now()

    return render(request, 'tasks.html', {
        'uncompleted_tasks': uncompleted_tasks,
        'completed_tasks':   completed_tasks,
        'is_exec':           request.user.profile.is_exec(),
        'team_members':      team_members,
        'team_name':         team.name,
        'now':               now,
    })


@login_required
def add_task(request):
    if not request.user.profile.is_exec():
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    data = json.loads(request.body)
    task = Task.objects.create(
        name=data.get('name', 'New Task') or 'New Task',
        description=data.get('description', ''),
        team=request.user.profile.team,
        total_actions=max(1, int(data.get('total_actions', 1))),
        actions_completed=0,
        priority=int(data.get('priority', 1)),
    )

    deadline_raw = data.get('deadline', None)
    if deadline_raw:
        from django.utils.dateparse import parse_datetime
        parsed = parse_datetime(deadline_raw)
        if parsed:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            task.deadline = parsed

    whole_team = data.get('whole_team', False)
    task.whole_team = whole_team
    if whole_team:
        task.active_users.clear()
    elif 'active_users' in data:
        ids = [int(i) for i in data['active_users'] if i]
        task.active_users.set(User.objects.filter(id__in=ids, profile__team=task.team))

    task.save()
    return JsonResponse({'ok': True})


@login_required
def remove_task(request, task_id):
    if not request.user.profile.is_exec():
        return redirect('tasks')

    task = get_object_or_404(Task, id=task_id, team=request.user.profile.team)
    task.delete()
    return redirect('tasks')


@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, team=request.user.profile.team)

    if request.method == 'POST':
        data = json.loads(request.body)

        if request.user.profile.is_exec():
            task.name          = data.get('name', task.name)
            task.description   = data.get('description', task.description)
            task.total_actions = int(data.get('total_actions', task.total_actions))
            task.priority      = int(data.get('priority', task.priority))

            deadline_raw = data.get('deadline', None)
            if deadline_raw == '' or deadline_raw is None:
                if 'deadline' in data:
                    task.deadline = None
            else:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(deadline_raw)
                if parsed:
                    if timezone.is_naive(parsed):
                        parsed = timezone.make_aware(parsed)
                    task.deadline = parsed

            whole_team = data.get('whole_team', False)
            task.whole_team = whole_team

            if whole_team:
                task.active_users.clear()
            elif 'active_users' in data:
                ids = [int(i) for i in data['active_users'] if i]
                task.active_users.set(User.objects.filter(id__in=ids, profile__team=task.team))

        if 'actions_completed' in data:
            task.actions_completed = max(0, min(int(data['actions_completed']), task.total_actions))

        task.save()

        if task.actions_completed >= task.total_actions:
            from .notifications import notify_task_completed
            notify_task_completed(task)

        return JsonResponse({
            'name':              task.name,
            'description':       task.description,
            'priority':          task.priority,
            'actions_completed': task.actions_completed,
            'total_actions':     task.total_actions,
            'whole_team':        task.whole_team,
            'deadline':          task.deadline.isoformat() if task.deadline else None,
            'active_users': [
                {
                    'id':        u.id,
                    'name':      u.get_full_name() or u.username,
                    'initial':   ((u.first_name[:1] or u.username[:1]) + u.last_name[:1]).upper(),
                    'avatar_url': u.profile.avatar.url if hasattr(u, 'profile') and u.profile.avatar else '',
                }
                for u in task.active_users.all()
            ],
        })

    return JsonResponse({'error': 'Invalid method'}, status=400)


# ── Attendance views ──────────────────────────────────────────────────────────

@login_required
def attendance_generate(request):
    """Exec only: generate a new code and make the session live."""
    if not request.user.profile.is_exec():
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    AttendanceSession.objects.filter(is_active=True).update(
        is_active=False, ended_at=timezone.now()
    )

    code = _generate_code()
    session = AttendanceSession.objects.create(
        code=code,
        is_active=True,
        started_at=timezone.now(),
        created_by=request.user,
    )
    async_to_sync(get_channel_layer().group_send)("attendance", {
        "type": "attendance.session.started",
    })
    return JsonResponse({'ok': True, 'code': code, 'session_id': session.id})


@login_required
def attendance_end(request):
    """Exec only: end the active attendance session."""
    if not request.user.profile.is_exec():
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    AttendanceSession.objects.filter(is_active=True).update(
        is_active=False, ended_at=timezone.now()
    )
    async_to_sync(get_channel_layer().group_send)("attendance", {
        "type": "attendance.session.ended",
    })
    return JsonResponse({'ok': True})


@login_required
def attendance_submit(request):
    """Member: submit an attendance code."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    data = json.loads(request.body)
    code_entered = data.get('code', '').strip().upper()

    if not request.user.email:
        return JsonResponse({'ok': False, 'result': 'error', 'message': 'Your account has no email address. Please sign in with Google to submit attendance.'}, status=403)

    active_session = AttendanceSession.get_active()
    if not active_session:
        return JsonResponse({'ok': True, 'result': 'inactive'})

    success = (code_entered == active_session.code)
    AttendanceAttempt.objects.create(
        session=active_session,
        user=request.user,
        code_entered=code_entered,
        success=success,
    )
    if success:
        user = request.user
        async_to_sync(get_channel_layer().group_send)("attendance", {
            "type": "attendance.member.checked.in",
            "member": {
                "id": user.id,
                "name": user.get_full_name() or user.email,
                "initial": (user.first_name or user.email)[0].upper(),
                "team": user.profile.team.name,
                "checked_in": True,
            },
        })
    return JsonResponse({'ok': True, 'result': 'success' if success else 'fail'})


@login_required
def attendance_status(request):
    active_session = AttendanceSession.get_active()
    if not active_session:
        return JsonResponse({'is_active': False})

    checked_off = active_session.attempts.filter(
        user=request.user, success=True
    ).exists()

    return JsonResponse({
        'is_active': True,
        'code': active_session.code if request.user.profile.is_exec() else None,
        'checked_off': checked_off,
    })


@login_required
def attendance_records(request):
    """Exec only: return attendance attempt records as JSON for the records table."""
    if not request.user.profile.is_exec():
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)

    team_filter = request.GET.get('team', '')
    result_filter = request.GET.get('result', 'all')

    qs = AttendanceAttempt.objects.select_related(
        'user', 'user__profile', 'user__profile__team', 'session'
    ).order_by('-submitted_at')

    if team_filter and team_filter.isdigit():
        qs = qs.filter(user__profile__team__id=team_filter)

    if result_filter == 'success':
        qs = qs.filter(success=True)
    elif result_filter == 'fail':
        qs = qs.filter(success=False)

    rows = []
    for attempt in qs:
        u = attempt.user
        name = u.get_full_name() or u.username
        initial = ((u.first_name[:1] or u.username[:1]) + u.last_name[:1]).upper()
        team_name = u.profile.team.name if hasattr(u, 'profile') else '—'
        avatar_url = ''
        try:
            if u.profile.avatar:
                avatar_url = u.profile.avatar.url
        except Exception:
            pass
        rows.append({
            'initial': initial,
            'avatar_url': avatar_url,
            'name': name,
            'team': team_name,
            'submitted_at': attempt.submitted_at.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'code': attempt.code_entered,
            'result': 'success' if attempt.success else 'failed',
        })

    return JsonResponse({'ok': True, 'rows': rows})


@login_required
def attendance_records_page(request):
    """Exec only: render the dedicated attendance records page."""
    if not request.user.profile.is_exec():
        return redirect('home')

    all_teams = Team.objects.all().order_by('name')
    return render(request, 'attendance_records.html', {
        'profile': request.user.profile,
        'all_teams': all_teams,
        'selected_team': request.GET.get('team', ''),
        'selected_result': request.GET.get('result', 'all'),
    })


@login_required
def attendance_live(request):
    """Exec only: dedicated live attendance page showing the code and check-in list."""
    if not request.user.profile.is_exec():
        return redirect('home')
    active_session = AttendanceSession.get_active()
    return render(request, 'attendance_live.html', {
        'profile': request.user.profile,
        'active_session': active_session,
    })


@login_required
def attendance_members_status(request):
    """Exec only: JSON list of all members with their check-in status for the active session."""
    if not request.user.profile.is_exec():
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)

    active_session = AttendanceSession.get_active()
    if not active_session:
        return JsonResponse({'ok': True, 'is_active': False, 'members': []})

    checked_in_ids = set(
        active_session.attempts.filter(success=True).values_list('user_id', flat=True)
    )

    members = (
        User.objects.filter(profile__role='member')
        .select_related('profile', 'profile__team')
        .order_by('first_name', 'last_name', 'username')
    )

    rows = []
    for u in members:
        name = u.get_full_name() or u.username
        initial = ((u.first_name[:1] or u.username[:1]) + u.last_name[:1]).upper()
        team_name = u.profile.team.name if hasattr(u, 'profile') else '—'
        rows.append({
            'id': u.id,
            'name': name,
            'initial': initial,
            'team': team_name,
            'checked_in': u.id in checked_in_ids,
        })

    return JsonResponse({
        'ok': True,
        'is_active': True,
        'code': active_session.code,
        'session_id': active_session.id,
        'members': rows,
    })


@login_required
def attendance_records_csv(request):
    """Exec only: download filtered attendance records as a CSV file."""
    import csv
    from django.http import HttpResponse
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    if not request.user.profile.is_exec():
        return redirect('home')

    tz_name = request.GET.get('tz', 'UTC')
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo('America/New_York')

    team_filter = request.GET.get('team', '')
    result_filter = request.GET.get('result', 'all')

    qs = AttendanceAttempt.objects.select_related(
        'user', 'user__profile', 'user__profile__team', 'session'
    ).order_by('-submitted_at')

    if team_filter and team_filter.isdigit():
        qs = qs.filter(user__profile__team__id=team_filter)

    if result_filter == 'success':
        qs = qs.filter(success=True)
    elif result_filter == 'fail':
        qs = qs.filter(success=False)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="attendance_records.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Team', 'Date', 'Time', 'Code Entered', 'Result'])

    for attempt in qs:
        u = attempt.user
        name = u.get_full_name() or u.username
        team_name = u.profile.team.name if hasattr(u, 'profile') else ''
        local_dt = attempt.submitted_at.astimezone(tz)
        writer.writerow([
            name,
            team_name,
            local_dt.strftime('%Y-%m-%d'),
            local_dt.strftime('%I:%M %p'),
            attempt.code_entered,
            'Success' if attempt.success else 'Failed',
        ])

    return response


@login_required
def beta_reset_db(request):
    allowed = [e.strip() for e in os.environ.get("RESET_DB_ALLOWED_EMAILS", "").split(",") if e.strip()]
    if request.user.email not in allowed:
        return HttpResponseForbidden("Not authorized.")
    call_command("set_db_state")
    return JsonResponse({"ok": True, "message": "Database seeded successfully."})