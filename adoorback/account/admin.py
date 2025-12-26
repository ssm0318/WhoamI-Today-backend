from django.contrib import admin
from django.contrib.auth import get_user_model

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from account.models import FriendRequest, Interest, Persona

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


admin.site.register(User, UserAdmin)
admin.site.register(FriendRequest, FriendRequestAdmin)
admin.site.register(Interest, InterestAdmin)
admin.site.register(Persona, PersonaAdmin)
