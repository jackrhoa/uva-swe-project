from django.contrib import admin
from .models import UserProfile, Team

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'team']
    list_editable = ['role', 'team']

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']        # 'id' is first column
    list_editable = ['name']             # now 'name' is editable
    list_display_links = ['id'] 