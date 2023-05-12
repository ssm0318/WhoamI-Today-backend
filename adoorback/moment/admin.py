from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from moment.models import Moment


class MomentResource(resources.ModelResource):

    class Meta:
        model = Moment


class MomentAdmin(ImportExportModelAdmin):
    resource_class = MomentResource


admin.site.register(Moment, MomentAdmin)
