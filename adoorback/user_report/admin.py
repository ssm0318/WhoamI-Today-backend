
from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from user_report.models import UserReport
 

class UserReportResource(resources.ModelResource):

    class Meta:
        model = UserReport


class UserReportAdmin(ImportExportModelAdmin):
    resource_class = UserReportResource


admin.site.register(UserReport, UserReportAdmin)
