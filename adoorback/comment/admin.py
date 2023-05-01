from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from comment.models import Comment


class CommentResource(resources.ModelResource):

    class Meta:
        model = Comment


class CommentAdmin(ImportExportModelAdmin):
    resource_class = CommentResource


admin.site.register(Comment, CommentAdmin)
