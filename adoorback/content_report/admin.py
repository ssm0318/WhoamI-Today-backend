
from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from content_report.models import ContentReport


class ContentReportResource(resources.ModelResource):

    class Meta:
        model = ContentReport


class ContentReportAdmin(ImportExportModelAdmin):
    resource_class = ContentReportResource


admin.site.register(ContentReport, ContentReportAdmin)
