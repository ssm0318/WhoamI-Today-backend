from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from mission.models import Mission


User = get_user_model()


def _user_today_for_default_tz():
    """Mirrors MissionManager.daily_missions() date logic."""
    tz = ZoneInfo('America/Los_Angeles')
    return (timezone.now().astimezone(tz) - timedelta(hours=8)).date()


class DailyMissionsApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='m_api_user', password='x')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_returns_today_when_scheduled(self):
        today = _user_today_for_default_tz()
        Mission.objects.create(
            slug='m_api_today',
            prompt_en='Today',
            prompt_ko='오늘',
            type='text',
            selected_dates=[today],
            selected=True,
        )
        resp = self.client.get('/api/missions/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]['slug'], 'm_api_today')

    def test_returns_empty_when_no_match(self):
        # Mission exists but not for today.
        Mission.objects.create(
            slug='m_api_other',
            prompt_en='Other',
            prompt_ko='',
            type='text',
            selected_dates=[_user_today_for_default_tz() + timedelta(days=30)],
            selected=True,
        )
        resp = self.client.get('/api/missions/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_serializer_excludes_internal_fields(self):
        today = _user_today_for_default_tz()
        Mission.objects.create(
            slug='m_api_fields',
            prompt_en='Fields',
            prompt_ko='',
            type='text',
            selected_dates=[today],
            selected=True,
        )
        resp = self.client.get('/api/missions/')
        body = resp.json()
        self.assertEqual(len(body), 1)
        keys = set(body[0].keys())
        self.assertEqual(keys, {'id', 'slug', 'prompt_en', 'prompt_ko', 'type'})

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get('/api/missions/')
        self.assertIn(resp.status_code, (401, 403))
