from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from like.models import Like


class LikeResource(resources.ModelResource):

    class Meta:
        model = Like


class LikeAdmin(ImportExportModelAdmin):
    resource_class = LikeResource


admin.site.register(Like, LikeAdmin)
