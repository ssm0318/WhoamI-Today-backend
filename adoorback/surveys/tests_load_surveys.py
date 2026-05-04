import tempfile
from pathlib import Path

import yaml
from django.core.management import call_command
from django.test import TestCase

from surveys.models import Survey


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
