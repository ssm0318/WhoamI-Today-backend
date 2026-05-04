"""Tests for the biweekly crossover version flip.

Verifies the date logic, the idempotent flip, and that the management
command + cron path produce the same result.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from account.phase_versioning import (
    PHASE_2_START, expected_version_for, flip_users_to_expected_version,
)


User = get_user_model()


class ExpectedVersionForTests(TestCase):
    def test_phase_1_w_first_uses_w(self):
        self.assertEqual(
            expected_version_for('group_w_first', date(2026, 5, 4)),
            'version_w',
        )

    def test_phase_1_q_first_uses_q(self):
        self.assertEqual(
            expected_version_for('group_q_first', date(2026, 5, 4)),
            'version_q',
        )

    def test_phase_2_w_first_crosses_to_q(self):
        self.assertEqual(
            expected_version_for('group_w_first', PHASE_2_START),
            'version_q',
        )

    def test_phase_2_q_first_crosses_to_w(self):
        self.assertEqual(
            expected_version_for('group_q_first', PHASE_2_START),
            'version_w',
        )

    def test_day_before_boundary_still_phase_1(self):
        # Day 14 (May 17) is the last Phase-1 day.
        day14 = date(2026, 5, 17)
        self.assertEqual(expected_version_for('group_w_first', day14), 'version_w')
        self.assertEqual(expected_version_for('group_q_first', day14), 'version_q')

    def test_post_study_keeps_phase_2_assignment(self):
        # After May 31, no revert — users stay on the Phase-2 version.
        post = date(2026, 6, 15)
        self.assertEqual(expected_version_for('group_w_first', post), 'version_q')
        self.assertEqual(expected_version_for('group_q_first', post), 'version_w')

    def test_unknown_group_falls_back_to_w_first_phase_1(self):
        # Solo signups / legacy rows without a group land on the model
        # default. Don't crash; mirror group_w_first behavior.
        self.assertEqual(expected_version_for('', date(2026, 5, 4)), 'version_w')


class FlipUsersToExpectedVersionTests(TestCase):
    def setUp(self):
        # Two participants per group, plus a superuser who must NOT flip.
        self.w1 = User.objects.create(
            username='w1', email='w1@x.com',
            user_group='group_w_first', current_ver='version_w',
        )
        self.w2 = User.objects.create(
            username='w2', email='w2@x.com',
            user_group='group_w_first', current_ver='version_w',
        )
        self.q1 = User.objects.create(
            username='q1', email='q1@x.com',
            user_group='group_q_first', current_ver='version_q',
        )
        self.admin = User.objects.create(
            username='admin', email='admin@x.com',
            user_group='group_w_first', current_ver='version_w',
            is_superuser=True,
        )

    def _refresh_all(self):
        for u in (self.w1, self.w2, self.q1, self.admin):
            u.refresh_from_db()

    def test_phase_1_does_not_flip_correctly_assigned_users(self):
        summary = flip_users_to_expected_version(date(2026, 5, 4))
        self.assertEqual(summary, {'group_w_first': 0, 'group_q_first': 0})
        self._refresh_all()
        self.assertEqual(self.w1.current_ver, 'version_w')
        self.assertEqual(self.q1.current_ver, 'version_q')

    def test_phase_2_flips_both_groups(self):
        summary = flip_users_to_expected_version(PHASE_2_START)
        self.assertEqual(summary, {'group_w_first': 2, 'group_q_first': 1})
        self._refresh_all()
        self.assertEqual(self.w1.current_ver, 'version_q')
        self.assertEqual(self.w2.current_ver, 'version_q')
        self.assertEqual(self.q1.current_ver, 'version_w')

    def test_phase_2_skips_superusers(self):
        flip_users_to_expected_version(PHASE_2_START)
        self.admin.refresh_from_db()
        # Admin in group_w_first stays on version_w — not flipped.
        self.assertEqual(self.admin.current_ver, 'version_w')

    def test_idempotent_second_call_no_ops(self):
        flip_users_to_expected_version(PHASE_2_START)
        summary2 = flip_users_to_expected_version(PHASE_2_START)
        self.assertEqual(summary2, {'group_w_first': 0, 'group_q_first': 0})

    def test_ver_changed_at_set_on_flip(self):
        self.assertIsNone(self.w1.ver_changed_at)
        flip_users_to_expected_version(PHASE_2_START)
        self.w1.refresh_from_db()
        self.assertIsNotNone(self.w1.ver_changed_at)


class FlipCrossoverVersionsCommandTests(TestCase):
    def test_dry_run_does_not_modify_db(self):
        u = User.objects.create(
            username='u', email='u@x.com',
            user_group='group_w_first', current_ver='version_w',
        )
        call_command('flip_crossover_versions', '--today=2026-05-18', '--dry-run')
        u.refresh_from_db()
        self.assertEqual(u.current_ver, 'version_w')

    def test_command_flips_users(self):
        u = User.objects.create(
            username='u', email='u@x.com',
            user_group='group_w_first', current_ver='version_w',
        )
        call_command('flip_crossover_versions', '--today=2026-05-18')
        u.refresh_from_db()
        self.assertEqual(u.current_ver, 'version_q')

    def test_invalid_today_raises(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('flip_crossover_versions', '--today=not-a-date')
