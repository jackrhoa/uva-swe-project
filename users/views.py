from django.db import IntegrityError
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Team, UserProfile
from .forms import ProfileNameForm


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