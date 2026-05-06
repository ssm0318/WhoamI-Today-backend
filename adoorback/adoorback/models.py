from django.db import models
from django.core.validators import MinLengthValidator


class AdoorTimestampedModel(models.Model):
    class Meta:
        abstract = True

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)


class AdoorModel(AdoorTimestampedModel):
    class Meta:
        abstract = True

    content = models.TextField(validators=[MinLengthValidator(1, "content length must be greater than 1")])

    def __str__(self):
        return self.content


class Mission(AdoorTimestampedModel):
    MISSION_TYPE_CHOICES = [
        ('song', 'Song'),
        ('question', 'Question'),
        ('text', 'Text'),
        ('compliment', 'Compliment'),
    ]

    prompt = models.TextField()
    type = models.CharField(max_length=20, choices=MISSION_TYPE_CHOICES)
    # When False, the discover digest hides the yesterday_mission card the
    # next day (e.g. for chat-based missions where there are no posts to share).
    share_results = models.BooleanField(default=True)
    # Optional override link surfaced on the Discover digest mission-card.
    # Empty string = default "View mission posts" → /missions/<id>?discover=true.
    # Non-empty = "Take me to wit_bot" (or similar) → cta_url verbatim.
    # Does NOT affect the Share tab "Do it" button.
    cta_url = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.prompt
