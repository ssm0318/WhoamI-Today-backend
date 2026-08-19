import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import FriendEvaluation, FriendRequest
from check_in.models import CheckInPost
from chat.models import WitBotConversationState
from note.models import Note
from surveys._test_helpers import make_likert_survey, make_user
from surveys.app_usage import (
    app_usage_metrics_for_user, sync_app_usage_award_for_user,
    sync_app_usage_awards,
)
from surveys.models import (
    CADENCE_DAILY, CADENCE_WEEKLY, PointAward, ScheduledSurvey, Survey,
    SurveyResponse,
)
from surveys.points import (
    available_max_for_user, backfill_missing_survey_point_awards,
    reimbursement_state_for_user,
)
from surveys.scheduling import _today_la_7am


class SurveyPointAwardSubmitTests(APITestCase):
    def _payload_for(self, survey):
        questions = list(survey.questions.order_by('order'))
        return {'answers': [
            {'question_id': questions[0].id, 'value': 4},
            {'question_id': questions[1].id, 'value': 2},
        ]}

    def test_first_submit_creates_one_award_for_scheduled_opportunity(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('rewarded')
        survey.point_value = 12
        survey.save(update_fields=['point_value'])
        today = _today_la_7am()
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        response = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        award = PointAward.objects.get(user=viewer, scheduled_survey=scheduled)
        self.assertEqual(award.response_id, response.json()['id'])
        self.assertEqual(award.source_kind, 'survey')
        self.assertEqual(award.source_slug, 'rewarded')
        self.assertEqual(award.awarded_points, 12)
        self.assertEqual(response.json()['point_award']['effective_points'], 12)

    def test_backfill_missing_survey_point_awards_creates_legacy_award_once(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('legacy_reward')
        survey.point_value = 12
        survey.save(update_fields=['point_value'])
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=datetime.date(2026, 5, 5),
            window_end=datetime.date(2026, 5, 5),
            allow_late=True,
            sequence_index=1,
        )
        response = SurveyResponse.objects.create(user=viewer, survey=survey)
        submitted_at = datetime.datetime(
            2026, 5, 5, 20, 0, tzinfo=datetime.timezone.utc,
        )
        SurveyResponse.objects.filter(pk=response.pk).update(submitted_at=submitted_at)
        response.refresh_from_db()

        first_result = backfill_missing_survey_point_awards()
        second_result = backfill_missing_survey_point_awards()

        self.assertEqual(first_result.created, 1)
        self.assertEqual(second_result.created, 0)
        award = PointAward.objects.get(user=viewer, scheduled_survey=scheduled)
        self.assertEqual(award.response_id, response.id)
        self.assertEqual(award.source_slug, 'legacy_reward')
        self.assertEqual(award.awarded_points, 12)

    def test_editable_resubmit_does_not_create_second_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('editable_reward')
        survey.point_value = 20
        survey.editable = True
        survey.save(update_fields=['point_value', 'editable'])
        today = _today_la_7am()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        first = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )
        second = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PointAward.objects.filter(user=viewer, source_slug=survey.slug).count(), 1)
        award = PointAward.objects.get(user=viewer, source_slug=survey.slug)
        self.assertEqual(award.response_id, first.json()['id'])

    def test_repeatable_submit_same_schedule_does_not_create_second_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('repeatable_reward')
        survey.point_value = 7
        survey.repeatable = True
        survey.save(update_fields=['point_value', 'repeatable'])
        today = _today_la_7am()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        self.client.post(f'/api/surveys/{survey.slug}/responses/', self._payload_for(survey), format='json')
        self.client.post(f'/api/surveys/{survey.slug}/responses/', self._payload_for(survey), format='json')

        self.assertEqual(SurveyResponse.objects.filter(user=viewer, survey=survey).count(), 2)
        self.assertEqual(PointAward.objects.filter(user=viewer, source_slug=survey.slug).count(), 1)

    def test_unmet_point_prereq_creates_zero_point_award(self):
        viewer = make_user('viewer')
        prereq = make_likert_survey('prereq')
        survey = make_likert_survey('locked_reward')
        survey.point_value = 9
        survey.point_prereq_slug = prereq.slug
        survey.save(update_fields=['point_value', 'point_prereq_slug'])
        today = _today_la_7am()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        response = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        award = PointAward.objects.get(user=viewer, source_slug=survey.slug)
        self.assertEqual(award.awarded_points, 0)
        self.assertIn('Prereq prereq not completed', award.note)
        self.assertEqual(response.json()['point_award']['note'], award.note)

    def test_zero_point_survey_creates_no_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('unrewarded')
        today = _today_la_7am()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        response = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.json()['point_award'])
        self.assertFalse(PointAward.objects.filter(user=viewer, source_slug=survey.slug).exists())

    def test_late_sotd_submit_on_weekend_creates_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('sotd_d26_transition')
        survey.point_value = 12
        survey.save(update_fields=['point_value'])
        friday = datetime.date(2026, 5, 29)
        sunday = datetime.date(2026, 5, 31)
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_DAILY,
            window_start=friday,
            window_end=friday,
            allow_late=True,
            sequence_index=126,
        )
        self.client.force_authenticate(user=viewer)

        with patch('surveys.points._today_la_7am', return_value=sunday):
            response = self.client.post(
                f'/api/surveys/{survey.slug}/responses/',
                self._payload_for(survey),
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        award = PointAward.objects.get(user=viewer, scheduled_survey=scheduled)
        self.assertEqual(award.awarded_points, 12)
        self.assertEqual(response.json()['point_award']['effective_points'], 12)


class ReimbursementApiTests(APITestCase):
    def test_reimbursement_state_returns_totals_awards_and_available_max(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('weekly_reward')
        survey.point_value = 16
        survey.save(update_fields=['point_value'])
        today = _today_la_7am()
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        response = SurveyResponse.objects.create(user=viewer, survey=survey)
        PointAward.objects.create(
            user=viewer,
            source_kind='survey',
            source_slug=survey.slug,
            scheduled_survey=scheduled,
            response=response,
            awarded_points=16,
            adjusted_points=4,
            note='Downgraded after audit.',
        )
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/reimbursement/')

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        body = result.json()
        self.assertEqual(body['provisional_total'], 4)
        self.assertEqual(body['adjusted_total'], 4)
        self.assertGreaterEqual(body['available_max'], 16)
        self.assertEqual(body['points_per_dollar'], 10)
        self.assertTrue(body['is_final'])
        self.assertEqual(
            body['policy_notice_en'],
            'Surveys determined not to have been answered in good faith were not credited, even when the survey was completed.',
        )
        self.assertEqual(body['awards'][0]['effective_points'], 4)
        self.assertEqual(body['awards'][0]['awarded_points'], 16)
        self.assertEqual(body['awards'][0]['title_en'], 'T')
        self.assertEqual(body['awards'][0]['scheduled_survey_id'], scheduled.id)

    def test_reimbursement_state_labels_interview_award_as_interview(self):
        viewer = make_user('viewer')
        PointAward.objects.create(
            user=viewer,
            source_kind=PointAward.SOURCE_INTERVIEW_SIGNUP,
            source_slug=PointAward.SOURCE_INTERVIEW_SIGNUP,
            awarded_points=200,
        )
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/reimbursement/')

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        award = result.json()['awards'][0]
        self.assertEqual(award['title_en'], 'Interview')
        self.assertEqual(award['title_ko'], 'Interview')
        self.assertTrue(result.json()['interview_opportunity']['completed'])
        self.assertIsNone(result.json()['interview_opportunity']['signup_url'])

    def test_incomplete_interview_exposes_only_the_calendly_action(self):
        viewer = make_user('viewer')
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/reimbursement/')

        opportunity = result.json()['interview_opportunity']
        self.assertFalse(opportunity['completed'])
        self.assertEqual(opportunity['potential_points'], 100)
        self.assertEqual(
            opportunity['signup_url'],
            'https://calendly.com/jaewonkim/60min',
        )
        self.assertEqual(result.json()['pending_prereqs'], [])

    def test_reimbursement_state_labels_researcher_adjustment_award(self):
        viewer = make_user('viewer')
        PointAward.objects.create(
            user=viewer,
            source_kind=PointAward.SOURCE_RESEARCHER_ADJUSTMENT,
            source_slug='interview_extra_75min',
            awarded_points=50,
            note='75-minute interview, +$5.',
        )
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/reimbursement/')

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        award = result.json()['awards'][0]
        self.assertEqual(award['title_en'], 'Interview Extra 75min')
        self.assertEqual(award['title_ko'], 'Interview Extra 75min')
        self.assertEqual(award['effective_points'], 50)

    def test_reimbursement_state_labels_friend_invitation_award(self):
        viewer = make_user('viewer')
        PointAward.objects.create(
            user=viewer,
            source_kind=PointAward.SOURCE_FRIEND_INVITE,
            source_slug=PointAward.SOURCE_FRIEND_INVITE,
            awarded_points=100,
        )
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/reimbursement/')

        award = result.json()['awards'][0]
        self.assertEqual(award['title_en'], 'Friend invitations')
        self.assertEqual(award['title_ko'], '친구 초대')

    def test_reimbursement_state_ignores_unmaterialized_response_in_frozen_ledger(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('legacy_reward')
        survey.point_value = 12
        survey.save(update_fields=['point_value'])
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=datetime.date(2026, 5, 5),
            window_end=datetime.date(2026, 5, 5),
            allow_late=True,
            sequence_index=1,
        )
        response = SurveyResponse.objects.create(user=viewer, survey=survey)
        submitted_at = datetime.datetime(
            2026, 5, 5, 20, 0, tzinfo=datetime.timezone.utc,
        )
        SurveyResponse.objects.filter(pk=response.pk).update(submitted_at=submitted_at)

        self.client.force_authenticate(user=viewer)
        result = self.client.get('/api/surveys/reimbursement/')

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        body = result.json()
        self.assertEqual(body['provisional_total'], 0)
        self.assertEqual(body['adjusted_total'], 0)
        self.assertEqual(body['awards'], [])
        self.assertEqual(PointAward.objects.filter(user=viewer).count(), 0)

    def test_reimbursement_state_does_not_duplicate_existing_point_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('already_awarded')
        survey.point_value = 12
        survey.save(update_fields=['point_value'])
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=datetime.date(2026, 5, 5),
            window_end=datetime.date(2026, 5, 5),
            allow_late=True,
            sequence_index=1,
        )
        response = SurveyResponse.objects.create(user=viewer, survey=survey)
        PointAward.objects.create(
            user=viewer,
            source_kind=PointAward.SOURCE_SURVEY,
            source_slug=survey.slug,
            scheduled_survey=scheduled,
            response=response,
            awarded_points=12,
            adjusted_points=4,
        )

        state = reimbursement_state_for_user(viewer)

        self.assertEqual(state['provisional_total'], 4)
        self.assertEqual(state['adjusted_total'], 4)
        self.assertEqual(len(state['awards']), 1)


class SurveyPointStateSerializerTests(APITestCase):
    def test_index_entries_include_point_state_and_prereq_lock(self):
        viewer = make_user('viewer')
        prereq = make_likert_survey('point_prereq')
        survey = make_likert_survey('locked_index')
        survey.point_value = 11
        survey.point_prereq_slug = prereq.slug
        survey.save(update_fields=['point_value', 'point_prereq_slug'])
        today = _today_la_7am()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/index/')

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        entry = result.json()['available_now'][0]
        self.assertEqual(entry['point_value'], 11)
        self.assertEqual(entry['point_locked_by_prereq_slug'], 'point_prereq')
        self.assertEqual(entry['point_locked_by_prereq_title_en'], 'T')
        self.assertIsNone(entry['point_award'])


class PointManualCreditCommandTests(TestCase):
    def _set_created_at(self, obj, day):
        moment = datetime.datetime.combine(
            day,
            datetime.time(hour=12),
            tzinfo=datetime.timezone.utc,
        )
        obj.__class__.objects.filter(pk=obj.pk).update(created_at=moment, updated_at=moment)

    def _note_on(self, user, day):
        note = Note.objects.create(author=user, content=f'note {day.isoformat()}')
        self._set_created_at(note, day)
        return note

    def _checkin_post_on(self, user, day):
        post = CheckInPost.objects.create(author=user, caption=f'post {day.isoformat()}')
        self._set_created_at(post, day)
        return post

    def test_credit_wit_bot_audit_credits_each_phase_separately(self):
        viewer = make_user('viewer')
        viewer.user_group = 'group_w_first'
        viewer.save(update_fields=['user_group'])

        call_command('credit_wit_bot_audit', '--user', viewer.username, '--phase', '1', '--pts', '10')
        call_command('credit_wit_bot_audit', '--user', viewer.username, '--phase', '2', '--pts', '12')
        call_command('credit_wit_bot_audit', '--user', viewer.username, '--phase', '2', '--pts', '12')

        awards = PointAward.objects.filter(
            user=viewer,
            source_kind='wit_bot_audit',
        ).order_by('source_slug')
        self.assertEqual(awards.count(), 2)
        self.assertEqual(
            [(award.source_slug, award.awarded_points) for award in awards],
            [('wit_bot_audit_phase_1', 10), ('wit_bot_audit_phase_2', 12)],
        )

    def test_wit_bot_audit_titles_use_phase_version_for_group(self):
        viewer = make_user('viewer')
        viewer.user_group = 'group_q_first'
        viewer.save(update_fields=['user_group'])
        PointAward.objects.create(
            user=viewer,
            source_kind='wit_bot_audit',
            source_slug='wit_bot_audit_phase_1',
            awarded_points=10,
        )
        PointAward.objects.create(
            user=viewer,
            source_kind='wit_bot_audit',
            source_slug='wit_bot_audit_phase_2',
            awarded_points=12,
        )

        titles = [
            award['title_en']
            for award in reimbursement_state_for_user(viewer)['awards']
            if award['source_kind'] == 'wit_bot_audit'
        ]

        self.assertIn('WIT bot and boss quiz - Phase 1 (Ver.Q)', titles)
        self.assertIn('WIT bot and boss quiz - Phase 2 (Ver.W)', titles)

    def test_reimbursement_state_does_not_compute_wit_credit_from_saved_phase_state(self):
        viewer = make_user('viewer')
        viewer.user_group = 'group_q_first'
        viewer.save(update_fields=['user_group'])
        WitBotConversationState.objects.create(
            user=viewer,
            context={
                'version_q': {'audit': {'last_missing_count': 0}},
                'version_w': {'audit': {'last_missing_count': 2}},
            },
        )

        state = reimbursement_state_for_user(viewer)
        awards = [
            award for award in state['awards']
            if award['source_kind'] == 'wit_bot_audit'
        ]

        self.assertEqual(state['provisional_total'], 0)
        self.assertEqual(state['adjusted_total'], 0)
        self.assertEqual(awards, [])

    def test_reimbursement_state_does_not_synthesize_phase_two_wit_credit(self):
        viewer = make_user('viewer')
        viewer.user_group = 'group_w_first'
        viewer.save(update_fields=['user_group'])
        WitBotConversationState.objects.create(
            user=viewer,
            context={
                'version_w': {'audit': {'last_missing_count': 1}},
                'version_q': {'audit': {'last_missing_count': 0}},
            },
        )

        awards = [
            award for award in reimbursement_state_for_user(viewer)['awards']
            if award['source_kind'] == 'wit_bot_audit'
        ]

        self.assertEqual(awards, [])

    def test_manual_wit_bot_audit_award_overrides_computed_phase_credit(self):
        viewer = make_user('viewer')
        viewer.user_group = 'group_w_first'
        viewer.save(update_fields=['user_group'])
        WitBotConversationState.objects.create(
            user=viewer,
            context={'version_w': {'audit': {'last_missing_count': 0}}},
        )
        PointAward.objects.create(
            user=viewer,
            source_kind='wit_bot_audit',
            source_slug='wit_bot_audit_phase_1',
            awarded_points=10,
            adjusted_points=4,
        )

        state = reimbursement_state_for_user(viewer)
        awards = [
            award for award in state['awards']
            if award['source_kind'] == 'wit_bot_audit'
        ]

        self.assertEqual(state['provisional_total'], 4)
        self.assertEqual(state['adjusted_total'], 4)
        self.assertEqual(len(awards), 1)
        self.assertEqual(awards[0]['source_slug'], 'wit_bot_audit_phase_1')
        self.assertEqual(awards[0]['adjusted_points'], 4)

    def test_available_max_counts_both_wit_bot_audit_phases(self):
        viewer = make_user('viewer')

        self.assertEqual(available_max_for_user(viewer), 800)

    def test_app_usage_full_credit_requires_first_four_and_later_activity(self):
        viewer = make_user('app_full')
        for day in [
            datetime.date(2026, 5, 4),
            datetime.date(2026, 5, 5),
            datetime.date(2026, 5, 6),
            datetime.date(2026, 5, 7),
            datetime.date(2026, 5, 8),
            datetime.date(2026, 5, 10),
        ]:
            self._note_on(viewer, day)

        award, metrics, status = sync_app_usage_award_for_user(viewer, 1)

        self.assertEqual(metrics.points, 50)
        self.assertEqual(status, 'created')
        self.assertEqual(award.source_kind, 'app_usage')
        self.assertEqual(award.source_slug, 'app_usage_phase_1')
        self.assertEqual(award.awarded_points, 50)

    def test_app_usage_partial_credit_requires_core_app_use(self):
        viewer = make_user('app_partial')
        self._checkin_post_on(viewer, datetime.date(2026, 5, 4))
        self._checkin_post_on(viewer, datetime.date(2026, 5, 8))

        metrics = app_usage_metrics_for_user(viewer, 1)

        self.assertEqual(metrics.points, 20)

    def test_app_usage_does_not_credit_friend_setup_only(self):
        viewer = make_user('friend_only')
        other = make_user('friend_other')
        request = FriendRequest.objects.create(requester=viewer, requestee=other, accepted=True)
        self._set_created_at(request, datetime.date(2026, 5, 4))
        FriendRequest.objects.filter(pk=request.pk).update(
            updated_at=datetime.datetime(
                2026, 5, 8, 12, tzinfo=datetime.timezone.utc,
            ),
        )
        evaluation = FriendEvaluation.objects.create(
            evaluator=viewer,
            evaluated_user=other,
            friend_request=request,
            closeness=3,
        )
        self._set_created_at(evaluation, datetime.date(2026, 5, 8))

        award, metrics, status = sync_app_usage_award_for_user(viewer, 1)

        self.assertEqual(metrics.active_days, 2)
        self.assertEqual(metrics.core_event_count, 0)
        self.assertEqual(metrics.points, 0)
        self.assertIsNone(award)
        self.assertEqual(status, 'skipped')

    def test_app_usage_credit_upgrades_partial_to_full(self):
        viewer = make_user('app_upgrade')
        self._note_on(viewer, datetime.date(2026, 5, 4))
        self._note_on(viewer, datetime.date(2026, 5, 8))

        award, _metrics, status = sync_app_usage_award_for_user(viewer, 1)
        self.assertEqual(status, 'created')
        self.assertEqual(award.awarded_points, 20)

        for day in [
            datetime.date(2026, 5, 5),
            datetime.date(2026, 5, 6),
            datetime.date(2026, 5, 7),
            datetime.date(2026, 5, 10),
        ]:
            self._note_on(viewer, day)

        award, metrics, status = sync_app_usage_award_for_user(viewer, 1)

        self.assertEqual(metrics.points, 50)
        self.assertEqual(status, 'upgraded')
        award.refresh_from_db()
        self.assertEqual(award.awarded_points, 50)

    def test_app_usage_sync_uses_replacement_participant_cohort(self):
        User = get_user_model()
        User.objects.create(id=63, username='included_63', email='included_63@x.com')
        User.objects.create(id=64, username='excluded_64', email='excluded_64@x.com')
        User.objects.create(id=65, username='included_65', email='included_65@x.com')
        User.objects.create(id=114, username='replacement_114', email='replacement_114@x.com')

        rows = sync_app_usage_awards(phase=1, dry_run=True)
        usernames = {row['user'].username for row in rows}

        self.assertIn('included_63', usernames)
        self.assertNotIn('excluded_64', usernames)
        self.assertIn('included_65', usernames)
        self.assertIn('replacement_114', usernames)
