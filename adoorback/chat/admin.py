from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from chat.models import OnboardingScreenshot


@admin.register(OnboardingScreenshot)
class OnboardingScreenshotAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'status', 'thumbnail', 'created_at', 'reviewed_by')
    list_filter = ('status', 'version', 'kind')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'version', 'kind', 'message', 'created_at')
    actions = ['approve_selected', 'reject_selected']

    def thumbnail(self, obj):
        if obj.message and obj.message.image:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:80px;"/></a>',
                obj.message.image.url,
            )
        return '—'
    thumbnail.short_description = 'Screenshot'

    def approve_selected(self, request, queryset):
        n = queryset.update(
            status='approved',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"Approved {n} screenshots.")
    approve_selected.short_description = 'Approve selected'

    def reject_selected(self, request, queryset):
        n = queryset.update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            rejection_reason='(bulk reject — use detail page for reason)',
        )
        self.message_user(request, f"Rejected {n} screenshots.")
    reject_selected.short_description = 'Reject selected (no reason — use detail for reason)'
