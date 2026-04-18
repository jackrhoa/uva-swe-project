"""
Management command to populate the database with a default demo state.

Since login is Google OAuth only, this command seeds teams, tasks, announcements,
and attendance data. It uses existing users (already logged in via Google) for
any relational fields that require a real user.

Allowed emails are read from the ALLOWED_USER_EMAILS env var (comma-separated).
Set this in your .env file to control which accounts survive --prune-users.

Roles are read from the SEED_USER_ROLES env var (comma-separated email:role pairs).
Example: SEED_USER_ROLES=you@gmail.com:exec,other@gmail.com:member

Usage:
    python manage.py set_db_state
    python manage.py set_db_state --flush
    python manage.py set_db_state --prune-users
    python manage.py set_db_state --set-role you@gmail.com exec Engineering
"""

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
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


TEAMS = ["Engineering", "Design", "Marketing", "Operations"]

# (name, description, priority, whole_team, team_name, total_actions, actions_completed)
TASKS = [
    ("Set up CI/CD pipeline",   "Configure GitHub Actions for automated testing and deployment.", 4, True,  "Engineering", 5, 2),
    ("API endpoint audit",       "Review all REST endpoints for auth and rate-limiting gaps.",     3, False, "Engineering", 3, 0),
    ("Redesign landing page",    "Update hero section and color palette per new brand guide.",     2, True,  "Design",      4, 1),
    ("Component library v2",     "Migrate Figma components to the new design tokens.",             2, False, "Design",      6, 3),
    ("Q2 campaign brief",        "Draft the copy and assets for the spring email campaign.",       3, True,  "Marketing",   3, 0),
    ("Social media calendar",    "Plan posts for April and May across all channels.",              1, False, "Marketing",   2, 2),
    ("Vendor contract renewals", "Review and renew three expiring SaaS subscriptions.",            3, True,  "Operations",  3, 1),
    ("Onboarding checklist",     "Update the new-member onboarding doc with current tooling.",     1, False, "Operations",  2, 0),
]

# (body, target, target_team_name_or_None)
ANNOUNCEMENTS = [
    ("Welcome to CIO Manager! Use this platform to track tasks, attendance, and stay in the loop.", "all",      None),
    ("Engineering team: sprint planning is every Monday at 10 AM in Room 302.",                     "specific", "Engineering"),
    ("Design review is scheduled for this Friday — please upload your assets by Thursday EOD.",     "specific", "Design"),
    ("All-hands meeting next Wednesday at 2 PM. Attendance is mandatory.",                          "all",      None),
]

ROLE_CHOICES = ("exec", "member", "admin")


class Command(BaseCommand):
    help = "Seed the database with a default demo state (Google OAuth compatible)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing app data (except users) before seeding.",
        )
        parser.add_argument(
            "--set-role",
            nargs=3,
            metavar=("EMAIL", "ROLE", "TEAM"),
            help=(
                "Assign a role and team to an existing Google-authenticated user. "
                f"ROLE must be one of: {', '.join(ROLE_CHOICES)}. "
                "Example: --set-role you@gmail.com exec Engineering"
            ),
        )

    def handle(self, *args, **options):
        if options["set_role"]:
            email, role, team_name = options["set_role"]
            self._set_role(email, role, team_name)

        if options["flush"]:
            self._flush()

        self._apply_env_roles()

        teams = self._create_teams()
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
            if len(parts) != 2:
                self.stdout.write(self.style.WARNING(f"  Skipping malformed SEED_USER_ROLES entry: {entry!r}"))
                continue
            email, role = parts[0].strip(), parts[1].strip()
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
            profile.save()
            self.stdout.write(f"  Role: {email} → {role}")

    def _flush(self):
        self.stdout.write("Flushing existing app data (auth.User records preserved)...")
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
        self.stdout.write("  Note: run --set-role to reassign roles after flush.")
        self.stdout.write("  Done.")

    def _set_role(self, email, role, team_name):
        if role not in ROLE_CHOICES:
            raise CommandError(f"Invalid role '{role}'. Choose from: {', '.join(ROLE_CHOICES)}")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(
                f"No user found with email '{email}'. "
                "The user must have logged in via Google at least once."
            )

        team, _ = Team.objects.get_or_create(name=team_name)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.team = team
        profile.save()

        self.stdout.write(
            self.style.SUCCESS(f"  Set {email} → role={role}, team={team_name}")
        )

    def _create_teams(self):
        teams = {}
        no_team, _ = Team.objects.get_or_create(name="No Team")
        teams["No Team"] = no_team
        for name in TEAMS:
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
        for name, desc, priority, whole_team, team_name, total, completed in TASKS:
            _, created = Task.objects.get_or_create(
                name=name,
                team=teams[team_name],
                defaults=dict(
                    description=desc,
                    priority=priority,
                    whole_team=whole_team,
                    total_actions=total,
                    actions_completed=completed,
                ),
            )
            if created:
                self.stdout.write(f"  Task: {name}")

    def _create_announcements(self, teams):
        sender = self._any_exec()
        for body, target, team_name in ANNOUNCEMENTS:
            ann, created = Announcement.objects.get_or_create(
                body=body,
                defaults=dict(sent_by=sender, target=target),
            )
            if created and target == "specific" and team_name:
                ann.target_teams.set([teams[team_name]])
            if created:
                self.stdout.write(f"  Announcement: {body[:60]}...")

    def _create_attendance(self):
        if AttendanceSession.objects.exists():
            return
        session = AttendanceSession.objects.create(
            is_active=False,
            started_at=timezone.now() - timezone.timedelta(hours=2),
            ended_at=timezone.now() - timezone.timedelta(hours=1),
            created_by=self._any_exec(),
        )
        self.stdout.write(f"  AttendanceSession: past session ({session.code})")

    def _create_team_conversations(self, teams):
        for team_name, team in teams.items():
            if team_name == "No Team":
                continue
            tc, created = TeamConversation.objects.get_or_create(team=team)
            if created:
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
