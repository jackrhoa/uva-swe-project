from django.contrib import admin
from django.urls import path, include
from users import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', views.home, name='home'),
    path('manage-roles/', views.manage_roles, name='manage_roles'),
    path('change-role/<int:user_id>/', views.change_role, name='change_role'),
    path('profile/', views.profile, name='profile'),

]