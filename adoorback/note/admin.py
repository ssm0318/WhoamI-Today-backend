from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Note


class NoteResource(resources.ModelResource):

    class Meta:
        model = Note


class NoteAdmin(ImportExportModelAdmin):
    resource_class = NoteResource


admin.site.register(Note, NoteAdmin)
from django.contrib import admin

# Register your models here.
