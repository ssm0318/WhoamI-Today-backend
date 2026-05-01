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
