from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from reaction.models import Reaction


class ReactionResource(resources.ModelResource):

    class Meta:
        model = Reaction


class ReactionAdmin(ImportExportModelAdmin):
    resource_class = ReactionResource


admin.site.register(Reaction, ReactionAdmin)
