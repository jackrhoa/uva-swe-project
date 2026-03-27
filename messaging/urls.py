from django.urls import path
from . import views

urlpatterns = [
    path('', views.message_list, name='message_list'),
    path('start/', views.start_conversation, name='start_conversation'),
    path('send/<int:conversation_id>/', views.send_message, name='send_message'),
    path('delete/<int:message_id>/', views.delete_message, name='delete_message'),
    path('mark-read/<int:conversation_id>/', views.mark_read, name='mark_read'),
    path('team/', views.team_chat, name='team_chat'),
    path('team/send/<int:team_conversation_id>/', views.send_team_message, name='send_team_message'),
]