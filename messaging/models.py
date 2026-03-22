from django.db import models
from django.contrib.auth.models import User


class Conversation(models.Model):
    user1 = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='conversations_as_user1'
    )
    user2 = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='conversations_as_user2'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        u1 = self.user1.username if self.user1 else 'Deleted User'
        u2 = self.user2.username if self.user2 else 'Deleted User'
        return f"{u1} & {u2}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user1', 'user2'], name='unique_conversation')
        ]

    @staticmethod
    def get_or_create_conversation(user_a, user_b):
        if user_a.id > user_b.id:
            user_a, user_b = user_b, user_a

        conversation, created = Conversation.objects.get_or_create(
            user1=user_a,
            user2=user_b
        )
        return conversation


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    content = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to='message_attachments/',
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        sender = self.sender.username if self.sender else 'Deleted User'
        return f"Message from {sender} at {self.created_at}"
    