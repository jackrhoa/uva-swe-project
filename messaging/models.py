from django.db import models
from django.contrib.auth.models import User


class Conversation(models.Model):
    user1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conversations_as_user1'
    )
    user2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conversations_as_user2'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user1', 'user2')

    def __str__(self):
        return f"{self.user1.username} & {self.user2.username}"

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
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to='message_attachments/',
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message from {self.sender.username} at {self.created_at}"
    