"""
Management command to reset and reseed the database with a default demo state.

Flushes all app data, deletes users not in ALLOWED_USER_EMAILS, then reseeds
teams, tasks, announcements, attendance, and team conversations.

ALLOWED_USER_EMAILS  — comma-separated emails; others are deleted on flush.
SEED_TEAMS           — comma-separated team names (default: Engineering Team,Design,Marketing,Operations).
SEED_USER_ROLES      — comma-separated email:role or email:role:team entries.
  Example: SEED_USER_ROLES=you@gmail.com:exec:Engineering Team,other@gmail.com:member

Usage:
    python manage.py set_db_state
"""

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import (
    Announcement,
    AnnouncementRead,
    AttendanceAttempt,
    AttendanceSession,
    Task,
    Team,
    UserProfile,
)
from messaging.models import (
    Conversation,
    ConversationRead,
    Message,
    TeamConversation,
    TeamMessage,
)


DEFAULT_TEAMS = ["Engineering Team", "Design"]

# (name, description, priority, whole_team, team_name, total_actions, actions_completed)
TASKS = [
    ("Set up CI/CD pipeline",   "Configure GitHub Actions for automated testing and deployment.", 4, True,  "Engineering Team", 5, 2),
    ("API endpoint audit",       "Review all REST endpoints for auth and rate-limiting gaps.",     3, False, "Engineering Team", 3, 0),
    ("Redesign landing page",    "Update hero section and color palette per new brand guide.",     2, True,  "Design",           4, 1),
    ("Component library v2",     "Migrate Figma components to the new design tokens.",             2, False, "Design",           6, 3),
]

# (body, target, target_team_name_or_None)
ANNOUNCEMENTS = [
    ("Welcome to CIO Manager! Use this platform to track tasks, attendance, and stay in the loop.", "all",      None),
    ("Engineering Team: sprint planning is every Monday at 10 AM in Room 302.",                     "specific", "Engineering Team"),
    ("Design review is scheduled for this Friday — please upload your assets by Thursday EOD.",     "specific", "Design"),
    ("All-hands meeting next Wednesday at 2 PM. Attendance is mandatory.",                          "all",      None),
]

ROLE_CHOICES = ("exec", "member", "admin")


class Command(BaseCommand):
    help = "Seed the database with a default demo state (Google OAuth compatible)."

    def handle(self, *args, **options):
        self._flush()

        teams = self._create_teams()
        self._apply_env_roles()
        self._create_tasks(teams)
        self._create_announcements(teams)
        self._create_attendance()
        self._create_team_conversations(teams)

        self.stdout.write(self.style.SUCCESS("Database seeded successfully."))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_env_roles(self):
        raw = os.environ.get("SEED_USER_ROLES", "").strip()
        if not raw:
            return
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) < 2 or len(parts) > 3:
                self.stdout.write(self.style.WARNING(f"  Skipping malformed SEED_USER_ROLES entry: {entry!r}"))
                continue
            email, role = parts[0].strip(), parts[1].strip()
            team_name = parts[2].strip() if len(parts) == 3 else None
            if role not in ROLE_CHOICES:
                self.stdout.write(self.style.WARNING(f"  Skipping unknown role {role!r} for {email}"))
                continue
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  No user found for {email} (must log in via Google first)"))
                continue
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            if team_name:
                try:
                    profile.team = Team.objects.get(name=team_name)
                except Team.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"  Team {team_name!r} not found for {email}"))
            profile.save()
            self.stdout.write(f"  Role: {email} → {role}" + (f", team={team_name}" if team_name else ""))

    def _flush(self):
        self.stdout.write("Flushing existing app data...")
        for model in (
            TeamMessage, TeamConversation,
            Message, ConversationRead, Conversation,
            AttendanceAttempt, AttendanceSession,
            AnnouncementRead, Announcement,
            Task,
            UserProfile,
            Team,
        ):
            model.objects.all().delete()

        allowed = {
            e.strip().lower()
            for e in os.environ.get("ALLOWED_USER_EMAILS", "").split(",")
            if e.strip()
        }
        deleted = User.objects.exclude(email__in=allowed).exclude(is_superuser=True).delete()
        self.stdout.write(f"  Deleted {deleted[0]} user(s) not in ALLOWED_USER_EMAILS.")

        surviving_users = User.objects.filter(email__in=allowed) | User.objects.filter(is_superuser=True)
        for user in surviving_users.distinct():
            UserProfile.objects.get_or_create(user=user)
            self.stdout.write(f"  Recreated profile for {user.email}")

        self.stdout.write("  Done.")

    def _create_teams(self):
        raw = os.environ.get("SEED_TEAMS", "").strip()
        team_names = [t.strip() for t in raw.split(",") if t.strip()] if raw else DEFAULT_TEAMS
        teams = {}
        no_team, _ = Team.objects.get_or_create(name="No Team")
        teams["No Team"] = no_team
        for name in team_names:
            team, _ = Team.objects.get_or_create(name=name)
            teams[name] = team
            self.stdout.write(f"  Team: {name}")
        return teams

    def _any_exec(self):
        """Return any exec-role user, or any user, or None."""
        profile = (
            UserProfile.objects.filter(role="exec").select_related("user").first()
            or UserProfile.objects.select_related("user").first()
        )
        return profile.user if profile else None

    def _create_tasks(self, teams):
        Task.objects.all().delete()
        for name, desc, priority, whole_team, team_name, total, completed in TASKS:
            if team_name not in teams:
                continue
            Task.objects.create(
                name=name,
                team=teams[team_name],
                description=desc,
                priority=priority,
                whole_team=whole_team,
                total_actions=total,
                actions_completed=completed,
            )
            self.stdout.write(f"  Task: {name}")

    def _create_announcements(self, teams):
        AnnouncementRead.objects.all().delete()
        Announcement.objects.all().delete()
        sender = self._any_exec()
        for body, target, team_name in ANNOUNCEMENTS:
            if target == "specific" and team_name and team_name not in teams:
                continue
            ann = Announcement.objects.create(body=body, sent_by=sender, target=target)
            if target == "specific" and team_name:
                ann.target_teams.set([teams[team_name]])
            self.stdout.write(f"  Announcement: {body[:60]}...")

    def _create_attendance(self):
        AttendanceAttempt.objects.all().delete()
        AttendanceSession.objects.all().delete()
        session = AttendanceSession.objects.create(
            is_active=False,
            started_at=timezone.now() - timezone.timedelta(hours=2),
            ended_at=timezone.now() - timezone.timedelta(hours=1),
            created_by=self._any_exec(),
        )
        self.stdout.write(f"  AttendanceSession: past session ({session.code})")

    def _create_team_conversations(self, teams):
        TeamMessage.objects.all().delete()
        TeamConversation.objects.all().delete()
        for team_name, team in teams.items():
            if team_name == "No Team":
                continue
            tc = TeamConversation.objects.create(team=team)
            sender = (
                UserProfile.objects
                .filter(team=team)
                .select_related("user")
                .first()
            )
            if sender:
                TeamMessage.objects.create(
                    team_conversation=tc,
                    sender=sender.user,
                    content=f"Welcome to the {team_name} team channel!",
                )
            self.stdout.write(f"  TeamConversation: {team_name}")
