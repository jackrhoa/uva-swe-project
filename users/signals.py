from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(pre_save, sender=UserProfile)
def capture_old_team(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_team_id = UserProfile.objects.get(pk=instance.pk).team_id
        except UserProfile.DoesNotExist:
            instance._old_team_id = None
    else:
        instance._old_team_id = None


@receiver(post_save, sender=UserProfile)
def auto_mark_announcements_on_team_change(sender, instance, created, **kwargs):
    old_team_id = getattr(instance, '_old_team_id', None)
    if old_team_id != instance.team_id:
        from .models import auto_mark_old_announcements_read
        auto_mark_old_announcements_read(instance.user)