from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from .models import Team, UserProfile


def make_user(username, team, role):
    user = User.objects.create_user(username=username, password='pw')
    UserProfile.objects.filter(user=user).update(team=team, role=role)
    user.refresh_from_db()
    return user


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class TasksDropdownTeamIsolationTest(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(name='Team A')
        self.team_b = Team.objects.create(name='Team B')

        self.exec_user   = make_user('exec_a',   self.team_a, 'exec')
        self.member_a1   = make_user('member_a1', self.team_a, 'member')
        self.member_a2   = make_user('member_a2', self.team_a, 'member')
        self.member_b    = make_user('member_b',  self.team_b, 'member')
        self.admin_user  = make_user('admin_a',   self.team_a, 'admin')

        self.client = Client()
        self.client.login(username='exec_a', password='pw')

    def test_dropdown_contains_only_own_team_members(self):
        response = self.client.get('/tasks/')
        self.assertEqual(response.status_code, 200)
        team_members = list(response.context['team_members'])

        self.assertIn(self.member_a1, team_members)
        self.assertIn(self.member_a2, team_members)

    def test_dropdown_excludes_other_team_members(self):
        response = self.client.get('/tasks/')
        team_members = list(response.context['team_members'])

        self.assertNotIn(self.member_b, team_members)

    def test_dropdown_excludes_admins(self):
        response = self.client.get('/tasks/')
        team_members = list(response.context['team_members'])

        self.assertNotIn(self.admin_user, team_members)
