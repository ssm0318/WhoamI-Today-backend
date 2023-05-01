from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Notification


class NotificationResource(resources.ModelResource):

    class Meta:
        model = Notification


class NotificationAdmin(ImportExportModelAdmin):
    resource_class = NotificationResource


admin.site.register(Notification, NotificationAdmin)
