from django.test import TestCase
from django.contrib.auth.models import User
from users.models import Team, UserProfile
from messaging.models import Conversation, Message
from messaging.views import get_allowed_users


def make_user(username, role='member', team=None):
    user = User.objects.create_user(username=username, password='testpass123')
    profile = user.profile
    profile.role = role
    if team:
        profile.team = team
    profile.save()
    return user


class GetAllowedUsersTests(TestCase):
    def setUp(self):
        self.team_a = Team.objects.create(name="TeamA")
        self.team_b = Team.objects.create(name="TeamB")
        self.exec_user = make_user('execuser', role='exec', team=self.team_a)
        self.member_a = make_user('membera', role='member', team=self.team_a)
        self.member_b = make_user('memberb', role='member', team=self.team_b)
        self.admin_user = make_user('adminuser', role='admin', team=self.team_a)

    def test_exec_sees_all_non_admin_users(self):
        allowed = get_allowed_users(self.exec_user)
        allowed_ids = set(allowed.values_list('id', flat=True))
        self.assertIn(self.member_a.id, allowed_ids)
        self.assertIn(self.member_b.id, allowed_ids)
        self.assertNotIn(self.exec_user.id, allowed_ids)

    def test_exec_does_not_see_admin(self):
        allowed = get_allowed_users(self.exec_user)
        allowed_ids = set(allowed.values_list('id', flat=True))
        self.assertNotIn(self.admin_user.id, allowed_ids)

    def test_member_sees_only_own_team(self):
        allowed = get_allowed_users(self.member_a)
        allowed_ids = set(allowed.values_list('id', flat=True))
        self.assertIn(self.exec_user.id, allowed_ids)
        self.assertNotIn(self.member_b.id, allowed_ids)
        self.assertNotIn(self.member_a.id, allowed_ids)

    def test_member_does_not_see_admin(self):
        allowed = get_allowed_users(self.member_a)
        allowed_ids = set(allowed.values_list('id', flat=True))
        self.assertNotIn(self.admin_user.id, allowed_ids)


class MessageListAccessTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.admin = make_user('adminuser', role='admin', team=self.team)
        self.exec_user = make_user('execuser', role='exec', team=self.team)
        self.member = make_user('memberuser', role='member', team=self.team)

    def test_admin_redirected_from_messages(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/messages/')
        self.assertRedirects(response, '/admin-panel/', fetch_redirect_response=False)

    def test_exec_can_access_messages(self):
        self.client.login(username='execuser', password='testpass123')
        response = self.client.get('/messages/')
        self.assertEqual(response.status_code, 200)

    def test_member_can_access_messages(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.get('/messages/')
        self.assertEqual(response.status_code, 200)


class TeamChatAccessTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.admin = make_user('adminuser', role='admin', team=self.team)
        self.member = make_user('memberuser', role='member', team=self.team)

    def test_admin_redirected_from_team_chat(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/messages/team/')
        self.assertRedirects(response, '/admin-panel/', fetch_redirect_response=False)

    def test_member_can_access_team_chat(self):
        self.client.login(username='memberuser', password='testpass123')
        response = self.client.get('/messages/team/')
        self.assertEqual(response.status_code, 200)


class ConversationModelTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="TestTeam")
        self.user1 = make_user('user1', role='member', team=self.team)
        self.user2 = make_user('user2', role='member', team=self.team)

    def test_get_or_create_conversation_creates_once(self):
        conv1 = Conversation.get_or_create_conversation(self.user1, self.user2)
        conv2 = Conversation.get_or_create_conversation(self.user1, self.user2)
        self.assertEqual(conv1.id, conv2.id)

    def test_get_or_create_conversation_order_independent(self):
        conv1 = Conversation.get_or_create_conversation(self.user1, self.user2)
        conv2 = Conversation.get_or_create_conversation(self.user2, self.user1)
        self.assertEqual(conv1.id, conv2.id)

    def test_conversation_str(self):
        conv = Conversation.get_or_create_conversation(self.user1, self.user2)
        self.assertIn('user1', str(conv))
        self.assertIn('user2', str(conv))