"""Add Mission.share_results and Mission.cta_url, and set May 5 to wit_bot CTA.

Schema additions:
- share_results: bool, default True. When False, the digest's
  yesterday_mission card is suppressed the next day. Existing missions keep
  current behavior (default True).
- cta_url: CharField(max_length=200, blank=True, default=''). When non-empty,
  the Discover digest mission-card swaps "View mission posts" for a custom
  link (e.g. "/users/wit_bot/chat"). Does NOT affect the Share tab "Do it"
  button — that keeps its existing type-based routing.

Data:
- Set the May 5, 2026 mission's cta_url to '/users/wit_bot/chat'. May 5 is
  the "Talk to wit_bot to finish onboarding" prompt (set in 0004); pairing
  that prompt with the wit_bot deep-link makes the next-day digest card open
  the wit_bot chat.

Defaults are supplied at the field level → safe single-step add (no
NOT NULL crash on existing rows).
"""
from django.db import migrations, models


MAY_5_2026_DAY_OF_YEAR = 125
WIT_BOT_CHAT_URL = '/users/wit_bot/chat'


def set_may_5_cta(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return
    target = missions[MAY_5_2026_DAY_OF_YEAR % len(missions)]
    target.cta_url = WIT_BOT_CHAT_URL
    target.save(update_fields=['cta_url'])


def clear_may_5_cta(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return
    target = missions[MAY_5_2026_DAY_OF_YEAR % len(missions)]
    target.cta_url = ''
    target.save(update_fields=['cta_url'])


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0004_may_4_7_mission_hotfix'),
    ]

    operations = [
        migrations.AddField(
            model_name='mission',
            name='share_results',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='mission',
            name='cta_url',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.RunPython(set_may_5_cta, clear_may_5_cta),
    ]
