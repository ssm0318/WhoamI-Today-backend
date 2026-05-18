from django.contrib import admin

from surveys.models import (
    ScheduledSurvey, Survey, SurveyAnswer, SurveyOption, SurveyQuestion,
    SurveyResponse,
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


@admin.register(ScheduledSurvey)
class ScheduledSurveyAdmin(admin.ModelAdmin):
    list_display = (
        'cadence', 'sequence_index', 'sidebar_order', 'survey',
        'window_start', 'window_end', 'allow_late',
    )
    list_filter = ('cadence', 'allow_late')
    search_fields = ('survey__slug',)
    ordering = ('window_start', 'sidebar_order', 'sequence_index')


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('user', 'survey', 'submitted_at')
    list_filter = ('survey',)
    search_fields = ('user__username',)
    readonly_fields = ('submitted_at',)


admin.site.register(SurveyAnswer)
