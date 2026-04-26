from django.test import TestCase, Client
from django.contrib.auth.models import User
from users.models import (
    Team, UserProfile, Task, get_default_team, _generate_code,
    Announcement, AnnouncementRead, AttendanceSession, AttendanceAttempt,
    get_announcement_for_user, get_announcements_for_user,
)
import json


def make_user(username, role='member', team=None):
    user = User.objects.create_user(username=username, password='testpass123')
    profile = user.profile
    profile.role = role
    if team:
        profile.team = team
    profile.save()
    return user


class TeamModelTests(TestCase):
    def test_get_default_team_creates_no_team(self):
        team_id = get_default_team()
        team = Team.objects.get(id=team_id)
        self.assertEqual(team.name, "No Team")

    def test_get_default_team_idempotent(self):
        id1 = get_default_team()
        id2 = get_default_team()
        self.assertEqual(id1, id2)

    def test_team_str(self):
        team = Team.objects.create(name="Engineering")
        self.assertEqual(str(team), "Engineering")


class UserProfileModelTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")

    def test_is_exec_true(self):
        user = make_user('exec_user', role='exec', team=self.team)
        self.assertTrue(user.profile.is_exec())

    def test_is_exec_false_for_member(self):
        user = make_user('member_user', role='member', team=self.team)
        self.assertFalse(user.profile.is_exec())

    def test_is_admin_true(self):
        user = make_user('admin_user', role='admin', team=self.team)
        self.assertTrue(user.profile.is_admin())

    def test_is_admin_false_for_exec(self):
        user = make_user('exec_user', role='exec', team=self.team)
        self.assertFalse(user.profile.is_admin())

    def test_is_admin_false_for_member(self):
        user = make_user('member_user', role='member', team=self.team)
        self.assertFalse(user.profile.is_admin())

    def test_default_role_is_member(self):
        user = User.objects.create_user(username='newuser', password='testpass123')
        self.assertEqual(user.profile.role, 'member')

    def test_profile_str(self):
        user = make_user('struser', role='exec', team=self.team)
        self.assertIn('exec', str(user.profile))
        self.assertIn('TestTeam', str(user.profile))

    def test_profile_created_via_signal(self):
        user = User.objects.create_user(username='signaluser', password='testpass123')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, UserProfile)


class TaskModelTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="DevTeam")

    def test_is_completed_true(self):
        task = Task.objects.create(name="Done", team=self.team, total_actions=3, actions_completed=3)
        self.assertTrue(task.is_completed())

    def test_is_completed_false(self):
        task = Task.objects.create(name="WIP", team=self.team, total_actions=3, actions_completed=1)
        self.assertFalse(task.is_completed())

    def test_is_completed_when_over(self):
        task = Task.objects.create(name="Over", team=self.team, total_actions=2, actions_completed=5)
        self.assertTrue(task.is_completed())

    def test_task_str(self):
        task = Task.objects.create(name="MyTask", team=self.team, priority=3)
        self.assertIn("MyTask", str(task))
        self.assertIn("DevTeam", str(task))


class AttendanceCodeTests(TestCase):
    def test_generate_code_length(self):
        code = _generate_code()
        self.assertEqual(len(code), 6)

    def test_generate_code_uppercase_alphanumeric(self):
        for _ in range(20):
            code = _generate_code()
            for char in code:
                self.assertTrue(char.isalpha() or char.isdigit())
                if char.isalpha():
                    self.assertTrue(char.isupper())

    def test_generate_code_excludes_ambiguous(self):
        for _ in range(50):
            code = _generate_code()
            self.assertNotIn('O', code)
            self.assertNotIn('0', code)

    def test_codes_are_random(self):
        codes = {_generate_code() for _ in range(20)}
        self.assertGreater(len(codes), 1)


# ── Access Control Tests ─────────────────────────────────────────────────────

class UnauthenticatedAccessTests(TestCase):
    def test_home_redirects_to_login(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_profile_redirects_to_login(self):
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_tasks_redirects_to_login(self):
        response = self.client.get('/tasks/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_manage_roles_redirects_to_login(self):
        response = self.client.get('/manage-roles/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_manage_teams_redirects_to_login(self):
        response = self.client.get('/manage-teams/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_messages_redirects_to_login(self):
        response = self.client.get('/messages/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_admin_panel_redirects_to_login(self):
        response = self.client.get('/admin-panel/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)


class AdminAccessControlTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.admin = make_user('adminuser', role='admin', team=self.team)
        self.client.login(username='adminuser', password='testpass123')

    def test_home_redirects_to_admin_dashboard(self):
        response = self.client.get('/')
        self.assertRedirects(response, '/admin-panel/', fetch_redirect_response=False)

    def test_admin_dashboard_accessible(self):
        response = self.client.get('/admin-panel/')
        self.assertEqual(response.status_code, 200)

    def test_profile_redirects_to_admin_dashboard(self):
        response = self.client.get('/profile/')
        self.assertRedirects(response, '/admin-panel/', fetch_redirect_response=False)

    def test_tasks_redirects_to_admin_dashboard(self):
        response = self.client.get('/tasks/')
        self.assertRedirects(response, '/admin-panel/', fetch_redirect_response=False)

    def test_manage_roles_accessible(self):
        response = self.client.get('/manage-roles/')
        self.assertEqual(response.status_code, 200)

    def test_manage_teams_redirects(self):
        response = self.client.get('/manage-teams/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)


class ExecAccessControlTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.exec_user = make_user('execuser', role='exec', team=self.team)
        self.client.login(username='execuser', password='testpass123')

    def test_home_redirects_to_exec_dashboard(self):
        response = self.client.get('/')
        self.assertRedirects(response, '/exec/', fetch_redirect_response=False)

    def test_exec_dashboard_accessible(self):
        response = self.client.get('/exec/')
        self.assertEqual(response.status_code, 200)

    def test_manage_roles_redirects_away(self):
        response = self.client.get('/manage-roles/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_manage_teams_accessible(self):
        response = self.client.get('/manage-teams/')
        self.assertEqual(response.status_code, 200)

    def test_tasks_accessible(self):
        response = self.client.get('/tasks/')
        self.assertEqual(response.status_code, 200)

    def test_profile_accessible(self):
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 200)

    def test_admin_dashboard_redirects(self):
        response = self.client.get('/admin-panel/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)


class MemberAccessControlTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.member = make_user('memberuser', role='member', team=self.team)
        self.client.login(username='memberuser', password='testpass123')

    def test_home_redirects_to_member_dashboard(self):
        response = self.client.get('/')
        self.assertRedirects(response, '/member/', fetch_redirect_response=False)

    def test_member_dashboard_accessible(self):
        response = self.client.get('/member/')
        self.assertEqual(response.status_code, 200)

    def test_manage_roles_redirects(self):
        response = self.client.get('/manage-roles/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_manage_teams_redirects(self):
        response = self.client.get('/manage-teams/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_tasks_accessible(self):
        response = self.client.get('/tasks/')
        self.assertEqual(response.status_code, 200)

    def test_profile_accessible(self):
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 200)

    def test_admin_dashboard_redirects(self):
        response = self.client.get('/admin-panel/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_exec_dashboard_redirects_to_member(self):
        response = self.client.get('/exec/')
        self.assertRedirects(response, '/member/', fetch_redirect_response=False)

    def test_attendance_records_page_redirects(self):
        response = self.client.get('/attendance/records/page/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)


# ── Role Management Tests ────────────────────────────────────────────────────

class RoleManagementTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.admin = make_user('adminuser', role='admin', team=self.team)
        self.target_user = make_user('targetuser', role='member', team=self.team)

    def test_admin_can_change_role_to_exec(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.post(
            f'/change-role/{self.target_user.id}/',
            {'role': 'exec'}
        )
        self.target_user.profile.refresh_from_db()
        self.assertEqual(self.target_user.profile.role, 'exec')

    def test_admin_can_change_role_to_member(self):
        self.client.login(username='adminuser', password='testpass123')
        self.target_user.profile.role = 'exec'
        self.target_user.profile.save()
        response = self.client.post(
            f'/change-role/{self.target_user.id}/',
            {'role': 'member'}
        )
        self.target_user.profile.refresh_from_db()
        self.assertEqual(self.target_user.profile.role, 'member')

    def test_admin_cannot_assign_admin_role(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.post(
            f'/change-role/{self.target_user.id}/',
            {'role': 'admin'}
        )
        self.target_user.profile.refresh_from_db()
        self.assertEqual(self.target_user.profile.role, 'member')

    def test_admin_cannot_change_own_role(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.post(
            f'/change-role/{self.admin.id}/',
            {'role': 'member'}
        )
        self.admin.profile.refresh_from_db()
        self.assertEqual(self.admin.profile.role, 'admin')

    def test_exec_cannot_access_change_role(self):
        exec_user = make_user('execuser', role='exec', team=self.team)
        self.client.login(username='execuser', password='testpass123')
        response = self.client.post(
            f'/change-role/{self.target_user.id}/',
            {'role': 'exec'}
        )
        self.target_user.profile.refresh_from_db()
        self.assertEqual(self.target_user.profile.role, 'member')

    def test_member_cannot_access_change_role(self):
        member = make_user('memberuser', role='member', team=self.team)
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post(
            f'/change-role/{self.target_user.id}/',
            {'role': 'exec'}
        )
        self.target_user.profile.refresh_from_db()
        self.assertEqual(self.target_user.profile.role, 'member')


# ── Task Visibility Tests ────────────────────────────────────────────────────

class TaskVisibilityTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="DevTeam")
        self.exec_user = make_user('execuser', role='exec', team=self.team)
        self.member = make_user('memberuser', role='member', team=self.team)

        self.whole_team_task = Task.objects.create(
            name="Team Task", team=self.team, whole_team=True
        )
        self.assigned_task = Task.objects.create(
            name="Assigned Task", team=self.team, whole_team=False
        )
        self.assigned_task.active_users.add(self.member)

        self.unassigned_task = Task.objects.create(
            name="Hidden Task", team=self.team, whole_team=False
        )

    def test_exec_sees_all_tasks(self):
        self.client.login(username='execuser', password='testpass123')
        response = self.client.get('/tasks/')
        self.assertContains(response, 'Team Task')
        self.assertContains(response, 'Assigned Task')
        self.assertContains(response, 'Hidden Task')

    def test_member_sees_whole_team_task(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.get('/tasks/')
        self.assertContains(response, 'Team Task')

    def test_member_sees_assigned_task(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.get('/tasks/')
        self.assertContains(response, 'Assigned Task')

    def test_member_does_not_see_unassigned_task(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.get('/tasks/')
        self.assertNotContains(response, 'Hidden Task')

    def test_admin_redirected_from_tasks(self):
        admin = make_user('adminuser', role='admin', team=self.team)
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/tasks/')
        self.assertRedirects(response, '/admin-panel/', fetch_redirect_response=False)

    def test_admin_excluded_from_team_members_in_tasks(self):
        admin = make_user('adminuser', role='admin', team=self.team)
        self.client.login(username='execuser', password='testpass123')
        response = self.client.get('/tasks/')
        self.assertNotContains(response, 'adminuser')


# ── Team Management Tests ────────────────────────────────────────────────────

class TeamManagementTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.exec_user = make_user('execuser', role='exec', team=self.team)
        self.client.login(username='execuser', password='testpass123')

    def test_add_team(self):
        self.client.post('/add-team/', {'team_name': 'NewTeam'})
        self.assertTrue(Team.objects.filter(name='NewTeam').exists())

    def test_add_duplicate_team(self):
        self.client.post('/add-team/', {'team_name': 'TestTeam'})
        self.assertEqual(Team.objects.filter(name='TestTeam').count(), 1)

    def test_delete_team(self):
        new_team = Team.objects.create(name="ToDelete")
        self.client.get(f'/delete-team/{new_team.id}/')
        self.assertFalse(Team.objects.filter(name="ToDelete").exists())

    def test_change_team(self):
        new_team = Team.objects.create(name="Engineering")
        member = make_user('memberuser', role='member', team=self.team)
        self.client.post(f'/change-team/{member.id}/', {'team': new_team.id})
        member.profile.refresh_from_db()
        self.assertEqual(member.profile.team, new_team)

    def test_admins_excluded_from_manage_teams(self):
        admin = make_user('adminuser', role='admin', team=self.team)
        response = self.client.get('/manage-teams/')
        self.assertNotContains(response, 'adminuser')


# ── Attendance Tests ─────────────────────────────────────────────────────────

class AttendanceTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.exec_user = make_user('execuser', role='exec', team=self.team)
        self.member = make_user('memberuser', role='member', team=self.team)

    def test_exec_can_generate_code(self):
        self.client.login(username='execuser', password='testpass123')
        response = self.client.post('/attendance/generate/')
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(len(data['code']), 6)

    def test_member_cannot_generate_code(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post('/attendance/generate/')
        self.assertEqual(response.status_code, 403)

    def test_submit_without_email_returns_403(self):
        self.client.login(username='execuser', password='testpass123')
        self.client.post('/attendance/generate/')

        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post(
            '/attendance/submit/',
            json.dumps({'code': 'AAAAAA'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_incorrect_code_fails(self):
        self.client.login(username='execuser', password='testpass123')
        self.client.post('/attendance/generate/')

        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post(
            '/attendance/submit/',
            json.dumps({'code': 'ZZZZZZ'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_submit_with_no_active_session(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post(
            '/attendance/submit/',
            json.dumps({'code': 'ABCDEF'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_end_session(self):
        self.client.login(username='execuser', password='testpass123')
        self.client.post('/attendance/generate/')
        self.assertIsNotNone(AttendanceSession.get_active())

        self.client.post('/attendance/end/')
        self.assertIsNone(AttendanceSession.get_active())

    def test_new_code_deactivates_old_session(self):
        self.client.login(username='execuser', password='testpass123')
        resp1 = self.client.post('/attendance/generate/')
        code1 = resp1.json()['code']

        resp2 = self.client.post('/attendance/generate/')
        code2 = resp2.json()['code']

        self.assertNotEqual(code1, code2)
        active = AttendanceSession.get_active()
        self.assertEqual(active.code, code2)


# ── Announcement Tests ───────────────────────────────────────────────────────

class AnnouncementModelTests(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(name="TeamA")
        self.team_b = Team.objects.create(name="TeamB")
        self.user_a = make_user('usera', role='member', team=self.team_a)
        self.user_b = make_user('userb', role='member', team=self.team_b)
        self.exec_user = make_user('execuser', role='exec', team=self.team_a)

    def test_all_target_visible_to_everyone(self):
        ann = Announcement.objects.create(
            body="Hello all", sent_by=self.exec_user, target=Announcement.TARGET_ALL
        )
        self.assertEqual(get_announcement_for_user(self.user_a), ann)
        self.assertEqual(get_announcement_for_user(self.user_b), ann)

    def test_specific_target_visible_only_to_target_team(self):
        ann = Announcement.objects.create(
            body="TeamA only", sent_by=self.exec_user, target=Announcement.TARGET_SPECIFIC
        )
        ann.target_teams.add(self.team_a)

        self.assertEqual(get_announcement_for_user(self.user_a), ann)
        self.assertIsNone(get_announcement_for_user(self.user_b))

    def test_get_announcements_returns_multiple(self):
        ann1 = Announcement.objects.create(
            body="First", sent_by=self.exec_user, target=Announcement.TARGET_ALL
        )
        ann2 = Announcement.objects.create(
            body="Second", sent_by=self.exec_user, target=Announcement.TARGET_ALL
        )
        announcements = list(get_announcements_for_user(self.user_a))
        self.assertEqual(len(announcements), 2)


class AnnouncementViewTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.exec_user = make_user('execuser', role='exec', team=self.team)
        self.member = make_user('memberuser', role='member', team=self.team)

    def test_mark_announcement_read(self):
        ann = Announcement.objects.create(
            body="Test", sent_by=self.exec_user, target=Announcement.TARGET_ALL
        )
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post(f'/announcements/mark-read/{ann.id}/')
        self.assertEqual(response.json()['ok'], True)
        self.assertTrue(
            AnnouncementRead.objects.filter(user=self.member, announcement=ann).exists()
        )

    def test_unmark_announcement_read(self):
        ann = Announcement.objects.create(
            body="Test", sent_by=self.exec_user, target=Announcement.TARGET_ALL
        )
        AnnouncementRead.objects.create(user=self.member, announcement=ann)
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post(f'/announcements/unmark-read/{ann.id}/')
        self.assertEqual(response.json()['ok'], True)
        self.assertFalse(
            AnnouncementRead.objects.filter(user=self.member, announcement=ann).exists()
        )

    def test_exec_can_send_team_announcement(self):
        self.client.login(username='execuser', password='testpass123')
        response = self.client.post(
            f'/announcements/send-to-team/{self.team.id}/',
            {'body': 'Team announcement'}
        )
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(Announcement.objects.count(), 1)

    def test_member_cannot_send_team_announcement(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.post(
            f'/announcements/send-to-team/{self.team.id}/',
            {'body': 'Nope'}
        )
        self.assertEqual(response.status_code, 403)


# ── Task Add/Remove Tests ───────────────────────────────────────────────────

class TaskAddRemoveTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.exec_user = make_user('execuser', role='exec', team=self.team)
        self.member = make_user('memberuser', role='member', team=self.team)

    def test_exec_can_add_task(self):
        self.client.login(username='execuser', password='testpass123')
        self.client.post(
            '/tasks/add/',
            json.dumps({'name': 'Test Task'}),
            content_type='application/json'
        )
        self.assertEqual(Task.objects.filter(team=self.team).count(), 1)

    def test_member_cannot_add_task(self):
        self.client.login(username='memberuser', password='testpass123')
        self.client.post(
            '/tasks/add/',
            json.dumps({'name': 'Test Task'}),
            content_type='application/json'
        )
        self.assertEqual(Task.objects.filter(team=self.team).count(), 0)

    def test_exec_can_remove_task(self):
        self.client.login(username='execuser', password='testpass123')
        task = Task.objects.create(name="ToRemove", team=self.team)
        self.client.get(f'/tasks/{task.id}/remove/')
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_member_cannot_remove_task(self):
        self.client.login(username='memberuser', password='testpass123')
        task = Task.objects.create(name="Protected", team=self.team)
        self.client.get(f'/tasks/{task.id}/remove/')
        self.assertTrue(Task.objects.filter(id=task.id).exists())


# ── Delete Account Tests ─────────────────────────────────────────────────────

class DeleteAccountTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")

    def test_member_can_delete_account(self):
        member = make_user('deleteme', role='member', team=self.team)
        self.client.login(username='deleteme', password='testpass123')
        response = self.client.post('/profile/delete/')
        self.assertFalse(User.objects.filter(username='deleteme').exists())

    def test_exec_cannot_delete_account(self):
        exec_user = make_user('execuser', role='exec', team=self.team)
        self.client.login(username='execuser', password='testpass123')
        response = self.client.post('/profile/delete/')
        self.assertTrue(User.objects.filter(username='execuser').exists())