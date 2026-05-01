from django.contrib import admin

from surveys.models import (
    DailySurvey, Survey, SurveyAnswer, SurveyOption, SurveyQuestion, SurveyResponse,
)


class SurveyOptionInline(admin.TabularInline):
    model = SurveyOption
    extra = 0


class SurveyQuestionInline(admin.StackedInline):
    model = SurveyQuestion
    extra = 0


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ('slug', 'title_en', 'friend_visible', 'results_hidden', 'last_used_date')
    search_fields = ('slug', 'title_en', 'title_ko')
    list_filter = ('friend_visible', 'results_hidden')
    inlines = [SurveyQuestionInline]


@admin.register(SurveyQuestion)
class SurveyQuestionAdmin(admin.ModelAdmin):
    list_display = ('survey', 'order', 'type', 'prompt_en', 'reverse_scored', 'result_hidden')
    list_filter = ('survey', 'type', 'reverse_scored', 'result_hidden')
    inlines = [SurveyOptionInline]


@admin.register(DailySurvey)
class DailySurveyAdmin(admin.ModelAdmin):
    list_display = ('date', 'survey')
    date_hierarchy = 'date'


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('user', 'survey', 'submitted_at')
    list_filter = ('survey',)
    search_fields = ('user__username',)
    readonly_fields = ('submitted_at',)


admin.site.register(SurveyAnswer)
