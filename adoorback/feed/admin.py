from django.contrib import admin

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Article, Response, Question, ResponseRequest


class ArticleResource(resources.ModelResource):

    class Meta:
        model = Article


class ResponseResource(resources.ModelResource):

    class Meta:
        model = Response


class QuestionResource(resources.ModelResource):

    class Meta:
        model = Question


class ResponseRequestResource(resources.ModelResource):

    class Meta:
        model = ResponseRequest


class ArticleAdmin(ImportExportModelAdmin):
    resource_class = ArticleResource


class ResponseAdmin(ImportExportModelAdmin):
    resource_class = ResponseResource


class QuestionAdmin(ImportExportModelAdmin):
    resource_class = QuestionResource


class ResponseRequestAdmin(ImportExportModelAdmin):
    resource_class = ResponseRequestResource


admin.site.register(Article, ArticleAdmin)
admin.site.register(Response, ResponseAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(ResponseRequest, ResponseRequestAdmin)
