import json
from datetime import date, datetime, timezone as dt_timezone
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from surveys.audit import (
    build_survey_audit,
    build_survey_user_audit,
    render_audit_html,
    render_survey_priority_audit_html,
    render_survey_user_audit_html,
)
from surveys.models import CADENCE_WEEKLY, ScheduledSurvey, Survey
from surveys.sidebar_order import render_sidebar_order_source


class SurveyAuditTests(SimpleTestCase):
    def test_audit_loads_only_cared_fixture_files_and_expands_questions(self):
        audit = build_survey_audit()

        self.assertEqual(
            set(audit['fixture_files']),
            {'endpoint.yaml', 'weekly_anytime.yaml', 'sotd.yaml', 'daily.yaml', 'pre.yaml'},
        )
        self.assertIn('daily_base', audit['surveys'])
        self.assertIn('mid_study_w', audit['surveys'])
        self.assertIn('week1_reflection', audit['surveys'])
        self.assertIn('study_endpoint', audit['surveys'])

        weekly = audit['surveys']['week1_reflection']
        self.assertEqual(weekly['question_count'], 3)
        self.assertEqual(
            [question['slug'] for question in weekly['questions']],
            ['weekly_ritual_highlight', 'weekly_issue_flag', 'weekly_issue_text'],
        )

    def test_audit_applies_runtime_schedule_overlays(self):
        audit = build_survey_audit()

        by_slug = {}
        for row in audit['schedule_rows']:
            by_slug.setdefault(row['survey_slug'], []).append(row)

        week1 = by_slug['week1_reflection'][0]
        self.assertEqual(week1['window_start'], date(2026, 5, 9).isoformat())
        self.assertEqual(week1['window_end'], date(2026, 5, 10).isoformat())
        self.assertFalse(week1['allow_late'])

        feature_rows = sorted(by_slug['feature_eval_w'], key=lambda row: row['window_start'])
        self.assertEqual(feature_rows[0]['audience'], 'group_w_first')
        self.assertEqual(feature_rows[0]['window_start'], date(2026, 5, 8).isoformat())
        self.assertEqual(feature_rows[0]['window_end'], date(2026, 5, 24).isoformat())
        self.assertTrue(feature_rows[0]['allow_late'])
        self.assertEqual(feature_rows[1]['audience'], 'group_q_first')
        self.assertEqual(feature_rows[1]['window_start'], date(2026, 5, 22).isoformat())
        self.assertEqual(feature_rows[1]['window_end'], date(2026, 5, 24).isoformat())
        self.assertTrue(feature_rows[1]['allow_late'])

        anytime = by_slug['anytime_reflection'][0]
        self.assertIsNone(anytime['window_end'])

        habit = by_slug['habit_platform'][0]
        self.assertEqual(habit['cadence'], 'daily')
        self.assertEqual(habit['window_start'], date(2026, 5, 18).isoformat())
        self.assertEqual(habit['window_end'], date(2026, 5, 18).isoformat())
        self.assertTrue(habit['allow_late'])

    def test_phase_reflection_part_titles_cover_mid_and_post_surveys(self):
        audit = build_survey_audit()

        expected_titles = {
            'mid_study_w': 'Phase 1 reflection: Part 2',
            'mid_study_q': 'Phase 1 reflection: Part 2',
            'goal_comparison_p1': 'Phase 1 reflection: Part 1',
            'post_study_w': 'Phase 2 reflection: Part 2',
            'post_study_q': 'Phase 2 reflection: Part 2',
            'goal_comparison_p2': 'Phase 2 reflection: Part 1',
        }

        for slug, title in expected_titles.items():
            with self.subTest(slug=slug):
                self.assertEqual(audit['surveys'][slug]['title'], title)

    def test_audit_marks_featured_sotd_card_after_reschedules(self):
        audit = build_survey_audit()

        sotd_rows = {
            (row['survey_slug'], row['window_start']): row
            for row in audit['schedule_rows']
            if row['cadence'] == 'daily'
        }

        self.assertEqual(
            sotd_rows[('sotd_d01_honeymoon', date(2026, 5, 5).isoformat())]['featured_surface'],
            'Survey of the Day card',
        )
        self.assertEqual(
            sotd_rows[('sotd_d02_rsds', date(2026, 5, 7).isoformat())]['featured_surface'],
            'Survey of the Day card',
        )
        self.assertEqual(
            sotd_rows[('sotd_d04_iscs_bridge', date(2026, 5, 7).isoformat())]['featured_surface'],
            'Survey index',
        )
        self.assertEqual(
            sotd_rows[('sotd_d15_shi', date(2026, 5, 18).isoformat())]['featured_surface'],
            'Survey of the Day card',
        )
        self.assertEqual(
            sotd_rows[('habit_platform', date(2026, 5, 18).isoformat())]['featured_surface'],
            'Survey index',
        )
        self.assertTrue(sotd_rows[('sotd_d02_rsds', date(2026, 5, 7).isoformat())]['allow_late'])
        self.assertEqual(
            sotd_rows[('sotd_d02_rsds', date(2026, 5, 7).isoformat())]['late_behavior'],
            'Late accepted',
        )

    def test_no_response_sidebar_simulation_matches_app_buckets(self):
        audit = build_survey_audit(
            logical_today=date(2026, 5, 18),
            now_utc=datetime(2026, 5, 18, 20, 0, tzinfo=dt_timezone.utc),
        )

        simulations = {
            simulation['audience']: simulation
            for simulation in audit['sidebar_simulations']
        }
        w_first = simulations['group_w_first']
        q_first = simulations['group_q_first']

        self.assertFalse(w_first['is_paused'])
        self.assertEqual(
            [entry['survey_slug'] for entry in w_first['buckets']['available_now']],
            [
                'phase1_friend_closeness',
                'goal_comparison_p1',
                'mid_study_w',
                'feature_eval_w',
                'habit_platform',
                'daily_base',
                'anytime_reflection',
            ],
        )
        self.assertEqual(
            [entry['survey_slug'] for entry in q_first['buckets']['available_now']],
            [
                'phase1_friend_closeness',
                'goal_comparison_p1',
                'mid_study_q',
                'habit_platform',
                'daily_base',
                'anytime_reflection',
            ],
        )
        w_mid = next(
            entry for entry in w_first['buckets']['available_now']
            if entry['survey_slug'] == 'mid_study_w'
        )
        q_mid = next(
            entry for entry in q_first['buckets']['available_now']
            if entry['survey_slug'] == 'mid_study_q'
        )
        phase1_goal = next(
            entry for entry in w_first['buckets']['available_now']
            if entry['survey_slug'] == 'goal_comparison_p1'
        )
        phase1_closeness = next(
            entry for entry in w_first['buckets']['available_now']
            if entry['survey_slug'] == 'phase1_friend_closeness'
        )
        self.assertEqual(w_mid['survey_title'], 'Phase 1 reflection: Part 2')
        self.assertEqual(q_mid['survey_title'], 'Phase 1 reflection: Part 2')
        self.assertEqual(phase1_goal['survey_title'], 'Phase 1 reflection: Part 1')
        self.assertEqual(
            phase1_closeness['survey_title'],
            'Rate your closeness with each friend (Phase 1)',
        )
        self.assertEqual(w_mid['window_start'], date(2026, 5, 18).isoformat())
        self.assertEqual(w_mid['window_end'], date(2026, 5, 18).isoformat())
        self.assertTrue(w_mid['allow_late'])
        self.assertEqual(q_mid['window_start'], date(2026, 5, 18).isoformat())
        self.assertEqual(q_mid['window_end'], date(2026, 5, 18).isoformat())
        self.assertTrue(q_mid['allow_late'])
        self.assertEqual(phase1_goal['window_start'], date(2026, 5, 18).isoformat())
        self.assertEqual(phase1_goal['window_end'], date(2026, 5, 18).isoformat())
        self.assertTrue(phase1_goal['allow_late'])
        self.assertEqual(w_first['hidden_available_now'], [])
        self.assertEqual(q_first['hidden_available_now'], [])

        w_late_slugs = [entry['survey_slug'] for entry in w_first['buckets']['late_but_accepted']]
        q_late_slugs = [entry['survey_slug'] for entry in q_first['buckets']['late_but_accepted']]
        self.assertNotIn('week1_reflection', w_late_slugs)
        self.assertNotIn('week2_reflection', w_late_slugs)
        self.assertNotIn('pre_study', w_late_slugs)
        self.assertNotIn('mid_study_w', w_late_slugs)
        self.assertNotIn('mid_study_q', w_late_slugs)
        self.assertNotIn('sotd_d15_shi', w_late_slugs)
        self.assertNotIn('pre_study', q_late_slugs)
        self.assertNotIn('mid_study_q', q_late_slugs)
        self.assertNotIn('mid_study_w', q_late_slugs)
        self.assertEqual(w_first['buckets']['completed'], [])

    def test_rendered_html_contains_audit_data(self):
        audit = build_survey_audit(
            logical_today=date(2026, 5, 18),
            now_utc=datetime(2026, 5, 18, 20, 0, tzinfo=dt_timezone.utc),
        )
        html = render_audit_html(audit)

        self.assertIn('WhoamI Survey Audit', html)
        self.assertIn('No-response sidebar simulation', html)
        self.assertIn('Available now', html)
        self.assertIn('Today, how comfortable did you feel sharing on WIT?', html)
        self.assertIn('feature_eval_w', html)

    def test_user_audit_includes_clickable_no_response_surveys_and_full_questions(self):
        audit = build_survey_user_audit(
            logical_today=date(2026, 5, 18),
            now_utc=datetime(2026, 5, 18, 20, 0, tzinfo=dt_timezone.utc),
        )

        w_first = next(
            simulation
            for simulation in audit['sidebar_simulations']
            if simulation['audience'] == 'group_w_first'
        )
        visible_and_hidden_slugs = [
            entry['survey_slug']
            for entry in (
                w_first['buckets']['available_now']
                + w_first['buckets']['late_but_accepted']
                + w_first['hidden_available_now']
            )
        ]

        self.assertNotIn('pre_study', visible_and_hidden_slugs)
        self.assertIn('feature_eval_w', visible_and_hidden_slugs)
        self.assertGreater(audit['summary']['question_count'], 500)
        self.assertGreater(audit['question_type_counts']['single_choice'], 0)
        self.assertGreater(audit['question_type_counts']['multi_choice'], 0)
        self.assertGreater(audit['question_type_counts']['free_text'], 0)

        self.assertTrue(
            any(
                question['options']
                for survey in audit['surveys'].values()
                for question in survey['questions']
            )
        )
        week1 = audit['surveys']['week1_reflection']
        self.assertEqual(
            [question['slug'] for question in week1['questions']],
            ['weekly_ritual_highlight', 'weekly_issue_flag', 'weekly_issue_text'],
        )
        self.assertIn('this week', week1['questions'][0]['prompt'])
        self.assertNotIn('{{week_label}}', week1['description'])
        self.assertNotIn('{{week_label_lower}}', week1['description'])

    def test_rendered_user_audit_contains_auditor_ui_and_question_controls(self):
        audit = build_survey_user_audit(
            logical_today=date(2026, 5, 18),
            now_utc=datetime(2026, 5, 18, 20, 0, tzinfo=dt_timezone.utc),
        )
        html = render_survey_user_audit_html(audit)

        self.assertIn('WhoamI Survey User Audit', html)
        self.assertIn('data-survey-slug', html)
        self.assertIn('Question type', html)
        self.assertIn('multi_choice', html)
        self.assertIn('single_choice', html)
        self.assertIn('Ver. W features', html)
        self.assertIn('Looking back: Week 1', html)
        self.assertNotIn('{{week_label}}', html)
        self.assertNotIn('{{week_label_lower}}', html)

    def test_rendered_priority_audit_contains_editor_and_export_command(self):
        audit = build_survey_user_audit(
            logical_today=date(2026, 5, 18),
            now_utc=datetime(2026, 5, 18, 20, 0, tzinfo=dt_timezone.utc),
        )
        html = render_survey_priority_audit_html(audit)

        self.assertIn('WhoamI Survey Sidebar Order Editor', html)
        self.assertIn('No-response Sidebar Preview', html)
        self.assertIn('data-order-for', html)
        self.assertIn('draggable="true"', html)
        self.assertIn('data-save-scope', html)
        self.assertIn('Conflicting date orders', html)
        self.assertIn('apply_survey_sidebar_order', html)
        self.assertIn('habit_platform', html)


class SurveySidebarOrderCommandTests(TestCase):
    def test_apply_sidebar_order_command_updates_and_clears_rows(self):
        first = Survey.objects.create(slug='first', title_en='First', title_ko='First')
        second = Survey.objects.create(slug='second', title_en='Second', title_ko='Second')
        ScheduledSurvey.objects.create(
            survey=first, cadence=CADENCE_WEEKLY,
            window_start=date(2026, 5, 18), window_end=date(2026, 5, 18),
            allow_late=True, sequence_index=1,
        )
        stale = ScheduledSurvey.objects.create(
            survey=second, cadence=CADENCE_WEEKLY,
            window_start=date(2026, 5, 18), window_end=date(2026, 5, 18),
            allow_late=True, sequence_index=2, sidebar_order=9,
        )

        out = StringIO()
        call_command(
            'apply_survey_sidebar_order',
            json_map=json.dumps({'weekly:1': 2}),
            clear_missing=True,
            stdout=out,
        )

        self.assertEqual(
            ScheduledSurvey.objects.get(cadence=CADENCE_WEEKLY, sequence_index=1).sidebar_order,
            2,
        )
        stale.refresh_from_db()
        self.assertIsNone(stale.sidebar_order)
        self.assertIn('updated=1 cleared=1 missing=0', out.getvalue())

    def test_render_sidebar_order_source_is_commit_ready(self):
        source = render_sidebar_order_source({'weekly:1': 2, 'daily:101': 1})

        self.assertIn("SIDEBAR_ORDER: dict[str, int] = {", source)
        self.assertIn("'daily:101': 1,", source)
        self.assertIn("'weekly:1': 2,", source)
