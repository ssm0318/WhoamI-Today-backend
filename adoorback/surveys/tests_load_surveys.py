import tempfile
from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from surveys.models import Survey, SurveyAnswer, SurveyResponse


PRE_FIXTURE_PATH = Path(__file__).resolve().parent / 'fixtures' / 'pre.yaml'


SAMPLE = [
    {
        'slug': 'unit_test_a',
        'type': 'single_choice',
        'title': {'en': 'A?', 'ko': 'A?'},
        'description': {'en': 'd', 'ko': 'd'},
        'interpretation': {'en': 'i', 'ko': 'i'},
        'questions': [
            {
                'order': 1,
                'prompt': {'en': 'Pick', 'ko': '고르세요'},
                'options': [
                    {'order': 1, 'label': {'en': 'X', 'ko': 'X'}, 'value': 1},
                    {'order': 2, 'label': {'en': 'Y', 'ko': 'Y'}, 'value': 2},
                ],
            },
        ],
    },
]


class LoadSurveysCommandTests(TestCase):
    def _write_fixture(self, data):
        f = tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w', encoding='utf-8')
        yaml.safe_dump(data, f)
        f.close()
        return Path(f.name)

    def test_creates_surveys(self):
        path = self._write_fixture(SAMPLE)
        call_command('load_surveys', str(path))
        s = Survey.objects.get(slug='unit_test_a')
        self.assertEqual(s.questions.count(), 1)
        self.assertEqual(s.questions.get().options.count(), 2)
        self.assertEqual(s.title_en, 'A?')

    def test_idempotent_on_rerun(self):
        path = self._write_fixture(SAMPLE)
        call_command('load_surveys', str(path))
        call_command('load_surveys', str(path))
        self.assertEqual(Survey.objects.filter(slug='unit_test_a').count(), 1)

    def test_replace_questions_flag(self):
        path = self._write_fixture(SAMPLE)
        call_command('load_surveys', str(path))
        modified = [{
            **SAMPLE[0],
            'questions': [
                {**SAMPLE[0]['questions'][0], 'prompt': {'en': 'NEW', 'ko': 'NEW'}},
            ],
        }]
        path2 = self._write_fixture(modified)
        call_command('load_surveys', str(path2), '--replace-questions')
        s = Survey.objects.get(slug='unit_test_a')
        self.assertEqual(s.questions.get().prompt_en, 'NEW')

    def test_loader_picks_up_editable_closed_priority(self):
        """The loader must read editable / closed / priority from YAML —
        regression for the June 1 audit bug where these silently defaulted
        to False/False/0 and disabled both the editable-survey UX and the
        priority sort."""
        sample = [
            {
                'slug': 'flags_test',
                'type': 'likert_5',
                'title': {'en': 'F', 'ko': 'F'},
                'description': {'en': 'd', 'ko': 'd'},
                'interpretation': {'en': '', 'ko': ''},
                'editable': True,
                'closed': False,
                'priority': 200,
                'point_value': 25,
                'point_prereq_slug': 'flags_prereq',
                'questions': [
                    {
                        'order': 1,
                        'prompt': {'en': 'p', 'ko': 'p'},
                        'low_label': {'en': 'lo', 'ko': 'lo'},
                        'high_label': {'en': 'hi', 'ko': 'hi'},
                    },
                ],
            },
        ]
        path = self._write_fixture(sample)
        call_command('load_surveys', str(path))
        s = Survey.objects.get(slug='flags_test')
        self.assertTrue(s.editable)
        self.assertFalse(s.closed)
        self.assertEqual(s.priority, 200)
        self.assertEqual(s.point_value, 25)
        self.assertEqual(s.point_prereq_slug, 'flags_prereq')

    def test_feature_eval_w_fixture_has_two_text_followups_per_feature_without_na(self):
        call_command('load_surveys', str(PRE_FIXTURE_PATH))

        survey = Survey.objects.get(slug='feature_eval_w')
        questions = list(survey.questions.order_by('order'))
        by_slug = {q.slug: q for q in questions}
        rating_questions = [
            q for q in questions
            if q.slug.startswith('goal') and not q.slug.endswith(('_enjoy', '_dislike'))
        ]

        self.assertGreater(len(rating_questions), 0)
        for rating in rating_questions:
            self.assertEqual(rating.type, 'likert_5')
            self.assertEqual(rating.na_option_en, '')
            enjoy = by_slug.get(f'{rating.slug}_enjoy')
            dislike = by_slug.get(f'{rating.slug}_dislike')
            self.assertIsNotNone(enjoy, rating.slug)
            self.assertIsNotNone(dislike, rating.slug)
            self.assertEqual(enjoy.type, 'free_text')
            self.assertEqual(dislike.type, 'free_text')
            self.assertEqual(enjoy.order, rating.order + 1)
            self.assertEqual(dislike.order, rating.order + 2)

    def test_replace_questions_if_unanswered_updates_unanswered_existing_survey(self):
        first = self._write_fixture([
            {
                **SAMPLE[0],
                'questions': [
                    {
                        **SAMPLE[0]['questions'][0],
                        'slug': 'old_question',
                    },
                ],
            },
        ])
        call_command('load_surveys', str(first))
        second = self._write_fixture([
            {
                'slug': 'unit_test_a',
                'type': 'likert_5',
                'title': {'en': 'Updated'},
                'questions': [
                    {
                        'order': 1,
                        'slug': 'new_question',
                        'prompt': {'en': 'New question'},
                    },
                ],
            },
        ])

        call_command('load_surveys', str(second), '--replace-questions-if-unanswered')

        survey = Survey.objects.get(slug='unit_test_a')
        self.assertEqual(survey.title_en, 'Updated')
        self.assertEqual(
            list(survey.questions.values_list('slug', flat=True)),
            ['new_question'],
        )

    def test_replace_questions_if_unanswered_preserves_answered_existing_survey(self):
        User = get_user_model()
        user = User.objects.create(username='answered_user', email='answered_user@example.com')
        first = self._write_fixture([
            {
                **SAMPLE[0],
                'questions': [
                    {
                        **SAMPLE[0]['questions'][0],
                        'slug': 'old_question',
                    },
                ],
            },
        ])
        call_command('load_surveys', str(first))
        survey = Survey.objects.get(slug='unit_test_a')
        question = survey.questions.get(slug='old_question')
        response = SurveyResponse.objects.create(user=user, survey=survey)
        SurveyAnswer.objects.create(response=response, question=question, value=4)
        second = self._write_fixture([
            {
                'slug': 'unit_test_a',
                'type': 'likert_5',
                'title': {'en': 'Updated'},
                'questions': [
                    {
                        'order': 1,
                        'slug': 'new_question',
                        'prompt': {'en': 'New question'},
                    },
                ],
            },
        ])

        call_command('load_surveys', str(second), '--replace-questions-if-unanswered')

        survey.refresh_from_db()
        self.assertEqual(survey.title_en, 'Updated')
        self.assertEqual(
            list(survey.questions.order_by('order').values_list('slug', flat=True)),
            ['old_question'],
        )
