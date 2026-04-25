from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/chat/$", consumers.ChatConsumer.as_asgi()),
    re_path(r"ws/team/(?P<team_id>\d+)/$", consumers.TeamChatConsumer.as_asgi()),
    re_path(r"ws/attendance/$", consumers.AttendanceConsumer.as_asgi()),
]
