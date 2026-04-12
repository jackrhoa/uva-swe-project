import random
import string
from django.db import models
from django.contrib.auth.models import User



class Team(models.Model):

    name = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.name
    

def get_default_team():
    from .models import Team
    team, created = Team.objects.get_or_create(name="No Team")
    return team.id

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('exec', 'Exec'),
        ('member', 'Member'),
        ('admin', 'Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_DEFAULT,
        default=get_default_team,      
        null=False,
        blank=False
    )

    def __str__(self):
        return f"{self.user.email} - {self.role} - {self.team.name}"

    def is_exec(self):
        return self.role == 'exec'

    def is_admin(self):
        return self.role == 'admin'
    
class Task(models.Model):
    PRIORITY_CHOICES = [
        (0, 'Undetermined'),
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Urgent'),
    ]
 
    # Basic info
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
 
    # Progress tracking
    actions_completed = models.PositiveIntegerField(default=0)
    total_actions = models.PositiveIntegerField(default=1)
 
    # Priority: 0=Undetermined, 1=Low, 2=Medium, 3=High, 4=Urgent
    priority = models.PositiveSmallIntegerField(default=0, choices=PRIORITY_CHOICES)
 
    # Deadline (optional)
    deadline = models.DateTimeField(null=True, blank=True)
 
    whole_team = models.BooleanField(
        default=False,
        help_text='If True, this task is visible to everyone on the team.'
    )
 
    # Relationships
    team = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='tasks')
    assigned_to = models.ManyToManyField(
        User,
        blank=True,
        related_name='assigned_tasks',
        help_text='Users assigned to this task.'
    )
    active_users = models.ManyToManyField(
        User,
        blank=True,
        related_name='active_tasks',
        help_text='Users currently working on this task.'
    )
 
    def is_completed(self):
        return self.actions_completed >= self.total_actions
 
    def display_assigned(self):
        if self.assigned_to.exists():
            return ", ".join([user.username for user in self.assigned_to.all()])
        return f"Everyone in {self.team.name}"
 
    def __str__(self):
        return f"{self.name} ({self.team.name}) - Priority {self.priority}"

class Announcement(models.Model):
    TARGET_ALL      = 'all'
    TARGET_SPECIFIC = 'specific'  # one or more specific teams
 
    TARGET_CHOICES = [
        (TARGET_ALL,      'All Teams'),
        (TARGET_SPECIFIC, 'Specific Teams'),
    ]
 
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='announcements_sent',
    )
 
    # 'all' → everyone; 'specific' → only teams in target_teams
    target = models.CharField(max_length=10, choices=TARGET_CHOICES, default=TARGET_ALL)
 
    # Populated when target == 'specific'
    target_teams = models.ManyToManyField(
        Team,
        blank=True,
        related_name='announcements',
    )
 
    class Meta:
        ordering = ['-sent_at']
 
    def __str__(self):
        return f"Announcement by {self.sent_by} at {self.sent_at:%Y-%m-%d %H:%M} → {self.target}"
 
 
def get_announcement_for_user(user):
    """
    Returns the single most recent Announcement visible to `user`, or None.
    Visible if: target == 'all'  OR  (target == 'specific' AND user's team is in target_teams).
    """
    from django.db.models import Q
    user_team = user.profile.team
    return (
        Announcement.objects
        .filter(
            Q(target=Announcement.TARGET_ALL)
            | Q(target=Announcement.TARGET_SPECIFIC, target_teams=user_team)
        )
        .order_by('-sent_at')
        .first()
    )
 
 
def get_announcements_for_user(user):
    """
    Returns all Announcements visible to `user`, newest first.
    Used for the history page.
    """
    from django.db.models import Q
    user_team = user.profile.team
    return (
        Announcement.objects
        .filter(
            Q(target=Announcement.TARGET_ALL)
            | Q(target=Announcement.TARGET_SPECIFIC, target_teams=user_team)
        )
        .order_by('-sent_at')
        .distinct()
    )

class AnnouncementRead(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcement_reads')
    announcement = models.ForeignKey('Announcement', on_delete=models.CASCADE, related_name='reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'announcement')]


def _generate_code():
    """Return a random 6-character alphanumeric code (uppercase)."""
    chars = [c for c in string.ascii_uppercase + string.digits if c not in ('O', '0')]
    return ''.join(random.choices(chars, k=6))
 
 
class AttendanceSession(models.Model):
    """
    Global singleton-ish model: only one row should be active at a time.
    is_active=True means the code is currently live.
    """
    code = models.CharField(max_length=6, default=_generate_code)
    is_active = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='attendance_sessions',
    )
 
    class Meta:
        ordering = ['-started_at']
 
    def __str__(self):
        status = 'LIVE' if self.is_active else 'ended'
        return f"Session {self.code} ({status})"
 
    @classmethod
    def get_active(cls):
        """Return the currently active session, or None."""
        return cls.objects.filter(is_active=True).first()
 
 
class AttendanceAttempt(models.Model):
    """
    One row per submission attempt (successful or not).
    """
    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name='attempts',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='attendance_attempts',
    )
    code_entered = models.CharField(max_length=6)
    submitted_at = models.DateTimeField(auto_now_add=True)
    # success = True if code_entered.upper() == session.code AND session was active at submission time
    success = models.BooleanField(default=False)
 
    class Meta:
        ordering = ['-submitted_at']
 
    def __str__(self):
        result = 'OK' if self.success else 'FAIL'
        return f"{self.user} → {self.code_entered} [{result}]"