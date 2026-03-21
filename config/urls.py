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
    path('manage-roles/', views.manage_roles, name='manage_roles'),
    path('change-role/<int:user_id>/', views.change_role, name='change_role'),
    path('manage-teams/', views.manage_teams, name='manage_teams'),
    path('change-team/<int:user_id>/', views.change_team, name='change_team'),
    path('add-team/', views.add_team, name='add_team'),
    path('delete-team/<int:team_id>/', views.delete_team, name='delete_team'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('messages/', include('messaging.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)