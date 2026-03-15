from django.db import models
from django.contrib.auth.models import User



class Team(models.Model):

    name = models.CharField(max_length=50, unique=True)

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
    
