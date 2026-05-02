from rest_framework import serializers

from browse_mode.models import (
    BrowseModePickEvent,
    BrowseModePreset,
    BrowseModeWishlistEntry,
)


# Tab keys the frontend lets the user toggle. `my` (profile) and `questions`
# live in the hamburger menu / feature-flag gate respectively — they're never
# user-toggleable, so we don't accept them from the client. Presets
# referencing other unknown keys are rejected at write-time.
ALLOWED_TAB_KEYS = {
    'friends',
    'update',
    'share',
    'discover',
    'chats',
}

ALLOWED_FILTER_KEYS = {
    'friends_close_only',
    'chats_close_only',
}

ALLOWED_SECTION_KEYS = {
    'hide_synthetic_discover_cards',
    'hide_ping_buttons',
    'hide_new_post_badge',
}

class BrowseModePresetSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrowseModePreset
        fields = [
            'id',
            'name',
            'description',
            'config',
            'default_battery',
            'last_used_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'last_used_at', 'created_at', 'updated_at']

    def validate_name(self, value):
        trimmed = (value or '').strip()
        if not trimmed:
            raise serializers.ValidationError("Preset name must not be empty.")
        return trimmed

    def validate_description(self, value):
        # Empty descriptions stay empty — the frontend falls back to a tab-list
        # summary in that case. Anything else gets trimmed and length-capped.
        trimmed = (value or '').strip()
        if len(trimmed) > 30:
            raise serializers.ValidationError("Description must be 30 characters or fewer.")
        return trimmed

    def validate_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("config must be an object.")

        tabs = value.get('tabs', [])
        if not isinstance(tabs, list) or any(not isinstance(t, str) for t in tabs):
            raise serializers.ValidationError("config.tabs must be a list of strings.")
        unknown_tabs = set(tabs) - ALLOWED_TAB_KEYS
        if unknown_tabs:
            raise serializers.ValidationError(
                f"Unknown tab keys: {sorted(unknown_tabs)}"
            )
        if not tabs:
            raise serializers.ValidationError(
                "config.tabs must include at least one tab — otherwise the user "
                "would be locked out of the app."
            )

        # Boolean-valued sections.
        for section, allowed in (
            ('filters', ALLOWED_FILTER_KEYS),
            ('sections', ALLOWED_SECTION_KEYS),
        ):
            section_value = value.get(section, {})
            if not isinstance(section_value, dict):
                raise serializers.ValidationError(f"config.{section} must be an object.")
            unknown_keys = set(section_value.keys()) - allowed
            if unknown_keys:
                raise serializers.ValidationError(
                    f"Unknown {section} keys: {sorted(unknown_keys)}"
                )
            for key, val in section_value.items():
                if not isinstance(val, bool):
                    raise serializers.ValidationError(
                        f"config.{section}.{key} must be a boolean."
                    )

        # Optional per-tab time limits — a Digital-Detox-style "show these
        # for N minutes then fade them out" map. Keys are tab keys, values
        # are positive integer minutes (1-1440). Tabs missing from the map
        # are persistent. Frontend honours this via useBrowseModeTabDurations.
        cleaned = {
            'tabs': list(tabs),
            'filters': dict(value.get('filters', {})),
            'sections': dict(value.get('sections', {})),
        }
        tab_durations = value.get('tab_durations')
        if tab_durations is not None:
            if not isinstance(tab_durations, dict):
                raise serializers.ValidationError(
                    "config.tab_durations must be an object."
                )
            unknown = set(tab_durations.keys()) - ALLOWED_TAB_KEYS
            if unknown:
                raise serializers.ValidationError(
                    f"Unknown tab_durations keys: {sorted(unknown)}"
                )
            for tab, minutes in tab_durations.items():
                if not isinstance(minutes, int) or isinstance(minutes, bool):
                    raise serializers.ValidationError(
                        f"config.tab_durations.{tab} must be an integer."
                    )
                if minutes < 1 or minutes > 24 * 60:
                    raise serializers.ValidationError(
                        f"config.tab_durations.{tab} must be between 1 and 1440."
                    )
            cleaned['tab_durations'] = dict(tab_durations)
        return cleaned


class BrowseModeWishlistEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = BrowseModeWishlistEntry
        fields = ['id', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_content(self, value):
        trimmed = (value or '').strip()
        if not trimmed:
            raise serializers.ValidationError("Wishlist entry must not be empty.")
        if len(trimmed) > 2000:
            raise serializers.ValidationError("Wishlist entry must be 2000 characters or fewer.")
        return trimmed


class BrowseModePickEventSerializer(serializers.ModelSerializer):
    # `preset_id` is the natural input from the frontend; map it onto the
    # FK without forcing the client to know DRF's PrimaryKeyRelatedField
    # conventions. Validation enforces ownership: a user can't log a pick
    # against another user's preset.
    preset_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = BrowseModePickEvent
        fields = ['id', 'kind', 'built_in_id', 'preset_id', 'preset', 'created_at']
        read_only_fields = ['id', 'preset', 'created_at']

    def validate(self, attrs):
        kind = attrs.get('kind')
        built_in_id = attrs.get('built_in_id')
        preset_id = attrs.get('preset_id')

        if kind == 'built_in':
            if not built_in_id:
                raise serializers.ValidationError(
                    {'built_in_id': 'Required when kind=built_in.'}
                )
            if preset_id is not None:
                raise serializers.ValidationError(
                    {'preset_id': 'Must be null when kind=built_in.'}
                )
        elif kind == 'custom':
            if preset_id is None:
                raise serializers.ValidationError(
                    {'preset_id': 'Required when kind=custom.'}
                )
            if built_in_id:
                raise serializers.ValidationError(
                    {'built_in_id': 'Must be null when kind=custom.'}
                )
        elif kind == 'apply_without_saving':
            if built_in_id or preset_id is not None:
                raise serializers.ValidationError(
                    'kind=apply_without_saving cannot carry built_in_id or preset_id.'
                )
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        preset_id = validated_data.pop('preset_id', None)
        preset = None
        if preset_id is not None:
            try:
                preset = BrowseModePreset.objects.get(pk=preset_id, user=request.user)
            except BrowseModePreset.DoesNotExist:
                raise serializers.ValidationError(
                    {'preset_id': 'Preset not found or not owned by user.'}
                )
        return BrowseModePickEvent.objects.create(
            user=request.user,
            preset=preset,
            **validated_data,
        )
