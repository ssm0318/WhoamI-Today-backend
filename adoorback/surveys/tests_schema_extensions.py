"""Tests for the long-form study schema extensions.

Covers:
  - new question types (likert_3/4/6/7, likert_5_na, display_only)
  - per-likert-variant aggregation ranges in AggregatedLikertStrategy
  - N/A sentinel exclusion from scoring
  - display_only skipped from group_panels
  - SurveyQuestion.clean() validations
  - scoring registry: register/get/list, default formula, rsq_brief_weighted
  - load_surveys: _include directive (single + nested + cycle), anchor-only
    skip, slug-uniqueness rejection, new-field parsing
"""
from __future__ import annotations

import textwrap
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase

from surveys.aggregation import (
    AggregatedLikertStrategy,
    OptionCountsStrategy,
    SliderHistogramStrategy,
    _likert_range,
    group_panels,
)
from surveys.models import (
    DISPLAY_ONLY,
    LIKERT_3,
    LIKERT_5,
    LIKERT_5_NA,
    LIKERT_7,
    LIKERT_RANGES,
    NA_SENTINEL,
    RESULT_AGGREGATED_LIKERT,
    RESULT_OPTION_COUNTS,
    RESULT_SCALE_SCORE_HISTOGRAM,
    SINGLE_CHOICE,
    Survey,
    SurveyAnswer,
    SurveyOption,
    SurveyQuestion,
    SurveyResponse,
    UserSurveyEmbeddedData,
)
from surveys.scoring import (
    get_formula,
    list_formulas,
    register_formula,
    score_response,
)


User = get_user_model()


# ---------------------------------------------------------------------------
# Model-level: SurveyQuestion.clean() validation rules
# ---------------------------------------------------------------------------
class SurveyQuestionCleanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.survey = Survey.objects.create(slug='clean_tests', title_en='T', title_ko='T')

    def _make(self, **kwargs):
        defaults = dict(
            survey=self.survey,
            order=1,
            type=LIKERT_5,
            prompt_en='p',
            prompt_ko='p',
        )
        defaults.update(kwargs)
        return SurveyQuestion(**defaults)

    def test_display_only_cannot_be_required(self):
        q = self._make(type=DISPLAY_ONLY, required=True)
        with self.assertRaises(ValidationError):
            q.clean()

    def test_display_only_with_required_false_passes(self):
        q = self._make(type=DISPLAY_ONLY, required=False, content_en='hello')
        q.clean()  # no raise

    def test_embedded_data_requires_slug(self):
        q = self._make(embedded_data=True, slug='')
        with self.assertRaises(ValidationError):
            q.clean()

    def test_embedded_data_with_slug_passes(self):
        q = self._make(embedded_data=True, slug='my_q')
        q.clean()  # no raise


# ---------------------------------------------------------------------------
# Aggregation: likert range parameterization + N/A skip + display_only skip
# ---------------------------------------------------------------------------
class LikertVariantAggregationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username='u', email='u@x.com')
        cls.viewer = User.objects.create(username='v', email='v@x.com')

    def test_likert_range_returns_correct_bounds(self):
        s = Survey.objects.create(slug='lr', title_en='T', title_ko='T')
        q3 = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_3, prompt_en='p', prompt_ko='p'
        )
        q7 = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_7, prompt_en='p', prompt_ko='p'
        )
        self.assertEqual(_likert_range(q3), (1, 3))
        self.assertEqual(_likert_range(q7), (1, 7))

    def test_likert_range_falls_back_to_5_for_unknown(self):
        s = Survey.objects.create(slug='lr2', title_en='T', title_ko='T')
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=SINGLE_CHOICE, prompt_en='p', prompt_ko='p'
        )
        # Defensive default — non-likert types fall back to (1, 5).
        self.assertEqual(_likert_range(q), (1, 5))

    def test_aggregated_likert_uses_per_question_range(self):
        """Score range = sum of each question's individual (min, max).

        Panel of (likert_3 + likert_7) → min 1+1=2, max 3+7=10.
        """
        s = Survey.objects.create(slug='mix', title_en='T', title_ko='T')
        q3 = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_3, slug='q3',
            prompt_en='p', prompt_ko='p', result_group='g',
        )
        q7 = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_7, slug='q7',
            prompt_en='p', prompt_ko='p', result_group='g',
        )
        # Viewer responded with 2 (mid of 1-3) and 5 (mid of 1-7) → score 7.
        resp = SurveyResponse.objects.create(user=self.viewer, survey=s)
        SurveyAnswer.objects.create(response=resp, question=q3, value=2)
        SurveyAnswer.objects.create(response=resp, question=q7, value=5)

        out = AggregatedLikertStrategy().build(s, [q3, q7], [self.viewer.id], self.viewer.id)
        self.assertEqual(out['min_score'], 2)
        self.assertEqual(out['max_score'], 10)
        self.assertEqual(out['user_score'], 7)

    def test_aggregated_likert_skips_na_sentinel(self):
        """likert_5_na N/A picks are skipped — NOT counted as 0."""
        s = Survey.objects.create(slug='na', title_en='T', title_ko='T')
        q1 = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5_NA, slug='a',
            prompt_en='p', prompt_ko='p', result_group='g',
        )
        q2 = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5_NA, slug='b',
            prompt_en='p', prompt_ko='p', result_group='g',
        )
        resp = SurveyResponse.objects.create(user=self.viewer, survey=s)
        SurveyAnswer.objects.create(response=resp, question=q1, value=4)
        SurveyAnswer.objects.create(response=resp, question=q2, value=NA_SENTINEL)

        out = AggregatedLikertStrategy().build(s, [q1, q2], [self.viewer.id], self.viewer.id)
        # q2 is skipped — only q1 contributes 4.
        self.assertEqual(out['user_score'], 4)

    def test_aggregated_likert_reverse_scoring_uses_per_question_range(self):
        """reverse_scored on likert_7 should invert via (7+1) - v, not 6 - v."""
        s = Survey.objects.create(slug='rev', title_en='T', title_ko='T')
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_7, slug='r',
            prompt_en='p', prompt_ko='p', reverse_scored=True, result_group='g',
        )
        resp = SurveyResponse.objects.create(user=self.viewer, survey=s)
        SurveyAnswer.objects.create(response=resp, question=q, value=2)

        out = AggregatedLikertStrategy().build(s, [q], [self.viewer.id], self.viewer.id)
        # 2 inverted through likert_7 = (7+1) - 2 = 6.
        self.assertEqual(out['user_score'], 6)

    def test_group_panels_skips_display_only(self):
        s = Survey.objects.create(slug='dpo', title_en='T', title_ko='T')
        SurveyQuestion.objects.create(
            survey=s, order=1, type=DISPLAY_ONLY, required=False,
            content_en='hello', prompt_en='', prompt_ko='',
        )
        q = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        panels = group_panels(s)
        # Only the likert_5 question makes it into the panels.
        self.assertEqual(len(panels), 1)
        all_panel_questions = [pq for _, qs in panels for pq in qs]
        self.assertEqual(all_panel_questions, [q])


# ---------------------------------------------------------------------------
# Scoring registry: register/get/list, default formula, rsq_brief_weighted
# ---------------------------------------------------------------------------
class ScoringRegistryTests(TestCase):
    def test_built_in_formulas_registered(self):
        names = list_formulas()
        self.assertIn('rsq_brief_weighted', names)

    def test_register_duplicate_raises(self):
        @register_formula('test_one_off_unique_xyz')
        def _f(survey, response):
            return 0
        with self.assertRaises(ValueError):
            register_formula('test_one_off_unique_xyz')(lambda s, r: 0)

    def test_get_unknown_raises_keyerror(self):
        with self.assertRaises(KeyError):
            get_formula('definitely_not_registered_anywhere')

    def test_default_score_sums_with_reverse(self):
        u = User.objects.create(username='ds', email='ds@x.com')
        s = Survey.objects.create(slug='ds', title_en='T', title_ko='T')
        q1 = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, slug='a',
            prompt_en='p', prompt_ko='p', reverse_scored=False,
        )
        q2 = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5, slug='b',
            prompt_en='p', prompt_ko='p', reverse_scored=True,
        )
        r = SurveyResponse.objects.create(user=u, survey=s)
        SurveyAnswer.objects.create(response=r, question=q1, value=4)
        SurveyAnswer.objects.create(response=r, question=q2, value=2)
        # q1 contributes 4, q2 inverted = (5+1) - 2 = 4 → total 8.
        self.assertEqual(score_response(s, r), 8)

    def test_default_score_skips_na(self):
        u = User.objects.create(username='dsna', email='dsna@x.com')
        s = Survey.objects.create(slug='dsna', title_en='T', title_ko='T')
        q1 = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5_NA, slug='a',
            prompt_en='p', prompt_ko='p',
        )
        q2 = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5_NA, slug='b',
            prompt_en='p', prompt_ko='p',
        )
        r = SurveyResponse.objects.create(user=u, survey=s)
        SurveyAnswer.objects.create(response=r, question=q1, value=3)
        SurveyAnswer.objects.create(response=r, question=q2, value=NA_SENTINEL)
        self.assertEqual(score_response(s, r), 3)

    def test_default_score_returns_none_when_no_scorable_items(self):
        u = User.objects.create(username='nones', email='nones@x.com')
        s = Survey.objects.create(slug='nones', title_en='T', title_ko='T')
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5_NA, slug='a',
            prompt_en='p', prompt_ko='p',
        )
        r = SurveyResponse.objects.create(user=u, survey=s)
        SurveyAnswer.objects.create(response=r, question=q, value=NA_SENTINEL)
        self.assertIsNone(score_response(s, r))

    def test_default_score_respects_score_components(self):
        """When score_components is set, only those slugs contribute."""
        u = User.objects.create(username='sc', email='sc@x.com')
        s = Survey.objects.create(
            slug='sc', title_en='T', title_ko='T',
            score_components=['a'],
        )
        q1 = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, slug='a',
            prompt_en='p', prompt_ko='p',
        )
        q2 = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5, slug='b',
            prompt_en='p', prompt_ko='p',
        )
        r = SurveyResponse.objects.create(user=u, survey=s)
        SurveyAnswer.objects.create(response=r, question=q1, value=4)
        SurveyAnswer.objects.create(response=r, question=q2, value=5)
        # Only q1 (slug=a) is in score_components → score is 4.
        self.assertEqual(score_response(s, r), 4)

    def test_score_response_dispatches_to_score_formula(self):
        u = User.objects.create(username='sf', email='sf@x.com')
        s = Survey.objects.create(
            slug='sf', title_en='T', title_ko='T',
            score_formula='rsq_brief_weighted',
        )
        # Two RSQ situations, each (concern, expect):
        #   sit 1: concern=4, expect=2 → 4 * (7-2) = 20
        #   sit 2: concern=3, expect=5 → 3 * (7-5) = 6
        # Total = 26
        for n, c, e in [(1, 4, 2), (2, 3, 5)]:
            qc = SurveyQuestion.objects.create(
                survey=s, order=2 * n - 1, type=LIKERT_7, slug=f'rsq_{n}_concern',
                prompt_en='p', prompt_ko='p',
            )
            qe = SurveyQuestion.objects.create(
                survey=s, order=2 * n, type=LIKERT_7, slug=f'rsq_{n}_expect',
                prompt_en='p', prompt_ko='p',
            )
            r, _ = SurveyResponse.objects.get_or_create(user=u, survey=s)
            SurveyAnswer.objects.create(response=r, question=qc, value=c)
            SurveyAnswer.objects.create(response=r, question=qe, value=e)
        r = SurveyResponse.objects.get(user=u, survey=s)
        self.assertEqual(score_response(s, r), 26)


# ---------------------------------------------------------------------------
# load_surveys: _include directive + anchor-only skip + new fields + slug
# uniqueness
# ---------------------------------------------------------------------------
def _write_yaml(tmpdir: Path, name: str, body: str) -> Path:
    path = tmpdir / name
    path.write_text(textwrap.dedent(body), encoding='utf-8')
    return path


class LoadSurveysIncludeTests(TestCase):
    def test_anchor_only_entries_are_skipped(self):
        """Top-level entries with slug starting `_` are anchor-only — not persisted."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'a.yaml', """
                - slug: _shared_block
                  title: { en: 'anchors only' }

                - slug: real_survey
                  title: { en: 'Real Survey' }
                  questions:
                    - order: 1
                      type: likert_5
                      prompt: { en: 'p' }
            """)
            out = StringIO()
            call_command('load_surveys', str(yml), stdout=out)
        self.assertFalse(Survey.objects.filter(slug='_shared_block').exists())
        self.assertTrue(Survey.objects.filter(slug='real_survey').exists())

    def test_include_directive_splices_anchored_list(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'b.yaml', """
                - slug: _block_anchor_holder
                  title: { en: 'anchor only' }
                  questions: &shared_block
                    - order: 1
                      slug: shared_q1
                      type: likert_5
                      prompt: { en: 'sq1' }
                    - order: 2
                      slug: shared_q2
                      type: likert_5
                      prompt: { en: 'sq2' }

                - slug: my_survey
                  title: { en: 'M' }
                  questions:
                    - order: 1
                      slug: header
                      type: display_only
                      required: false
                      content: { en: '# Welcome' }
                    - _include: shared_block
                    - order: 99
                      slug: my_specific
                      type: likert_5
                      prompt: { en: 'spec' }
            """)
            out = StringIO()
            call_command('load_surveys', str(yml), stdout=out)
        s = Survey.objects.get(slug='my_survey')
        slugs = list(s.questions.order_by('order').values_list('slug', flat=True))
        # Header + spliced shared_q1, shared_q2 + my_specific = 4 questions.
        self.assertEqual(slugs, ['header', 'shared_q1', 'shared_q2', 'my_specific'])
        # And `order` is renumbered absolutely 1..4 (block-relative orders dropped).
        orders = list(s.questions.order_by('order').values_list('order', flat=True))
        self.assertEqual(orders, [1, 2, 3, 4])

    def test_include_unknown_anchor_raises(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'c.yaml', """
                - slug: my_survey
                  title: { en: 'M' }
                  questions:
                    - _include: nope_no_such_anchor
            """)
            with self.assertRaises(CommandError):
                call_command('load_surveys', str(yml))

    def test_duplicate_slug_within_survey_rejected(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'd.yaml', """
                - slug: dupes
                  title: { en: 'D' }
                  questions:
                    - { order: 1, slug: same, type: likert_5, prompt: { en: 'p' } }
                    - { order: 2, slug: same, type: likert_5, prompt: { en: 'p' } }
            """)
            with self.assertRaises(CommandError):
                call_command('load_surveys', str(yml))

    def test_empty_slugs_do_not_collide(self):
        """Multiple display_only blocks with no slug are fine — empty != duplicate."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'e.yaml', """
                - slug: empties
                  title: { en: 'E' }
                  questions:
                    - { order: 1, type: display_only, required: false, content: { en: 'a' } }
                    - { order: 2, type: display_only, required: false, content: { en: 'b' } }
                    - { order: 3, type: likert_5, slug: real, prompt: { en: 'p' } }
            """)
            call_command('load_surveys', str(yml), stdout=StringIO())
        s = Survey.objects.get(slug='empties')
        self.assertEqual(s.questions.count(), 3)

    def test_new_fields_parsed_correctly(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'f.yaml', """
                - slug: with_extensions
                  title: { en: 'X' }
                  tokens:
                    phase_label: 'Phase 1'
                  repeatable: true
                  result_kind: scale_score_histogram
                  score_formula: rsq_brief_weighted
                  score_components: ['a', 'b']
                  serving_condition:
                    skip_if_user_embedded_data:
                      habit_platform: 'none'
                  questions:
                    - order: 1
                      slug: q1
                      type: likert_5_na
                      prompt: { en: 'p' }
                      description: { en: 'desc' }
                      placeholder: { en: 'ph' }
                      min_length: 10
                      min_length_warning: { en: 'too short' }
                      required: false
                      na_option: { en: 'N/A' }
                      embedded_data: false
                      conditional_display:
                        depends_on: q0
                        show_when_value: 1
            """)
            call_command('load_surveys', str(yml), stdout=StringIO())
        s = Survey.objects.get(slug='with_extensions')
        self.assertEqual(s.tokens, {'phase_label': 'Phase 1'})
        self.assertTrue(s.repeatable)
        self.assertEqual(s.result_kind, RESULT_SCALE_SCORE_HISTOGRAM)
        self.assertEqual(s.score_formula, 'rsq_brief_weighted')
        self.assertEqual(s.score_components, ['a', 'b'])
        self.assertEqual(
            s.serving_condition,
            {'skip_if_user_embedded_data': {'habit_platform': 'none'}},
        )
        q = s.questions.get(slug='q1')
        self.assertEqual(q.type, LIKERT_5_NA)
        self.assertEqual(q.description_en, 'desc')
        self.assertEqual(q.placeholder_en, 'ph')
        self.assertEqual(q.min_length, 10)
        self.assertEqual(q.min_length_warning_en, 'too short')
        self.assertFalse(q.required)
        self.assertEqual(q.na_option_en, 'N/A')
        self.assertEqual(
            q.conditional_display,
            {'depends_on': 'q0', 'show_when_value': 1},
        )

    def test_include_must_reference_a_list(self):
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'g.yaml', """
                - slug: _holder
                  title: { en: 'h' }
                  description: &not_a_list { en: 'just a mapping' }

                - slug: bad_include
                  title: { en: 'B' }
                  questions:
                    - _include: not_a_list
            """)
            with self.assertRaises(CommandError):
                call_command('load_surveys', str(yml))


# ---------------------------------------------------------------------------
# UserSurveyEmbeddedData model basics
# ---------------------------------------------------------------------------
class UserSurveyEmbeddedDataTests(TestCase):
    def test_unique_per_user_key(self):
        u = User.objects.create(username='ed', email='ed@x.com')
        UserSurveyEmbeddedData.objects.create(user=u, key='habit_platform', value='instagram')
        # Same (user, key) again must collide on the unique constraint.
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserSurveyEmbeddedData.objects.create(user=u, key='habit_platform', value='tiktok')
