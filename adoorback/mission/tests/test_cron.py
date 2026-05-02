import datetime

from django.test import TestCase

from mission.algorithms.data_crawler import select_daily_missions
from mission.models import Mission


class SelectDailyMissionsTest(TestCase):
    def test_picks_random_when_unscheduled(self):
        for i in range(5):
            Mission.objects.create(
                slug=f'm_cron_{i}',
                prompt_en=f'Prompt {i}',
                prompt_ko='',
                type='text',
            )
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        select_daily_missions(set_date=tomorrow)
        picked = Mission.objects.filter(selected=True)
        self.assertEqual(picked.count(), 1)
        self.assertIn(tomorrow, picked.first().selected_dates)

    def test_skips_when_already_scheduled(self):
        scheduled_date = datetime.date(2026, 5, 3)
        Mission.objects.create(
            slug='m_curated_w1_d1',
            prompt_en='Curated',
            prompt_ko='',
            type='text',
            selected_dates=[scheduled_date],
            selected=True,
        )
        for i in range(3):
            Mission.objects.create(
                slug=f'm_pool_{i}',
                prompt_en=f'P {i}',
                prompt_ko='',
                type='text',
            )
        select_daily_missions(set_date=scheduled_date)
        # No additional mission should have been picked for this date.
        on_date = Mission.objects.filter(selected_dates__contains=[scheduled_date])
        self.assertEqual(on_date.count(), 1)
        self.assertEqual(on_date.first().slug, 'm_curated_w1_d1')
        # No general-pool mission was selected.
        self.assertEqual(Mission.objects.filter(slug__startswith='m_pool_', selected=True).count(), 0)

    def test_pool_exhaustion_resets_only_unscheduled(self):
        # 3 unscheduled missions (selected=True with empty selected_dates — the
        # unnatural state the plan's pool-exhaustion narrowing targets).
        for i in range(3):
            Mission.objects.create(
                slug=f'm_unscheduled_{i}',
                prompt_en=f'U {i}',
                prompt_ko='',
                type='text',
                selected_dates=[],
                selected=True,
            )
        # 1 scheduled (curated) mission, selected=True with non-empty selected_dates.
        scheduled_old = datetime.date(2026, 5, 3)
        Mission.objects.create(
            slug='m_curated_only',
            prompt_en='Curated',
            prompt_ko='',
            type='text',
            selected_dates=[scheduled_old],
            selected=True,
        )
        # Pool-exhaustion path: no selected=False missions exist, so the cron
        # falls into the reset branch.
        target = datetime.date.today() + datetime.timedelta(days=1)
        select_daily_missions(set_date=target)

        # Curated mission: still selected=True, untouched.
        curated = Mission.objects.get(slug='m_curated_only')
        self.assertTrue(curated.selected)
        self.assertEqual(curated.selected_dates, [scheduled_old])

        # One of the three unscheduled missions should have been picked.
        picked_today = Mission.objects.filter(selected_dates__contains=[target])
        self.assertEqual(picked_today.count(), 1)
        self.assertTrue(picked_today.first().slug.startswith('m_unscheduled_'))

    def test_default_set_date_is_tomorrow(self):
        Mission.objects.create(
            slug='m_default',
            prompt_en='Default',
            prompt_ko='',
            type='text',
        )
        select_daily_missions()
        m = Mission.objects.get(slug='m_default')
        self.assertEqual(len(m.selected_dates), 1)
        self.assertEqual(m.selected_dates[0], datetime.date.today() + datetime.timedelta(days=1))
