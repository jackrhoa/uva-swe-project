from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from users import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', views.home, name='home'),
    path('exec/', views.exec_dashboard, name='exec_dashboard'),
    path('member/', views.member_dashboard, name='member_dashboard'),
    path('profile/', views.profile, name='profile'),
    path('tasks/', views.tasks, name='tasks'),
    path('manage-roles/', views.manage_roles, name='manage_roles'),
    path('change-role/<int:user_id>/', views.change_role, name='change_role'),
    path('manage-teams/', views.manage_teams, name='manage_teams'),
    path('change-team/<int:user_id>/', views.change_team, name='change_team'),
    path('add-team/', views.add_team, name='add_team'),
    path('delete-team/<int:team_id>/', views.delete_team, name='delete_team'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    path('messages/', include('messaging.urls')),
    path('tasks/add/', views.add_task, name='add_task'),
    path('tasks/<int:task_id>/remove/', views.remove_task, name='remove_task'),
    path('tasks/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('announcements/', views.announcement_history, name='announcement_history'),
    path('attendance/generate/', views.attendance_generate, name='attendance_generate'),
    path('attendance/end/', views.attendance_end, name='attendance_end'),
    path('attendance/submit/', views.attendance_submit, name='attendance_submit'),
    path('attendance/status/', views.attendance_status, name='attendance_status'),
    path('attendance/records/', views.attendance_records, name='attendance_records'),
    path('attendance/records/page/', views.attendance_records_page, name='attendance_records_page'),
    path('attendance/records/csv/', views.attendance_records_csv, name='attendance_records_csv'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)