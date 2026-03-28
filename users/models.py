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
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
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
    
class Task(models.Model):
    # Basic info
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Progress tracking
    actions_completed = models.PositiveIntegerField(default=0)
    total_actions = models.PositiveIntegerField(default=1)

    # Priority (higher number = higher priority)
    priority = models.PositiveSmallIntegerField(default=1)
    
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
        help_text='Users assigned to this task. Leave empty for "everyone on the team".'
    )
    active_users = models.ManyToManyField(
        User,
        blank=True,
        related_name='active_tasks',
        help_text='Users currently working on this task.'
    )

    # created_at = models.DateTimeField(auto_now_add=True)
     # updated_at = models.DateTimeField(auto_now=True)

    def is_completed(self):
        """Return True if all actions are completed."""
        return self.actions_completed >= self.total_actions

    def display_assigned(self):
        """
        Return a list of assigned users, or "Team" if assigned_to is empty.
        """
        if self.assigned_to.exists():
            return ", ".join([user.username for user in self.assigned_to.all()])
        return f"Everyone in {self.team.name}"

    def __str__(self):
        return f"{self.name} ({self.team.name}) - Priority {self.priority}"