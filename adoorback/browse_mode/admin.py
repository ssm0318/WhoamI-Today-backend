from django.contrib import admin

from browse_mode.models import BrowseModePreset, BrowseModeWishlistEntry


@admin.register(BrowseModePreset)
class BrowseModePresetAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'last_used_at', 'updated_at')
    list_filter = ('user',)
    search_fields = ('user__username', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BrowseModeWishlistEntry)
class BrowseModeWishlistEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'short_content', 'created_at')
    search_fields = ('user__username', 'content')
    readonly_fields = ('created_at', 'updated_at')

    def short_content(self, obj):
        excerpt = (obj.content or '')[:80]
        return excerpt + ('…' if len(obj.content or '') > 80 else '')
    short_content.short_description = 'content'
