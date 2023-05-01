from django.contrib import admin
from django.contrib.auth import get_user_model

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from account.models import FriendRequest

User = get_user_model()


class FriendRequestResource(resources.ModelResource):

    class Meta:
        model = FriendRequest


class FriendRequestAdmin(ImportExportModelAdmin):
    resource_class = FriendRequestResource


class UserResource(resources.ModelResource):

    class Meta:
        model = User


class UserAdmin(ImportExportModelAdmin):
    resource_class = UserResource


admin.site.register(User, UserAdmin)
admin.site.register(FriendRequest, FriendRequestAdmin)
