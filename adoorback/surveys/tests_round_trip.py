"""End-to-end test: load the example YAML fixture, exercise the SurveyIndex
API. Verifies the full pipeline (YAML → DB → bucketing → serializer → response).

Per plan: ScheduledSurvey rows are created directly in setUpTestData (path c)
rather than running the data migration. This isolates "the loader works" from
"the schedule migration works" — both are tested separately.
"""
import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from surveys.models import (
    CADENCE_ANYTIME, CADENCE_BIWEEKLY, CADENCE_DAILY, CADENCE_ENDPOINT,
    CADENCE_WEEKLY, ScheduledSurvey, Survey,
)


FIXTURE_PATH = Path(__file__).resolve().parent / 'fixtures' / 'study_2026q2.example.yaml'


class SurveyIndexRoundTripTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. Load the example YAML — populates Survey + SurveyQuestion (+ SurveyOption) rows.
        call_command('load_surveys', str(FIXTURE_PATH))

        # 2. Create ScheduledSurvey rows directly. We don't invoke seed_schedule
        #    from the migration because that hardcodes May 2026 dates; for a
        #    round-trip API test we want dates relative to "today".
        today = datetime.date.today()
        cls.today = today

        def schedule(slug, cadence, seq, ws, we, allow_late):
            ScheduledSurvey.objects.create(
                survey=Survey.objects.get(slug=slug),
                cadence=cadence, sequence_index=seq,
                window_start=ws, window_end=we, allow_late=allow_late,
            )

        # Daily for today (available_now)
        schedule('daily_base', CADENCE_DAILY, 1,
                 today, today, allow_late=False)

        # Weekly that's late (window_end was yesterday, allow_late=True)
        schedule('week1_reflection', CADENCE_WEEKLY, 1,
                 today - datetime.timedelta(days=8),
                 today - datetime.timedelta(days=1),
                 allow_late=True)

        # Pre-study biweekly that's late
        schedule('pre_study', CADENCE_BIWEEKLY, 1,
                 today - datetime.timedelta(days=2),
                 today - datetime.timedelta(days=2),
                 allow_late=True)

        # Anytime, currently open
        schedule('anytime_reflection', CADENCE_ANYTIME, 1,
                 today - datetime.timedelta(days=3),
                 today + datetime.timedelta(days=10),
                 allow_late=True)

        # Endpoint, opens today, no upper bound
        schedule('study_endpoint', CADENCE_ENDPOINT, 1,
                 today, None, allow_late=True)

        # An already-expired daily that should be hidden
        schedule('week2_reflection', CADENCE_DAILY, 2,
                 today - datetime.timedelta(days=5),
                 today - datetime.timedelta(days=5),
                 allow_late=False)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='adoor_test', email='t@x.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_example_yaml_loaded_required_slugs(self):
        for slug in (
            'daily_base', 'pre_study', 'mid_study', 'post_study',
            'week1_reflection', 'week2_reflection', 'week3_reflection', 'week4_reflection',
            'anytime_reflection', 'study_endpoint',
        ):
            self.assertTrue(Survey.objects.filter(slug=slug).exists(), f'missing: {slug}')

    def test_index_endpoint_returns_three_buckets(self):
        r = self.client.get('/api/surveys/index/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn('available_now', body)
        self.assertIn('late_but_accepted', body)
        self.assertIn('completed', body)

    def test_index_buckets_match_expected_layout(self):
        """Without any responses, the buckets should split exactly along the
        scheduling rules — and the expired daily should be in NO bucket."""
        r = self.client.get('/api/surveys/index/')
        body = r.json()

        avail_slugs = {e['survey']['slug'] for e in body['available_now']}
        late_slugs = {e['survey']['slug'] for e in body['late_but_accepted']}
        completed_slugs = {e['survey']['slug'] for e in body['completed']}

        # Daily for today, anytime, and endpoint are all in available_now.
        self.assertIn('daily_base', avail_slugs)
        self.assertIn('anytime_reflection', avail_slugs)
        self.assertIn('study_endpoint', avail_slugs)

        # Past weekly + biweekly with allow_late=True land in late_but_accepted.
        self.assertIn('week1_reflection', late_slugs)
        self.assertIn('pre_study', late_slugs)

        # No responses yet → completed empty.
        self.assertEqual(completed_slugs, set())

        # Expired daily (allow_late=False, window_end < today) is hidden everywhere.
        self.assertNotIn('week2_reflection', avail_slugs)
        self.assertNotIn('week2_reflection', late_slugs)
        self.assertNotIn('week2_reflection', completed_slugs)

    def test_index_entry_redirect_url_points_to_answer_when_unanswered(self):
        r = self.client.get('/api/surveys/index/')
        body = r.json()
        for entry in body['available_now'] + body['late_but_accepted']:
            self.assertEqual(entry['redirect_url'], f"/surveys/{entry['survey']['slug']}/answer")
