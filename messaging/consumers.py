import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return
        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_message",
            "message": event["message"],
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_deleted",
            "message_id": event["message_id"],
            "conversation_id": event["conversation_id"],
        }))


class TeamChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return
        self.team_id = self.scope["url_route"]["kwargs"]["team_id"]
        self.group_name = f"team_{self.team_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def team_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_team_message",
            "message": event["message"],
        }))

    async def team_message_deleted(self, event):
        await self.send(text_data=json.dumps({
            "type": "team_message_deleted",
            "message_id": event["message_id"],
        }))


class AttendanceConsumer(AsyncWebsocketConsumer):
    GROUP = "attendance"

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return
        await self.channel_layer.group_add(self.GROUP, self.channel_name)
        await self.accept()
        # Send initial state so the badge is correct on page load
        from users.models import AttendanceSession
        session = await database_sync_to_async(AttendanceSession.get_active)()
        if session:
            checked_off = await database_sync_to_async(
                lambda: session.attempts.filter(user=self.user, success=True).exists()
            )()
            await self.send(text_data=json.dumps({
                "type": "session_started",
                "checked_off": checked_off,
            }))
        else:
            await self.send(text_data=json.dumps({"type": "session_ended"}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.GROUP, self.channel_name)

    async def attendance_session_started(self, event):
        await self.send(text_data=json.dumps({"type": "session_started", "checked_off": False}))

    async def attendance_session_ended(self, event):
        await self.send(text_data=json.dumps({"type": "session_ended"}))

    async def attendance_member_checked_in(self, event):
        await self.send(text_data=json.dumps({
            "type": "member_checked_in",
            "member": event["member"],
        }))
