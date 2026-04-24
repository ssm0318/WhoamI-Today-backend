from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import CheckInComponentEntry


class CheckInComponentEntryResource(resources.ModelResource):

    class Meta:
        model = CheckInComponentEntry


class CheckInComponentEntryAdmin(ImportExportModelAdmin):
    resource_class = CheckInComponentEntryResource
    list_display = (
        'id',
        'owner',
        'component',
        'visibility',
        'is_pinned',
        'pin_visibility',
        'created_at',
        'superseded_at',
    )
    list_filter = ('component', 'visibility', 'is_pinned', 'pin_visibility')
    search_fields = ('owner__username',)
    readonly_fields = ('created_at', 'updated_at')


admin.site.register(CheckInComponentEntry, CheckInComponentEntryAdmin)
