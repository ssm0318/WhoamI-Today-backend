from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel


MISSION_TYPE_CHOICES = [
    ('song', 'Song'),
    ('question', 'Question'),
    ('text', 'Text'),
    ('compliment', 'Compliment'),
]


class MissionManager(models.Manager):
    def daily_missions(self, user):
        try:
            tz = ZoneInfo(user.timezone)
        except (ZoneInfoNotFoundError, AttributeError):
            tz = ZoneInfo('America/Los_Angeles')
        user_today = (timezone.now().astimezone(tz) - timedelta(hours=8)).date()
        return self.filter(selected_dates__contains=[user_today])


class Mission(AdoorTimestampedModel):
    """Mission of the Day. Long-term content with random daily rotation,
    plus 43-day curated study schedule overlay (2026-04-30 → 2026-06-11).
    """
    slug = models.SlugField(max_length=64, unique=True)
    prompt_en = models.TextField()
    prompt_ko = models.TextField(blank=True, default='')
    type = models.CharField(max_length=20, choices=MISSION_TYPE_CHOICES)
    selected_dates = ArrayField(models.DateField(), blank=True, default=list)
    selected = models.BooleanField(default=False)

    objects = MissionManager()

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'[{self.slug}] {self.prompt_en[:50]}'
