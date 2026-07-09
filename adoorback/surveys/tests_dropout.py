import json

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from surveys.models import DropoutSurveyDraft, DropoutSurveyResponse


User = get_user_model()


class DropoutSurveyLookupTests(APITestCase):
    def setUp(self):
        self.w_first = User.objects.create(
            id=8,
            username='phasew',
            email='phasew@example.com',
            user_group='group_w_first',
            current_ver='version_q',
        )
        self.q_first = User.objects.create(
            id=9,
            username='phaseq',
            email='phaseq@example.com',
            user_group='group_q_first',
            current_ver='version_w',
        )
        self.replaced = User.objects.create(
            id=64,
            username='replaced',
            email='replaced@example.com',
            user_group='group_q_first',
        )
        self.replacement = User.objects.create(
            id=114,
            username='replacement',
            email='replacement@example.com',
            user_group='group_w_first',
        )
        self.out_of_cohort = User.objects.create(
            id=123,
            username='outside',
            email='outside@example.com',
            user_group='group_q_first',
        )

    def lookup(self, identifier):
        return self.client.post(
            '/api/surveys/dropout/context/',
            {'identifier': identifier},
            format='json',
        )

    def assert_no_raw_email(self, payload, *emails):
        raw = json.dumps(payload)
        for email in emails:
            self.assertNotIn(email, raw)

    def test_lookup_by_username_returns_phase_context_without_email(self):
        response = self.lookup('phasew')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['matched'])
        self.assertTrue(data['lookup_token'])
        self.assertEqual(data['matched_identifier_type'], 'username')
        self.assertEqual(data['participant']['username'], 'phasew')
        self.assertEqual(data['phases']['phase1']['version'], 'version_w')
        self.assertEqual(data['phases']['phase1']['version_label'], 'Ver.W')
        self.assertEqual(data['phases']['phase2']['version'], 'version_q')
        self.assertEqual(data['phases']['phase2']['version_label'], 'Ver.Q')
        self.assert_no_raw_email(data, self.w_first.email)

    def test_lookup_by_email_is_case_insensitive_and_returns_q_first_context(self):
        response = self.lookup('PHASEQ@EXAMPLE.COM')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['matched'])
        self.assertEqual(data['matched_identifier_type'], 'email')
        self.assertEqual(data['phases']['phase1']['version'], 'version_q')
        self.assertEqual(data['phases']['phase2']['version'], 'version_w')
        self.assert_no_raw_email(data, self.q_first.email)

    def test_lookup_rejects_non_cohort_and_replaced_participants_as_unmatched(self):
        for identifier in ['outside', 'replaced@example.com']:
            with self.subTest(identifier=identifier):
                response = self.lookup(identifier)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                data = response.json()
                self.assertFalse(data['matched'])
                self.assertTrue(data['lookup_token'])
                self.assertIsNone(data['participant'])
                self.assertEqual(data['matched_identifier_type'], 'unmatched')
                self.assertEqual(data['phases']['phase1']['version'], '')
                self.assert_no_raw_email(data, 'outside@example.com', 'replaced@example.com')

    def test_lookup_includes_replacement_participant(self):
        response = self.lookup('replacement@example.com')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['matched'])
        self.assertEqual(data['participant']['username'], 'replacement')
        self.assertEqual(data['matched_identifier_type'], 'email')
        self.assert_no_raw_email(data, self.replacement.email)


class DropoutSurveyResponseTests(APITestCase):
    def setUp(self):
        self.participant = User.objects.create(
            id=8,
            username='phasew',
            email='phasew@example.com',
            user_group='group_w_first',
        )

    def lookup_token(self, identifier):
        response = self.client.post(
            '/api/surveys/dropout/context/',
            {'identifier': identifier},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()['lookup_token']

    def test_submit_with_signed_lookup_token_stores_matched_response(self):
        token = self.lookup_token('phasew')
        payload = {
            'lookup_token': token,
            'answers': {
                'phase1_participation': 'stopped',
                'phase1_reasons': [
                    'Exams, finals, or assignments',
                    'Bugs, glitches, or login/loading problems',
                ],
                'phase1_reasons_by_group': {
                    'busy': ['Exams, finals, or assignments'],
                    'app': ['Bugs, glitches, or login/loading problems'],
                },
                'phase1_comment': '',
                'phase2_participation': 'stopped',
                'phase2_same_as_phase1': True,
                'phase2_reasons': [
                    'Exams, finals, or assignments',
                    'Bugs, glitches, or login/loading problems',
                ],
                'phase2_reasons_by_group': {
                    'busy': ['Exams, finals, or assignments'],
                    'app': ['Bugs, glitches, or login/loading problems'],
                },
                'phase2_comment': '',
                'feature_preference': 'Ver.Q',
                'version_comment': '',
                'concerns': ['None'],
                'concerns_comment': '',
                'final_comment': '',
            },
        }

        response = self.client.post(
            '/api/surveys/dropout/responses/',
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stored = DropoutSurveyResponse.objects.get()
        self.assertEqual(stored.user, self.participant)
        self.assertEqual(stored.matched_identifier_type, 'username')
        self.assertEqual(stored.user_group, 'group_w_first')
        self.assertEqual(stored.phase1_version, 'version_w')
        self.assertEqual(stored.phase2_version, 'version_q')
        self.assertEqual(stored.answers, payload['answers'])
        self.assertNotIn(self.participant.email, json.dumps(response.json()))

    def test_unmatched_lookup_token_can_submit_without_user(self):
        token = self.lookup_token('unknown@example.com')
        payload = {
            'lookup_token': token,
            'answers': {
                'phase1_participation': 'did_not_start',
                'phase2_participation': 'did_not_start',
                'open_comment': 'I never got around to it.',
            },
        }

        response = self.client.post(
            '/api/surveys/dropout/responses/',
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stored = DropoutSurveyResponse.objects.get()
        self.assertIsNone(stored.user)
        self.assertEqual(stored.matched_identifier_type, 'unmatched')
        self.assertEqual(stored.user_group, '')
        self.assertEqual(stored.identifier_hash, stored.lookup_metadata['identifier_hash'])
        self.assertNotIn('unknown@example.com', json.dumps(response.json()))

    def test_submit_rejects_invalid_lookup_token(self):
        response = self.client.post(
            '/api/surveys/dropout/responses/',
            {'lookup_token': 'not-a-token', 'answers': {'phase1_participation': 'stopped'}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DropoutSurveyResponse.objects.exists())

    def test_draft_save_and_load_round_trip(self):
        token = self.lookup_token('phasew')
        draft = {'radios': {'phase1_participation': 'used_less'}, 'checks': {}, 'texts': {}}

        save = self.client.post(
            '/api/surveys/dropout/draft/',
            {'lookup_token': token, 'draft': draft},
            format='json',
        )
        self.assertEqual(save.status_code, status.HTTP_200_OK)
        self.assertTrue(save.json()['saved'])
        self.assertEqual(DropoutSurveyDraft.objects.count(), 1)

        load = self.client.post(
            '/api/surveys/dropout/draft/load/',
            {'lookup_token': token},
            format='json',
        )
        self.assertEqual(load.status_code, status.HTTP_200_OK)
        self.assertEqual(load.json()['draft'], draft)

    def test_draft_save_is_idempotent_per_identifier(self):
        token = self.lookup_token('phasew')
        for text in ['first', 'second']:
            self.client.post(
                '/api/surveys/dropout/draft/',
                {'lookup_token': token, 'draft': {'texts': {'final_comment': text}}},
                format='json',
            )
        self.assertEqual(DropoutSurveyDraft.objects.count(), 1)
        load = self.client.post(
            '/api/surveys/dropout/draft/load/',
            {'lookup_token': token},
            format='json',
        )
        self.assertEqual(load.json()['draft']['texts']['final_comment'], 'second')

    def test_draft_cleared_after_response_submitted(self):
        token = self.lookup_token('phasew')
        self.client.post(
            '/api/surveys/dropout/draft/',
            {'lookup_token': token, 'draft': {'texts': {'final_comment': 'wip'}}},
            format='json',
        )
        self.assertEqual(DropoutSurveyDraft.objects.count(), 1)

        submit = self.client.post(
            '/api/surveys/dropout/responses/',
            {'lookup_token': token, 'answers': {'phase1_participation': 'stopped'}},
            format='json',
        )
        self.assertEqual(submit.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DropoutSurveyDraft.objects.count(), 0)

    def test_draft_load_with_invalid_token_returns_none(self):
        load = self.client.post(
            '/api/surveys/dropout/draft/load/',
            {'lookup_token': 'not-a-token'},
            format='json',
        )
        self.assertEqual(load.status_code, status.HTTP_200_OK)
        self.assertIsNone(load.json()['draft'])
