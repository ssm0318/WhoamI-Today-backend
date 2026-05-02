from django.contrib.auth import get_user_model
from django.db import models

from adoorback.models import AdoorTimestampedModel
from check_in.models import CheckIn

User = get_user_model()


class BrowseModePreset(AdoorTimestampedModel):
    """A user-saved combination of which tabs / sections / filters they want to
    see while in a given "browse mode" session (printer-preset metaphor).

    Built-in modes (very_social / selectively_social / quiet) live as
    constants on the frontend and are NOT stored here — only user-created
    custom presets are persisted.

    The active mode for the current session is tracked client-side; this
    model only persists the saved presets the user can re-pick later.
    """

    user = models.ForeignKey(
        User,
        related_name='browse_mode_presets',
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=40)
    # Short user-written blurb shown under the preset name on the picker
    # card (e.g. "low-key Tuesdays"). Replaces the auto-generated
    # tab-list summary when set. Capped at 30 chars to keep the picker
    # cards visually consistent — anything longer would wrap awkwardly.
    description = models.CharField(max_length=30, blank=True, default='')
    config = models.JSONField(default=dict)
    # Battery level the frontend should set when the user activates this preset
    # AND has the "Also set my battery" sync toggle on. Null means "no
    # opinion" — the toggle becomes a no-op for this preset.
    default_battery = models.CharField(
        max_length=30,
        choices=CheckIn.SOCIAL_BATTERY_CHOICES,
        null=True,
        blank=True,
    )
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'],
                name='unique_browse_mode_preset_per_user',
            ),
        ]
        ordering = ['-last_used_at', '-updated_at']

    def __str__(self):
        return f'{self.user} — {self.name}'


class BrowseModePickEvent(AdoorTimestampedModel):
    """One row per active pick of a browse mode — the analytics ground truth
    for "how often did the user activate a mode, switch, or apply-without-
    saving." Skips / dismisses are NOT recorded; only positive picks.

    Three kinds:
      - `built_in`: one of the frontend constants (very_social /
        selectively_social / quiet). `built_in_id` is set, `preset` is
        null.
      - `custom`: a saved `BrowseModePreset` was activated. `preset` FK
        is set, `built_in_id` is null. `preset` uses SET_NULL on delete
        so historical events survive preset deletion.
      - `apply_without_saving`: the user customized something in the
        sheet and tapped "Apply without saving" — both `built_in_id`
        and `preset` are null.

    `created_at` from `AdoorTimestampedModel` is the pick time; no
    separate `picked_at` field needed.
    """

    KIND_CHOICES = (
        ('built_in', 'built_in'),
        ('custom', 'custom'),
        ('apply_without_saving', 'apply_without_saving'),
    )

    BUILT_IN_ID_CHOICES = (
        ('very_social', 'very_social'),
        ('selectively_social', 'selectively_social'),
        ('quiet', 'quiet'),
    )

    user = models.ForeignKey(
        User,
        related_name='browse_mode_pick_events',
        on_delete=models.CASCADE,
    )
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    built_in_id = models.CharField(
        max_length=40,
        choices=BUILT_IN_ID_CHOICES,
        null=True,
        blank=True,
    )
    preset = models.ForeignKey(
        BrowseModePreset,
        related_name='pick_events',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        target = self.built_in_id or (
            f'preset:{self.preset_id}' if self.preset_id else 'apply_without_saving'
        )
        return f'{self.user} → {target} @ {self.created_at:%Y-%m-%d %H:%M}'


class BrowseModeWishlistEntry(AdoorTimestampedModel):
    """Free-text feature requests the user submits from the customize sheet —
    "what other granular changes would you like?". Read by the team to inform
    future browse-mode capabilities; users never see other users' entries.
    """

    user = models.ForeignKey(
        User,
        related_name='browse_mode_wishlist_entries',
        on_delete=models.CASCADE,
    )
    content = models.TextField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        excerpt = (self.content or '')[:60]
        return f'{self.user}: {excerpt}'
