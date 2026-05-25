import csv
import datetime
import tempfile
from importlib import import_module
from pathlib import Path

import yaml
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import Connection
from surveys.models import (
    CADENCE_ENDPOINT, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse,
    ScheduledSurvey,
)
from surveys.recovery import build_recovery_coverage, load_recovery_manifest
from surveys.scheduling import _today_la_7am


RECOVERY_FIXTURE_PATH = Path(__file__).resolve().parent / 'fixtures' / 'recovery.yaml'


class RecoveryCoverageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create(
            username='alice',
            email='alice@example.com',
            user_group='group_w_first',
        )
        self.bob = User.objects.create(
            username='bob',
            email='bob@example.com',
            user_group='group_w_first',
        )
        self.q_user = User.objects.create(
            username='quinn',
            email='quinn@example.com',
            user_group='group_q_first',
        )

    def _survey(self, slug):
        return Survey.objects.create(slug=slug, title_en=slug, title_ko=slug)

    def _question(self, survey, slug, order=1, qtype='free_text'):
        return SurveyQuestion.objects.create(
            survey=survey,
            order=order,
            slug=slug,
            type=qtype,
            prompt_en=slug,
            prompt_ko=slug,
        )

    def _answer(self, user, survey, question, value='answer'):
        response, _ = SurveyResponse.objects.get_or_create(user=user, survey=survey)
        return SurveyAnswer.objects.create(response=response, question=question, value=value)

    def _write_manifest(self, data):
        f = tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w', encoding='utf-8')
        yaml.safe_dump(data, f, sort_keys=False)
        f.close()
        return Path(f.name)

    def test_exact_sources_count_as_answered_and_related_sources_do_not(self):
        base = self._survey('phase1_reflection')
        exact = self._question(base, 'final_followup', order=1)
        related = self._question(base, 'old_broad_question', order=2)
        self._answer(self.alice, base, exact, value='exact text')
        self._answer(self.bob, base, related, value='related text')

        manifest = {
            'canonical_questions': [
                {
                    'canonical_id': 'phase1.final.followup',
                    'response_type': 'free_text',
                    'sources': [
                        {
                            'survey_slug': 'phase1_reflection',
                            'question_slug': 'final_followup',
                            'equivalence': 'exact',
                        },
                        {
                            'survey_slug': 'phase1_reflection_part2',
                            'question_slug': 'final_followup',
                            'equivalence': 'exact',
                        },
                    ],
                    'related_sources': [
                        {
                            'survey_slug': 'phase1_reflection',
                            'question_slug': 'old_broad_question',
                            'equivalence': 'related_only',
                            'reason': 'Older broad prompt; useful context but not the final variable.',
                        },
                    ],
                },
            ],
            'recovery_surveys': [
                {
                    'survey_slug': 'phase1_reflection_part2',
                    'participant_title': 'Phase 1 reflection: Part 2',
                    'base_survey_slug': 'phase1_reflection',
                    'eligible_if': {'answered_survey_slug': 'phase1_reflection'},
                    'collects_canonical_ids': ['phase1.final.followup'],
                },
            ],
        }

        report = build_recovery_coverage(manifest)
        recovery = report['recovery_surveys'][0]
        question = recovery['canonical_questions'][0]

        self.assertEqual(recovery['eligible_user_count'], 2)
        self.assertEqual(recovery['users_needing_recovery_count'], 1)
        self.assertEqual(
            recovery['missing_canonical_ids_by_username'],
            {'bob': ['phase1.final.followup']},
        )
        self.assertEqual(
            recovery['related_only_canonical_ids_by_username'],
            {'bob': ['phase1.final.followup']},
        )
        self.assertEqual(question['answered_usernames'], ['alice'])
        self.assertEqual(question['missing_usernames'], ['bob'])
        self.assertEqual(question['related_only_usernames'], ['bob'])

    def test_eligible_if_can_filter_by_user_group(self):
        base = self._survey('ver_q_survey')
        exact = self._question(base, 'missing_q')
        self._answer(self.alice, base, exact, value='wrong group but answered')
        self._answer(self.q_user, base, exact, value='right group')

        manifest = {
            'canonical_questions': [
                {
                    'canonical_id': 'ver_q.missing_q',
                    'response_type': 'free_text',
                    'sources': [
                        {
                            'survey_slug': 'ver_q_survey',
                            'question_slug': 'missing_q',
                            'equivalence': 'exact',
                        },
                    ],
                },
            ],
            'recovery_surveys': [
                {
                    'survey_slug': 'ver_q_survey_part2',
                    'participant_title': 'Ver.Q features: Part 2',
                    'base_survey_slug': 'ver_q_survey',
                    'eligible_if': {
                        'answered_survey_slug': 'ver_q_survey',
                        'user_group': 'group_q_first',
                    },
                    'collects_canonical_ids': ['ver_q.missing_q'],
                },
            ],
        }

        report = build_recovery_coverage(manifest)
        recovery = report['recovery_surveys'][0]

        self.assertEqual(recovery['eligible_usernames'], ['quinn'])
        self.assertEqual(recovery['users_needing_recovery_count'], 0)

    def test_source_can_exclude_invalid_answer_values(self):
        base = self._survey('feature_eval_w')
        rating = self._question(base, 'goal1_feat_dailyq', qtype='likert_5')
        self._answer(self.alice, base, rating, value=None)
        self._answer(self.bob, base, rating, value=4)

        manifest = {
            'canonical_questions': [
                {
                    'canonical_id': 'feature_eval_w.goal1_feat_dailyq',
                    'response_type': 'likert_5',
                    'sources': [
                        {
                            'survey_slug': 'feature_eval_w',
                            'question_slug': 'goal1_feat_dailyq',
                            'equivalence': 'exact',
                            'exclude_values': [None],
                        },
                    ],
                },
            ],
            'recovery_surveys': [
                {
                    'survey_slug': 'feature_eval_w_part2',
                    'participant_title': 'Ver.W features: Part 2',
                    'base_survey_slug': 'feature_eval_w',
                    'eligible_if': {'answered_survey_slug': 'feature_eval_w'},
                    'collects_canonical_ids': ['feature_eval_w.goal1_feat_dailyq'],
                },
            ],
        }

        report = build_recovery_coverage(manifest)
        recovery = report['recovery_surveys'][0]
        question = recovery['canonical_questions'][0]

        self.assertEqual(question['answered_usernames'], ['bob'])
        self.assertEqual(question['missing_usernames'], ['alice'])
        self.assertEqual(question['sources'][0]['excluded_answer_count'], 1)

    def test_command_writes_yaml_report(self):
        base = self._survey('cmd_survey')
        question = self._question(base, 'cmd_question')
        self._answer(self.alice, base, question, value='done')
        manifest_path = self._write_manifest({
            'canonical_questions': [
                {
                    'canonical_id': 'cmd.question',
                    'response_type': 'free_text',
                    'sources': [
                        {
                            'survey_slug': 'cmd_survey',
                            'question_slug': 'cmd_question',
                            'equivalence': 'exact',
                        },
                    ],
                },
            ],
            'recovery_surveys': [
                {
                    'survey_slug': 'cmd_survey_part2',
                    'participant_title': 'Command Survey: Part 2',
                    'base_survey_slug': 'cmd_survey',
                    'eligible_if': {'answered_survey_slug': 'cmd_survey'},
                    'collects_canonical_ids': ['cmd.question'],
                },
            ],
        })
        out = tempfile.NamedTemporaryFile(suffix='.yaml', delete=False)
        out.close()

        call_command(
            'audit_survey_recovery_coverage',
            '--manifest',
            str(manifest_path),
            '--out',
            out.name,
        )

        report = yaml.safe_load(Path(out.name).read_text(encoding='utf-8'))
        self.assertEqual(report['manifest_path'], str(manifest_path))
        self.assertEqual(
            report['recovery_surveys'][0]['canonical_questions'][0]['answered_usernames'],
            ['alice'],
        )

    def test_default_manifest_loads(self):
        manifest = load_recovery_manifest()

        self.assertIn('canonical_questions', manifest)
        self.assertIn('recovery_surveys', manifest)


class RecoverySurveyApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(
            username='recover_me',
            email='recover_me@example.com',
            user_group='group_w_first',
        )
        self.client.force_authenticate(user=self.user)

    def _survey(self, slug, *, repeatable=False):
        return Survey.objects.create(
            slug=slug,
            title_en=slug,
            title_ko=slug,
            repeatable=repeatable,
            results_hidden=True,
        )

    def _question(self, survey, slug, order, qtype='free_text'):
        return SurveyQuestion.objects.create(
            survey=survey,
            slug=slug,
            order=order,
            type=qtype,
            prompt_en=slug,
            prompt_ko=slug,
        )

    def _answer(self, user, survey, question, value='answer'):
        response = SurveyResponse.objects.create(user=user, survey=survey)
        return SurveyAnswer.objects.create(response=response, question=question, value=value)

    def _schedule_open(self, survey):
        today = _today_la_7am()
        return ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_ENDPOINT,
            sequence_index=950,
            window_start=today,
            window_end=None,
            allow_late=True,
        )

    def test_recovery_detail_expands_missing_feature_followups_to_blocks(self):
        base = self._survey('feature_eval_w')
        answered_rating = self._question(base, 'goal1_feat_dailyq', 1, 'likert_5')
        related_only = self._question(base, 'goal4_feat_social_battery', 2, 'likert_5')
        self._answer(self.user, base, answered_rating, value=4)
        self._answer(self.user, base, related_only, value=5)

        recovery = self._survey('feature_eval_w_part2', repeatable=True)
        self._question(recovery, 'goal1_feat_dailyq', 1, 'likert_5')
        self._question(recovery, 'goal1_feat_dailyq_enjoy', 2)
        self._question(recovery, 'goal1_feat_dailyq_dislike', 3)
        self._question(recovery, 'goal2_feat_social_battery_level', 4, 'likert_5')
        self._schedule_open(recovery)

        response = self.client.get('/api/surveys/feature_eval_w_part2/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [q['slug'] for q in response.json()['questions']]
        self.assertIn('goal1_feat_dailyq', slugs)
        self.assertIn('goal1_feat_dailyq_enjoy', slugs)
        self.assertIn('goal1_feat_dailyq_dislike', slugs)
        self.assertIn('goal2_feat_social_battery_level', slugs)

    def test_feature_recovery_detail_preserves_feature_blocks_when_followups_missing(self):
        base = self._survey('feature_eval_w')
        answered_rating = self._question(base, 'goal1_feat_dailyq', 1, 'likert_5')
        self._answer(self.user, base, answered_rating, value=4)

        recovery = self._survey('feature_eval_w_part2', repeatable=True)
        rating = self._question(recovery, 'goal1_feat_dailyq', 1, 'likert_5')
        enjoy = self._question(recovery, 'goal1_feat_dailyq_enjoy', 2)
        dislike = self._question(recovery, 'goal1_feat_dailyq_dislike', 3)
        self._schedule_open(recovery)

        response = self.client.get('/api/surveys/feature_eval_w_part2/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [q['slug'] for q in response.json()['questions']],
            [rating.slug, enjoy.slug, dislike.slug],
        )
        self.assertEqual(response.json()['draft']['answers'], {str(rating.id): 4})

    def test_recovery_index_hides_survey_when_user_has_no_visible_missing_questions(self):
        base = self._survey('feature_eval_w')
        rating = self._question(base, 'goal1_feat_dailyq', 1, 'likert_5')
        enjoy = self._question(base, 'goal1_feat_dailyq_enjoy', 2)
        dislike = self._question(base, 'goal1_feat_dailyq_dislike', 3)
        self._answer(self.user, base, rating, value=4)
        self._answer(self.user, base, enjoy, value='Useful')
        self._answer(self.user, base, dislike, value='None')

        recovery = self._survey('feature_eval_w_part2', repeatable=True)
        self._question(recovery, 'goal1_feat_dailyq', 1, 'likert_5')
        self._question(recovery, 'goal1_feat_dailyq_enjoy', 2)
        self._question(recovery, 'goal1_feat_dailyq_dislike', 3)
        self._schedule_open(recovery)

        response = self.client.get('/api/surveys/index/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_slugs = [row['survey']['slug'] for row in response.json()['available_now']]
        self.assertNotIn('feature_eval_w_part2', available_slugs)

    def test_recovery_replacement_shows_full_part_when_base_unanswered(self):
        self._survey('feature_eval_w')
        recovery = self._survey('feature_eval_w_part2', repeatable=True)
        rating = self._question(recovery, 'goal1_feat_dailyq', 1, 'likert_5')
        enjoy = self._question(recovery, 'goal1_feat_dailyq_enjoy', 2)
        dislike = self._question(recovery, 'goal1_feat_dailyq_dislike', 3)
        self._schedule_open(recovery)

        response = self.client.get('/api/surveys/feature_eval_w_part2/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [q['slug'] for q in response.json()['questions']],
            [rating.slug, enjoy.slug, dislike.slug],
        )

    def test_recovery_submit_accepts_visible_feature_block_and_rejects_unrelated_question(self):
        base = self._survey('feature_eval_w')
        rating = self._question(base, 'goal1_feat_dailyq', 1, 'likert_5')
        self._answer(self.user, base, rating, value=4)

        recovery = self._survey('feature_eval_w_part2', repeatable=True)
        repeated_rating = self._question(recovery, 'goal1_feat_dailyq', 1, 'likert_5')
        enjoy = self._question(recovery, 'goal1_feat_dailyq_enjoy', 2)
        unrelated = self._question(recovery, 'unrelated_question', 3)
        self._schedule_open(recovery)

        rejected = self.client.post(
            '/api/surveys/feature_eval_w_part2/responses/',
            {'answers': [{'question_id': unrelated.id, 'value': 'Nope'}]},
            format='json',
        )
        accepted = self.client.post(
            '/api/surveys/feature_eval_w_part2/responses/',
            {
                'answers': [
                    {'question_id': repeated_rating.id, 'value': 5},
                    {'question_id': enjoy.id, 'value': 'Useful'},
                ],
            },
            format='json',
        )

        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(accepted.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            SurveyAnswer.objects.filter(question=repeated_rating, response__user=self.user).exists()
        )
        self.assertTrue(
            SurveyAnswer.objects.filter(question=enjoy, response__user=self.user).exists()
        )
        self.assertFalse(
            SurveyAnswer.objects.filter(question=unrelated, response__user=self.user).exists()
        )

    def test_full_resubmit_recovery_shows_all_questions_until_part2_answered(self):
        friend = get_user_model().objects.create(
            username='recover_friend',
            email='recover_friend@example.com',
        )
        connection = Connection.objects.create(
            user1=self.user,
            user2=friend,
            user1_choice='friend',
            user2_choice='friend',
        )
        Connection.objects.filter(id=connection.id).update(
            created_at=timezone.now() - datetime.timedelta(days=4),
        )
        base = self._survey('phase1_friend_closeness')
        SurveyResponse.objects.create(user=self.user, survey=base)

        recovery = self._survey('phase1_friend_closeness_part2', repeatable=True)
        current = self._question(
            recovery,
            'phase1_friend_closeness_part2_current',
            1,
            'per_friend_likert_5',
        )
        corrected = self._question(
            recovery,
            'phase1_friend_closeness_part2_corrected_baseline',
            2,
            'per_friend_likert_5',
        )
        offline = self._question(
            recovery,
            'phase1_friend_closeness_part2_offline',
            3,
            'per_friend_single_choice',
        )
        self._schedule_open(recovery)

        before = self.client.get('/api/surveys/index/')
        self.assertEqual(before.status_code, status.HTTP_200_OK)
        available_slugs = [row['survey']['slug'] for row in before.json()['available_now']]
        self.assertIn('phase1_friend_closeness_part2', available_slugs)

        detail = self.client.get('/api/surveys/phase1_friend_closeness_part2/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [q['slug'] for q in detail.json()['questions']],
            [
                current.slug,
                corrected.slug,
                offline.slug,
            ],
        )

        submitted = self.client.post(
            '/api/surveys/phase1_friend_closeness_part2/responses/',
            {
                'answers': [
                    {
                        'question_id': current.id,
                        'target_user_id': friend.id,
                        'value': 4,
                    },
                    {
                        'question_id': offline.id,
                        'target_user_id': friend.id,
                        'value': 'weekly',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(submitted.status_code, status.HTTP_201_CREATED)
        self.assertFalse(
            SurveyAnswer.objects.filter(question=corrected, response__user=self.user).exists()
        )

        after = self.client.get('/api/surveys/index/')
        self.assertEqual(after.status_code, status.HTTP_200_OK)
        available_slugs = [row['survey']['slug'] for row in after.json()['available_now']]
        self.assertNotIn('phase1_friend_closeness_part2', available_slugs)

    def test_friend_closeness_part2_prefills_from_part1_eligible_friends_only(self):
        User = get_user_model()
        friend = User.objects.create(
            username='recover_friend',
            email='recover_friend@example.com',
        )
        stale_nonfriend = User.objects.create(
            username='stale_nonfriend',
            email='stale_nonfriend@example.com',
        )
        connection = Connection.objects.create(
            user1=self.user,
            user2=friend,
            user1_choice='friend',
            user2_choice='friend',
        )
        Connection.objects.filter(id=connection.id).update(
            created_at=timezone.now() - datetime.timedelta(days=4),
        )
        base = self._survey('phase1_friend_closeness')
        base_current = self._question(
            base,
            'phase1_friend_closeness_current',
            1,
            'per_friend_likert_5',
        )
        base_corrected = self._question(
            base,
            'phase1_friend_closeness_corrected_baseline',
            2,
            'per_friend_likert_5',
        )
        base_offline = self._question(
            base,
            'phase1_friend_closeness_offline',
            3,
            'per_friend_single_choice',
        )
        source_response = SurveyResponse.objects.create(user=self.user, survey=base)
        SurveyAnswer.objects.create(
            response=source_response,
            question=base_current,
            target_user=friend,
            value=4,
        )
        SurveyAnswer.objects.create(
            response=source_response,
            question=base_corrected,
            target_user=friend,
            value=2,
        )
        SurveyAnswer.objects.create(
            response=source_response,
            question=base_offline,
            target_user=friend,
            value='weekly',
        )
        SurveyAnswer.objects.create(
            response=source_response,
            question=base_current,
            target_user=stale_nonfriend,
            value=1,
        )

        recovery = self._survey('phase1_friend_closeness_part2', repeatable=True)
        current = self._question(
            recovery,
            'phase1_friend_closeness_part2_current',
            1,
            'per_friend_likert_5',
        )
        corrected = self._question(
            recovery,
            'phase1_friend_closeness_part2_corrected_baseline',
            2,
            'per_friend_likert_5',
        )
        offline = self._question(
            recovery,
            'phase1_friend_closeness_part2_offline',
            3,
            'per_friend_single_choice',
        )
        self._schedule_open(recovery)

        response = self.client.get('/api/surveys/phase1_friend_closeness_part2/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        draft = response.json()['draft']
        self.assertIsNotNone(draft)
        self.assertEqual(
            draft['answers'][str(current.id)],
            {str(friend.id): 4},
        )
        self.assertEqual(
            draft['answers'][str(corrected.id)],
            {str(friend.id): 2},
        )
        self.assertEqual(
            draft['answers'][str(offline.id)],
            {str(friend.id): 'weekly'},
        )
        self.assertNotIn(str(stale_nonfriend.id), draft['answers'][str(current.id)])


class FriendClosenessPanelDumpTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(
            username='panel_user',
            email='panel_user@example.com',
        )
        self.friend = User.objects.create(
            username='panel_friend',
            email='panel_friend@example.com',
        )

    def _survey(self, slug):
        return Survey.objects.create(
            slug=slug,
            title_en=slug,
            title_ko=slug,
            results_hidden=True,
        )

    def _question(self, survey, slug, order, qtype='per_friend_likert_5'):
        return SurveyQuestion.objects.create(
            survey=survey,
            slug=slug,
            order=order,
            type=qtype,
            prompt_en=slug,
            prompt_ko=slug,
        )

    def test_dump_prefers_phase1_part2_over_original_phase1_response(self):
        phase1 = self._survey('phase1_friend_closeness')
        phase1_current = self._question(
            phase1,
            'phase1_friend_closeness_current',
            1,
        )
        part2 = self._survey('phase1_friend_closeness_part2')
        part2_current = self._question(
            part2,
            'phase1_friend_closeness_part2_current',
            1,
        )
        p1_response = SurveyResponse.objects.create(user=self.user, survey=phase1)
        SurveyAnswer.objects.create(
            response=p1_response,
            question=phase1_current,
            target_user=self.friend,
            value=2,
        )
        part2_response = SurveyResponse.objects.create(user=self.user, survey=part2)
        SurveyAnswer.objects.create(
            response=part2_response,
            question=part2_current,
            target_user=self.friend,
            value=5,
        )
        out = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        out.close()

        call_command(
            'dump_friend_closeness_panel',
            '--user',
            self.user.username,
            '--out',
            out.name,
        )

        with open(out.name, newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['evaluated_user_username'], self.friend.username)
        self.assertEqual(rows[0]['phase1_current_closeness'], '5')

    def test_dump_falls_back_to_original_phase1_when_part2_missing(self):
        phase1 = self._survey('phase1_friend_closeness')
        phase1_current = self._question(
            phase1,
            'phase1_friend_closeness_current',
            1,
        )
        p1_response = SurveyResponse.objects.create(user=self.user, survey=phase1)
        SurveyAnswer.objects.create(
            response=p1_response,
            question=phase1_current,
            target_user=self.friend,
            value=3,
        )
        out = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        out.close()

        call_command(
            'dump_friend_closeness_panel',
            '--user',
            self.user.username,
            '--out',
            out.name,
        )

        with open(out.name, newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['phase1_current_closeness'], '3')


class RecoveryFixtureTests(TestCase):
    def test_recovery_fixture_loads_public_part_surveys_without_internal_copy(self):
        call_command('load_surveys', str(RECOVERY_FIXTURE_PATH))

        expected_slugs = {
            'study_endpoint_part2',
            'phase1_reflection_part3_w',
            'phase1_reflection_part3_q',
            'phase2_reflection_part3_w',
            'phase2_reflection_part3_q',
            'feature_eval_w_part2',
            'phase1_friend_closeness_part2',
        }
        self.assertEqual(
            set(Survey.objects.filter(slug__in=expected_slugs).values_list('slug', flat=True)),
            expected_slugs,
        )
        forbidden_words = ('missed', 'schema', 'supplemental', 'internal')
        for survey in Survey.objects.filter(slug__in=expected_slugs).prefetch_related('questions'):
            public_text = ' '.join([
                survey.title_en,
                survey.description_en,
                *[
                    ' '.join([q.prompt_en, q.description_en, q.placeholder_en, q.content_en])
                    for q in survey.questions.all()
                ],
            ]).lower()
            for word in forbidden_words:
                self.assertNotIn(word, public_text, survey.slug)
            self.assertTrue(survey.results_hidden)
            self.assertTrue(survey.repeatable)

    def test_recovery_schedule_seeder_creates_open_rows(self):
        call_command('load_surveys', str(RECOVERY_FIXTURE_PATH))
        module = import_module('surveys.migrations.0039_seed_recovery_surveys')

        module.seed_recovery_surveys(django_apps, None)

        rows = ScheduledSurvey.objects.filter(
            survey__slug__in=[row[1] for row in module.RECOVERY_SCHEDULE],
        ).select_related('survey')
        self.assertEqual(rows.count(), len(module.RECOVERY_SCHEDULE))
        by_slug = {row.survey.slug: row for row in rows}
        self.assertEqual(
            by_slug['phase1_reflection_part3_w'].target_user_group,
            'group_w_first',
        )
        self.assertEqual(
            by_slug['phase1_reflection_part3_q'].target_user_group,
            'group_q_first',
        )
        self.assertEqual(by_slug['feature_eval_w_part2'].target_user_group, '')

    def test_friend_closeness_part2_schedule_seeder_creates_open_row(self):
        call_command('load_surveys', str(RECOVERY_FIXTURE_PATH))
        module = import_module('surveys.migrations.0042_seed_friend_closeness_part2_recovery')

        module.seed_friend_closeness_part2_recovery(django_apps, None)

        row = ScheduledSurvey.objects.get(
            cadence=CADENCE_ENDPOINT,
            sequence_index=26,
        )
        self.assertEqual(row.survey.slug, 'phase1_friend_closeness_part2')
        self.assertTrue(row.allow_late)

    def test_recovery_manifest_sources_exist_in_recovery_fixture(self):
        call_command('load_surveys', str(RECOVERY_FIXTURE_PATH))
        manifest = load_recovery_manifest()
        canonical_by_id = {
            item['canonical_id']: item
            for item in manifest['canonical_questions']
        }

        missing_sources = []
        for recovery in manifest['recovery_surveys']:
            survey_slug = recovery['survey_slug']
            existing_slugs = set(
                SurveyQuestion.objects
                .filter(survey__slug=survey_slug)
                .values_list('slug', flat=True)
            )
            for canonical_id in recovery['collects_canonical_ids']:
                canonical = canonical_by_id[canonical_id]
                for source in canonical['sources']:
                    if source['survey_slug'] != survey_slug:
                        continue
                    if source['question_slug'] not in existing_slugs:
                        missing_sources.append((survey_slug, source['question_slug'], canonical_id))

        self.assertEqual(missing_sources, [])


class FeatureEvalWFinalSetMigrationTests(TestCase):
    def test_migration_adds_final_social_battery_feature_and_hides_obsolete_feature(self):
        User = get_user_model()
        user = User.objects.create(username='feature_user', email='feature_user@example.com')
        survey = Survey.objects.create(slug='feature_eval_w', title_en='Ver.W features')
        browse = SurveyQuestion.objects.create(
            survey=survey,
            order=1,
            slug='goal2_feat_browse',
            type='likert_5',
            prompt_en='**Browsing modes** — I liked this feature.',
        )
        obsolete_availability = SurveyQuestion.objects.create(
            survey=survey,
            order=2,
            slug='goal2_feat_chatstatus',
            type='likert_5',
            prompt_en='**Obsolete availability item** — I liked this feature.',
        )
        obsolete_social = SurveyQuestion.objects.create(
            survey=survey,
            order=3,
            slug='goal4_feat_social_battery',
            type='likert_5',
            prompt_en='**Social battery update after long chats** — I liked this feature.',
        )
        granular = SurveyQuestion.objects.create(
            survey=survey,
            order=4,
            slug='goal4_feat_granular_sub',
            type='likert_5',
            prompt_en='**Granular subscription to friends** — I liked this feature.',
        )
        response = SurveyResponse.objects.create(user=user, survey=survey)
        SurveyAnswer.objects.create(response=response, question=obsolete_availability, value=4)
        SurveyAnswer.objects.create(response=response, question=obsolete_social, value=5)

        module = import_module('surveys.migrations.0040_feature_eval_w_final_feature_set')
        module.apply_feature_eval_w_final_feature_set(django_apps, None)

        final_slugs = list(survey.questions.order_by('order').values_list('slug', flat=True))
        self.assertLess(
            final_slugs.index('goal2_feat_browse'),
            final_slugs.index('goal2_feat_social_battery_level'),
        )
        self.assertLess(
            final_slugs.index('goal2_feat_social_battery_level'),
            final_slugs.index('goal4_feat_granular_sub'),
        )
        for slug in [
            'goal2_feat_social_battery_level',
            'goal2_feat_social_battery_level_enjoy',
            'goal2_feat_social_battery_level_dislike',
        ]:
            self.assertTrue(SurveyQuestion.objects.filter(survey=survey, slug=slug).exists())

        obsolete_availability.refresh_from_db()
        obsolete_social.refresh_from_db()
        expected_hidden_rule = {
            'depends_on': '__deprecated_feature_never_shown__',
            'show_when_value': '__show__',
        }
        self.assertEqual(obsolete_availability.conditional_display, expected_hidden_rule)
        self.assertEqual(obsolete_social.conditional_display, expected_hidden_rule)
        self.assertFalse(obsolete_availability.required)
        self.assertFalse(obsolete_social.required)
        self.assertEqual(obsolete_availability.answers.count(), 1)
        self.assertEqual(obsolete_social.answers.count(), 1)


class FeatureEvalWCopyCleanupMigrationTests(TestCase):
    def test_migration_removes_feature_descriptions_and_hides_deprecated_rows(self):
        survey = Survey.objects.create(slug='feature_eval_w', title_en='Ver.W features')
        SurveyQuestion.objects.create(
            survey=survey,
            order=1,
            slug='goal8_feat_retroactive',
            type='likert_5',
            prompt_en='**Apply privacy changes to past posts** — I liked this feature.',
            description_en='Old leading explanation.',
            description_ko='Old leading explanation.',
        )
        survey_digest = SurveyQuestion.objects.create(
            survey=survey,
            order=2,
            slug='goal6_feat_survey_digest',
            type='likert_5',
            prompt_en='**Old combined digest item** — I liked this feature.',
            description_en='Old combined explanation.',
            description_ko='Old combined explanation.',
        )
        daily_digest = SurveyQuestion.objects.create(
            survey=survey,
            order=3,
            slug='goal7_feat_discover',
            type='likert_5',
            prompt_en='**Old digest item** — I liked this feature.',
        )
        deprecated = SurveyQuestion.objects.create(
            survey=survey,
            order=4,
            slug='goal2_feat_chatstatus',
            type='likert_5',
            prompt_en='**Obsolete availability item** — I liked this feature.',
        )

        module = import_module('surveys.migrations.0041_feature_eval_w_copy_cleanup')
        module.apply_feature_eval_w_copy_cleanup(django_apps, None)

        survey_digest.refresh_from_db()
        daily_digest.refresh_from_db()
        deprecated.refresh_from_db()
        retroactive = SurveyQuestion.objects.get(survey=survey, slug='goal8_feat_retroactive')

        self.assertEqual(retroactive.description_en, '')
        self.assertEqual(survey_digest.description_en, '')
        self.assertEqual(survey_digest.prompt_en, '**Survey of the Day** — I liked this feature.')
        self.assertEqual(daily_digest.prompt_en, '**Daily Digest** — I liked this feature.')
        self.assertEqual(
            deprecated.conditional_display,
            {
                'depends_on': '__deprecated_feature_never_shown__',
                'show_when_value': '__show__',
            },
        )
        self.assertEqual(deprecated.prompt_en, 'Deprecated feature (hidden)')
        self.assertEqual(deprecated.description_en, '')
        self.assertFalse(deprecated.required)
