import asyncio
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

PING_INTERVAL = 30
PING_TIMEOUT = 10


class _PingMixin:
    async def _start_keepalive(self):
        self._pong_received = True
        self._ping_task = asyncio.ensure_future(self._keepalive())

    async def _stop_keepalive(self):
        if hasattr(self, "_ping_task"):
            self._ping_task.cancel()

    async def _keepalive(self):
        while True:
            await asyncio.sleep(PING_INTERVAL)
            self._pong_received = False
            await self.send(text_data=json.dumps({"type": "ping"}))
            await asyncio.sleep(PING_TIMEOUT)
            if not self._pong_received:
                await self.close()
                return

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get("type") == "pong":
            self._pong_received = True


class ChatConsumer(_PingMixin, AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return
        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self._start_keepalive()

    async def disconnect(self, close_code):
        await self._stop_keepalive()
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


class TeamChatConsumer(_PingMixin, AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return
        self.team_id = self.scope["url_route"]["kwargs"]["team_id"]
        self.group_name = f"team_{self.team_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self._start_keepalive()

    async def disconnect(self, close_code):
        await self._stop_keepalive()
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


class AttendanceConsumer(_PingMixin, AsyncWebsocketConsumer):
    GROUP = "attendance"

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return
        await self.channel_layer.group_add(self.GROUP, self.channel_name)
        await self.accept()
        await self._start_keepalive()
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
        await self._stop_keepalive()
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
