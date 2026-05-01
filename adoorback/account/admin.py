from django.contrib import admin
from django.contrib.auth import get_user_model

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from account.models import FriendRequest, Interest, Persona, VersionSwapRequest

User = get_user_model()


class InterestResource(resources.ModelResource):

    class Meta:
        model = Interest


class InterestAdmin(ImportExportModelAdmin):
    resource_class = InterestResource


class PersonaResource(resources.ModelResource):

    class Meta:
        model = Persona


class PersonaAdmin(ImportExportModelAdmin):
    resource_class = PersonaResource


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


class VersionSwapRequestResource(resources.ModelResource):

    class Meta:
        model = VersionSwapRequest


class VersionSwapRequestAdmin(ImportExportModelAdmin):
    resource_class = VersionSwapRequestResource
    list_display = ['user', 'from_version', 'to_version', 'status', 'created_at', 'reason']
    list_filter = ['status', 'from_version', 'to_version']
    search_fields = ['user__username']
    readonly_fields = ['from_version', 'to_version', 'reason']


admin.site.register(User, UserAdmin)
admin.site.register(FriendRequest, FriendRequestAdmin)
admin.site.register(Interest, InterestAdmin)
admin.site.register(Persona, PersonaAdmin)
admin.site.register(VersionSwapRequest, VersionSwapRequestAdmin)
