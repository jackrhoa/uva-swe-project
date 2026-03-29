from django.utils import timezone
from django.db import IntegrityError, models
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Team, UserProfile, Task
from .forms import ProfileNameForm
import json


@login_required
def home(request):
    profile = request.user.profile
    if profile.is_exec():
        return redirect('exec_dashboard')
    return redirect('member_dashboard')

@login_required
def exec_dashboard(request):
    if not request.user.profile.is_exec():
        return redirect('member_dashboard')
    return render(request, 'exec_dashboard.html', {'profile': request.user.profile})

@login_required
def member_dashboard(request):
    if request.user.profile.is_exec():
        return redirect('exec_dashboard')
    return render(request, 'member_dashboard.html', {'profile': request.user.profile})

@login_required
def profile(request):
    return render(request, 'profile.html', {
        'profile': request.user.profile,
        'picture': '',
    })

@login_required
def manage_roles(request):
    if not request.user.profile.is_exec():
        return redirect('home')
    users = UserProfile.objects.select_related('user').all()
    return render(request, 'manage_roles.html', {'users': users})

@login_required
def change_role(request, user_id):
    if not request.user.profile.is_exec():
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
    users = UserProfile.objects.select_related('user').all()
    return render(request, 'manage_teams.html', {'users': users , 'teams': teams})

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
            try:
                Team.objects.create(name=team_name)
            except IntegrityError:
                pass
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
            return redirect('profile')
    else:
        form = ProfileNameForm(instance=request.user)

    return render(request, 'edit_profile.html', {'form': form})

@login_required
def delete_account(request):
    if request.user.profile.is_exec():
        return redirect('profile')
    if request.method == 'POST':
        user = request.user
        logout(request)
        user.delete()
        return redirect('account_login')
    return redirect('profile')

@login_required
def tasks(request):
    team = request.user.profile.team
    from django.db.models import Q, Case, When, Value, IntegerField
 
    all_tasks = Task.objects.filter(team=team)
 
    # Visibility: exec sees all; members see whole_team tasks or tasks assigned to them
    if request.user.profile.is_exec():
        visible = all_tasks
    else:
        visible = all_tasks.filter(
            Q(whole_team=True) | Q(active_users=request.user)
        ).distinct()
 
    # Undetermined (priority=0) always first, then highest priority, then name
    priority_order = Case(
        When(priority=0, then=Value(0)),
        default=Value(1),
        output_field=IntegerField()
    )
 
    uncompleted_tasks = (
        visible
        .filter(actions_completed__lt=models.F('total_actions'))
        .order_by(priority_order, '-priority', 'name')
    )
    completed_tasks = (
        visible
        .filter(actions_completed__gte=models.F('total_actions'))
        .order_by('-priority', 'name')
    )
 
    team_members = User.objects.filter(profile__team=team)
    now = timezone.now()
 
    return render(request, 'tasks.html', {
        'uncompleted_tasks': uncompleted_tasks,
        'completed_tasks':   completed_tasks,
        'is_exec':           request.user.profile.is_exec(),
        'team_members':      team_members,
        'team_name':         team.name,
        'now':               now,
    })


# Exec-only: Add a blank task
@login_required
def add_task(request):
    if not request.user.profile.is_exec():
        return redirect('tasks')
 
    Task.objects.create(
        name="New Task",
        description="",
        team=request.user.profile.team,
        total_actions=1,
        actions_completed=0,
        priority=0   # Undetermined by default
    )
    return redirect('tasks')


# Exec-only: Remove task
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
 
            # Deadline: empty string clears it, ISO string sets it
            deadline_raw = data.get('deadline', None)
            if deadline_raw == '' or deadline_raw is None:
                if 'deadline' in data:   # key present but empty → clear
                    task.deadline = None
            else:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(deadline_raw)
                if parsed:
                    # Make timezone-aware if USE_TZ=True and parsed is naive
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
                    'id':      u.id,
                    'name':    u.get_full_name() or u.username,
                    'initial': (u.first_name[:1] or u.username[:1]).upper(),
                }
                for u in task.active_users.all()
            ],
        })
 
    return JsonResponse({'error': 'Invalid method'}, status=400)