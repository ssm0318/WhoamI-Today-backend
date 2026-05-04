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
    ScaleScoreHistogramStrategy,
    SliderHistogramPairedStrategy,
    SliderHistogramStrategy,
    _likert_range,
    group_panels,
    group_panels_for_survey_level_kind,
)
from surveys.management.commands.load_surveys import (
    _preprocess_yaml_text,
    _rewrite_merge_key_to_include,
    _wrap_top_level_anchor_blocks,
)
from surveys.scheduling import get_survey_index, get_today_daily
from surveys.serializers import SurveyDetailSerializer
from surveys.tokens import build_token_map, substitute
from surveys.models import (
    CADENCE_DAILY,
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
    RESULT_SLIDER_HISTOGRAM_PAIRED,
    ScheduledSurvey,
    SINGLE_CHOICE,
    SLIDER,
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
# Survey-level result kinds: scale_score_histogram + slider_histogram_paired
# ---------------------------------------------------------------------------
class SurveyLevelResultKindTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create(username='svl', email='svl@x.com')

    def test_scale_score_histogram_groups_all_scorable_questions(self):
        s = Survey.objects.create(
            slug='ssh', title_en='S', title_ko='S',
            result_kind=RESULT_SCALE_SCORE_HISTOGRAM,
        )
        # Mix display_only (skipped), likert_5 (counted), and a hidden question.
        SurveyQuestion.objects.create(
            survey=s, order=1, type=DISPLAY_ONLY, required=False,
            content_en='intro', prompt_en='', prompt_ko='',
        )
        SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5, slug='a',
            prompt_en='p', prompt_ko='p',
        )
        SurveyQuestion.objects.create(
            survey=s, order=3, type=LIKERT_5, slug='b',
            prompt_en='p', prompt_ko='p',
        )
        SurveyQuestion.objects.create(
            survey=s, order=4, type=LIKERT_5, slug='hidden',
            prompt_en='p', prompt_ko='p', result_hidden=True,
        )
        panels = group_panels_for_survey_level_kind(s)
        self.assertEqual(len(panels), 1)
        group_key, qs = panels[0]
        self.assertEqual(group_key, '__survey__')
        # display_only and result_hidden are filtered out; the two scorable
        # likert questions remain.
        self.assertEqual([q.slug for q in qs], ['a', 'b'])

    def test_scale_score_histogram_strategy_builds_histogram(self):
        s = Survey.objects.create(
            slug='ssh2', title_en='S', title_ko='S',
            result_kind=RESULT_SCALE_SCORE_HISTOGRAM,
        )
        q1 = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, slug='a',
            prompt_en='p', prompt_ko='p',
        )
        q2 = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5, slug='b',
            prompt_en='p', prompt_ko='p',
        )
        # Two responders: viewer with score 4+5=9, another with 3+3=6.
        u2 = User.objects.create(username='svl2', email='svl2@x.com')
        for u, v1, v2 in [(self.viewer, 4, 5), (u2, 3, 3)]:
            r = SurveyResponse.objects.create(user=u, survey=s)
            SurveyAnswer.objects.create(response=r, question=q1, value=v1)
            SurveyAnswer.objects.create(response=r, question=q2, value=v2)

        out = ScaleScoreHistogramStrategy().build(
            s, [q1, q2], [self.viewer.id, u2.id], self.viewer.id,
        )
        self.assertEqual(out['min_score'], 6)
        self.assertEqual(out['max_score'], 9)
        self.assertEqual(out['user_score'], 9)
        # Bins span 6..9 — only 6 and 9 have count 1, others 0.
        scored = {b['score']: b['count'] for b in out['bins']}
        self.assertEqual(scored, {6: 1, 7: 0, 8: 0, 9: 1})

    def test_slider_histogram_paired_strategy_pairs_two_sliders(self):
        s = Survey.objects.create(
            slug='shp', title_en='S', title_ko='S',
            result_kind=RESULT_SLIDER_HISTOGRAM_PAIRED,
        )
        qx = SurveyQuestion.objects.create(
            survey=s, order=1, type=SLIDER, slug='valence',
            prompt_en='p', prompt_ko='p',
            slider_min_value=0, slider_max_value=100, result_group='mood',
        )
        qy = SurveyQuestion.objects.create(
            survey=s, order=2, type=SLIDER, slug='arousal',
            prompt_en='p', prompt_ko='p',
            slider_min_value=0, slider_max_value=100, result_group='mood',
        )
        r = SurveyResponse.objects.create(user=self.viewer, survey=s)
        SurveyAnswer.objects.create(response=r, question=qx, value=70)
        SurveyAnswer.objects.create(response=r, question=qy, value=40)

        out = SliderHistogramPairedStrategy().build(
            s, [qx, qy], [self.viewer.id], self.viewer.id,
        )
        self.assertEqual(out['x_min'], 0)
        self.assertEqual(out['x_max'], 100)
        self.assertEqual(out['user_point'], {'x': 70, 'y': 40})
        self.assertEqual(out['points'], [{'x': 70, 'y': 40}])

    def test_slider_histogram_paired_strategy_skips_unpaired_responses(self):
        """A response that has only the X-slider answered (no Y) is excluded —
        we can't plot a half-pair."""
        s = Survey.objects.create(slug='shp2', title_en='S', title_ko='S')
        qx = SurveyQuestion.objects.create(
            survey=s, order=1, type=SLIDER, slug='vx',
            prompt_en='p', prompt_ko='p',
            slider_min_value=0, slider_max_value=10, result_group='m',
        )
        qy = SurveyQuestion.objects.create(
            survey=s, order=2, type=SLIDER, slug='vy',
            prompt_en='p', prompt_ko='p',
            slider_min_value=0, slider_max_value=10, result_group='m',
        )
        u2 = User.objects.create(username='svl3', email='svl3@x.com')
        # u2: only x answered.
        r2 = SurveyResponse.objects.create(user=u2, survey=s)
        SurveyAnswer.objects.create(response=r2, question=qx, value=5)
        # viewer: full pair.
        r1 = SurveyResponse.objects.create(user=self.viewer, survey=s)
        SurveyAnswer.objects.create(response=r1, question=qx, value=3)
        SurveyAnswer.objects.create(response=r1, question=qy, value=7)

        out = SliderHistogramPairedStrategy().build(
            s, [qx, qy], [self.viewer.id, u2.id], self.viewer.id,
        )
        # Only the viewer's full pair is returned.
        self.assertEqual(out['points'], [{'x': 3, 'y': 7}])


# ---------------------------------------------------------------------------
# Scheduling: serving_condition + version routing + weekend skip
# ---------------------------------------------------------------------------
class SchedulingFiltersTests(TestCase):
    def setUp(self):
        from datetime import date as _date
        # Pin a known weekday for the daily window. Pick a Wednesday (May 6,
        # 2026) so we can also run a separate Saturday test.
        self.today = _date(2026, 5, 6)  # Wednesday
        self.user_w = User.objects.create(
            username='w', email='w@x.com', user_group='group_w_first',
        )
        self.user_q = User.objects.create(
            username='q', email='q@x.com', user_group='group_q_first',
        )

    def _schedule(self, survey, day, seq, cadence=CADENCE_DAILY):
        return ScheduledSurvey.objects.create(
            survey=survey, cadence=cadence,
            window_start=day, window_end=day,
            allow_late=False, sequence_index=seq,
        )

    def test_version_routing_w_user_only_sees_w_survey(self):
        from unittest.mock import patch

        sw = Survey.objects.create(slug='mid_study_w', title_en='W', title_ko='W')
        sq = Survey.objects.create(slug='mid_study_q', title_en='Q', title_ko='Q')
        SurveyQuestion.objects.create(survey=sw, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        SurveyQuestion.objects.create(survey=sq, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        self._schedule(sw, self.today, seq=1001)
        self._schedule(sq, self.today, seq=1002)
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            res = get_survey_index(self.user_w)
            slugs_w = [r.survey.slug for r in res['available_now']]
        self.assertEqual(slugs_w, ['mid_study_w'])

    def test_version_routing_q_user_only_sees_q_survey(self):
        from unittest.mock import patch

        sw = Survey.objects.create(slug='post_study_w', title_en='W', title_ko='W')
        sq = Survey.objects.create(slug='post_study_q', title_en='Q', title_ko='Q')
        SurveyQuestion.objects.create(survey=sw, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        SurveyQuestion.objects.create(survey=sq, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        self._schedule(sw, self.today, seq=1003)
        self._schedule(sq, self.today, seq=1004)
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            res = get_survey_index(self.user_q)
            slugs_q = [r.survey.slug for r in res['available_now']]
        self.assertEqual(slugs_q, ['post_study_q'])

    def test_weekend_skip_for_non_daily_base_dailies(self):
        from datetime import date as _date
        from unittest.mock import patch

        saturday = _date(2026, 5, 9)  # Saturday
        sotd = Survey.objects.create(slug='sotd_d05_rsq', title_en='S', title_ko='S')
        diary = Survey.objects.create(slug='daily_base', title_en='D', title_ko='D')
        SurveyQuestion.objects.create(survey=sotd, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        SurveyQuestion.objects.create(survey=diary, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        self._schedule(sotd, saturday, seq=2001)
        self._schedule(diary, saturday, seq=2002)
        with patch('surveys.scheduling._today_la_7am', return_value=saturday):
            res = get_survey_index(self.user_w)
            slugs = sorted(r.survey.slug for r in res['available_now'])
        # SOTD is hidden on Saturday; daily_base survives.
        self.assertEqual(slugs, ['daily_base'])

    def test_serving_condition_skips_when_user_data_matches(self):
        from unittest.mock import patch

        s = Survey.objects.create(
            slug='sotd_d15_shi', title_en='S', title_ko='S',
            serving_condition={
                'skip_if_user_embedded_data': {'habit_platform': 'none'},
            },
        )
        SurveyQuestion.objects.create(survey=s, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        self._schedule(s, self.today, seq=3001)
        # User picked "none" → skip rule fires.
        UserSurveyEmbeddedData.objects.create(
            user=self.user_w, key='habit_platform', value='none',
        )
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            res = get_survey_index(self.user_w)
        self.assertEqual(res['available_now'], [])

    def test_serving_condition_keeps_when_user_data_differs(self):
        from unittest.mock import patch

        s = Survey.objects.create(
            slug='sotd_d15_shi', title_en='S', title_ko='S',
            serving_condition={
                'skip_if_user_embedded_data': {'habit_platform': 'none'},
            },
        )
        SurveyQuestion.objects.create(survey=s, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        self._schedule(s, self.today, seq=3002)
        UserSurveyEmbeddedData.objects.create(
            user=self.user_w, key='habit_platform', value='instagram',
        )
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            res = get_survey_index(self.user_w)
            slugs = [r.survey.slug for r in res['available_now']]
        self.assertEqual(slugs, ['sotd_d15_shi'])

    def test_get_today_daily_picks_routed_survey_for_w_user(self):
        from unittest.mock import patch

        sw = Survey.objects.create(slug='mid_study_w', title_en='W', title_ko='W')
        sq = Survey.objects.create(slug='mid_study_q', title_en='Q', title_ko='Q')
        SurveyQuestion.objects.create(survey=sw, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        SurveyQuestion.objects.create(survey=sq, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        self._schedule(sw, self.today, seq=4001)
        self._schedule(sq, self.today, seq=4002)
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            picked = get_today_daily(self.user_w)
        self.assertIsNotNone(picked)
        self.assertEqual(picked.survey.slug, 'mid_study_w')


# ---------------------------------------------------------------------------
# Token substitution
# ---------------------------------------------------------------------------
class TokenSubstitutionTests(TestCase):
    def test_substitute_replaces_known_tokens(self):
        out = substitute(
            'Welcome to {{phase_label}} ({{phase_window}})',
            {'phase_label': 'Phase 1', 'phase_window': 'May 4-17'},
        )
        self.assertEqual(out, 'Welcome to Phase 1 (May 4-17)')

    def test_substitute_leaves_unknown_tokens_literal(self):
        out = substitute('hi {{nope}}', {'phase': 'P1'})
        self.assertEqual(out, 'hi {{nope}}')

    def test_substitute_handles_whitespace_inside_braces(self):
        out = substitute('hi {{ name }}', {'name': 'world'})
        self.assertEqual(out, 'hi world')

    def test_substitute_passthrough_on_empty_or_non_string(self):
        self.assertEqual(substitute('', {'a': 'b'}), '')
        self.assertIsNone(substitute(None, {'a': 'b'}))

    def test_build_token_map_merges_survey_and_user(self):
        # `User.objects.create` produces an authenticated User instance —
        # is_authenticated is a property True when the user isn't anonymous,
        # which a real User from the DB always is.
        u = User.objects.create(username='tk', email='tk@x.com')
        s = Survey.objects.create(
            slug='tk', title_en='T', title_ko='T',
            tokens={'phase_label': 'Phase 1'},
        )
        UserSurveyEmbeddedData.objects.create(
            user=u, key='habit_platform_label', value='Instagram',
        )
        out = build_token_map(s, viewer=u)
        self.assertEqual(out['phase_label'], 'Phase 1')
        self.assertEqual(out['habit_platform_label'], 'Instagram')

    def test_build_token_map_survey_wins_on_collision(self):
        u = User.objects.create(username='tk2', email='tk2@x.com')
        s = Survey.objects.create(
            slug='tk2', title_en='T', title_ko='T',
            tokens={'name': 'survey_value'},
        )
        UserSurveyEmbeddedData.objects.create(
            user=u, key='name', value='user_value',
        )
        out = build_token_map(s, viewer=u)
        self.assertEqual(out['name'], 'survey_value')

    def test_build_token_map_anonymous_viewer(self):
        from django.contrib.auth.models import AnonymousUser
        s = Survey.objects.create(
            slug='anon', title_en='T', title_ko='T',
            tokens={'phase_label': 'Phase 1'},
        )
        out = build_token_map(s, viewer=AnonymousUser())
        # Anonymous viewers get only the survey-level tokens, not user data.
        self.assertEqual(out, {'phase_label': 'Phase 1'})

    def test_serializer_substitutes_tokens_in_question_text(self):
        u = User.objects.create(username='ser', email='ser@x.com')
        s = Survey.objects.create(
            slug='ser', title_en='T', title_ko='T',
            tokens={'phase_label': 'Phase 1'},
        )
        SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5,
            prompt_en='How was {{phase_label}}?',
            prompt_ko='어땠나요 {{phase_label}}?',
            description_en='Reflecting on {{phase_label}}',
            description_ko='',
        )
        from rest_framework.test import APIRequestFactory
        request = APIRequestFactory().get('/')
        request.user = u
        data = SurveyDetailSerializer(s, context={'request': request}).data
        q = data['questions'][0]
        self.assertEqual(q['prompt_en'], 'How was Phase 1?')
        self.assertEqual(q['prompt_ko'], '어땠나요 Phase 1?')
        self.assertEqual(q['description_en'], 'Reflecting on Phase 1')


# ---------------------------------------------------------------------------
# YAML preprocessor: top-level anchor wrap + merge-key → _include rewrite
# ---------------------------------------------------------------------------
class YamlPreprocessorTests(TestCase):
    def test_top_level_anchor_block_is_wrapped(self):
        src = textwrap.dedent("""
            _block: &block
              - order: 1
                slug: q1

            - slug: my_survey
              questions:
                - _include: block
        """).strip()
        out = _wrap_top_level_anchor_blocks(src)
        # The original `_block: &block` line is replaced with a wrapped
        # Survey holder.
        self.assertIn('- slug: _block', out)
        self.assertIn('  questions: &block', out)
        # The block's content is re-indented by 2 extra spaces (was at depth
        # 2, now at depth 4 under `questions:`).
        self.assertIn('    - order: 1', out)
        # The unrelated survey list item passes through unchanged.
        self.assertIn('- slug: my_survey', out)

    def test_merge_key_rewritten_to_include(self):
        src = textwrap.dedent("""
            questions:
              - <<: *shared_block
              - <<: *another_block
        """).strip()
        out = _rewrite_merge_key_to_include(src)
        self.assertIn('- _include: shared_block', out)
        self.assertIn('- _include: another_block', out)
        self.assertNotIn('<<: *', out)

    def test_preprocessor_handles_full_hybrid_format(self):
        """End-to-end: an author writes top-level anchor mappings + uses
        `<<: *anchor` for sequence merge. The preprocessed text loads cleanly.
        """
        src = textwrap.dedent("""
            _shared_questions: &shared_questions
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
                - <<: *shared_questions
                - { order: 99, slug: extra, type: likert_5, prompt: { en: 'x' } }
        """).strip()
        with TemporaryDirectory() as td:
            path = Path(td) / 'h.yaml'
            path.write_text(src)
            call_command('load_surveys', str(path), stdout=StringIO())
        survey = Survey.objects.get(slug='my_survey')
        slugs = list(survey.questions.order_by('order').values_list('slug', flat=True))
        self.assertEqual(slugs, ['shared_q1', 'shared_q2', 'extra'])

    def test_preprocessor_passthrough_when_no_patterns_match(self):
        """A normal valid YAML (no top-level anchors, no merge keys) is unchanged."""
        src = textwrap.dedent("""
            - slug: plain
              title: { en: 'P' }
              questions:
                - { order: 1, slug: q, type: likert_5, prompt: { en: 'p' } }
        """).strip()
        self.assertEqual(_preprocess_yaml_text(src), src)


# ---------------------------------------------------------------------------
# SurveyOption.value JSONField — int and string codes both supported
# ---------------------------------------------------------------------------
class SurveyOptionStringValuesTests(TestCase):
    def test_string_valued_option_loads_and_aggregates(self):
        u = User.objects.create(username='sv', email='sv@x.com')
        with TemporaryDirectory() as td:
            tmp = Path(td)
            yml = _write_yaml(tmp, 'sv.yaml', """
                - slug: cat_survey
                  title: { en: 'C' }
                  questions:
                    - order: 1
                      slug: q1
                      type: single_choice
                      prompt: { en: 'pick one' }
                      options:
                        - { order: 1, value: 'yes',   label: { en: 'Y' } }
                        - { order: 2, value: 'no',    label: { en: 'N' } }
                        - { order: 3, value: 'maybe', label: { en: 'M' } }
            """)
            call_command('load_surveys', str(yml), stdout=StringIO())
        s = Survey.objects.get(slug='cat_survey')
        opts = list(s.questions.first().options.order_by('order'))
        self.assertEqual([o.value for o in opts], ['yes', 'no', 'maybe'])

        # Submit an answer with the string value and confirm aggregation
        # buckets it under the matching option.
        q = s.questions.first()
        r = SurveyResponse.objects.create(user=u, survey=s)
        SurveyAnswer.objects.create(response=r, question=q, value='maybe')
        out = OptionCountsStrategy().build(s, [q], [u.id], u.id)
        counts = {o['value']: o['count'] for o in out['options']}
        self.assertEqual(counts, {'yes': 0, 'no': 0, 'maybe': 1})
        self.assertEqual(out['user_choice'], 'maybe')


# ---------------------------------------------------------------------------
# Submit view: repeatable + embedded_data persistence + likert_5_na N/A
# ---------------------------------------------------------------------------
class SubmitViewExtensionsTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient

        self.user = User.objects.create(username='sb', email='sb@x.com')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_repeatable_survey_allows_multiple_submits(self):
        s = Survey.objects.create(
            slug='r', title_en='R', title_ko='R', repeatable=True,
        )
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        # Schedule it as anytime so the open-window check passes.
        ScheduledSurvey.objects.create(
            survey=s, cadence='anytime',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=5001,
        )
        url = f'/api/surveys/{s.slug}/responses/'
        for _ in range(2):
            r = self.client.post(
                url, data={'answers': [{'question_id': q.id, 'value': 3}]},
                format='json',
            )
            self.assertEqual(r.status_code, 201)
        # Two distinct SurveyResponse rows for the same user.
        self.assertEqual(SurveyResponse.objects.filter(user=self.user, survey=s).count(), 2)

    def test_non_repeatable_survey_returns_409_on_resubmit(self):
        s = Survey.objects.create(slug='nr', title_en='N', title_ko='N')
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='anytime',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=5002,
        )
        url = f'/api/surveys/{s.slug}/responses/'
        r1 = self.client.post(
            url, data={'answers': [{'question_id': q.id, 'value': 3}]},
            format='json',
        )
        r2 = self.client.post(
            url, data={'answers': [{'question_id': q.id, 'value': 4}]},
            format='json',
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 409)

    def test_likert_5_na_accepts_null_value(self):
        s = Survey.objects.create(slug='na_s', title_en='N', title_ko='N')
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5_NA, prompt_en='p', prompt_ko='p',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='anytime',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=5003,
        )
        r = self.client.post(
            f'/api/surveys/{s.slug}/responses/',
            data={'answers': [{'question_id': q.id, 'value': None}]},
            format='json',
        )
        self.assertEqual(r.status_code, 201)
        ans = SurveyAnswer.objects.get(response__user=self.user, question=q)
        self.assertIsNone(ans.value)

    def test_embedded_data_signal_persists_flagged_answers(self):
        s = Survey.objects.create(slug='emb', title_en='E', title_ko='E')
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=SINGLE_CHOICE,
            prompt_en='p', prompt_ko='p',
            slug='habit_platform', embedded_data=True,
        )
        SurveyOption.objects.create(
            question=q, order=1, value='instagram',
            label_en='Instagram', label_ko='Instagram',
        )
        SurveyOption.objects.create(
            question=q, order=2, value='tiktok',
            label_en='TikTok', label_ko='틱톡',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='anytime',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=5004,
        )
        r = self.client.post(
            f'/api/surveys/{s.slug}/responses/',
            data={'answers': [{'question_id': q.id, 'value': 'instagram'}]},
            format='json',
        )
        self.assertEqual(r.status_code, 201)
        # The raw value AND the human-readable label were both persisted.
        rows = {
            row.key: row.value
            for row in UserSurveyEmbeddedData.objects.filter(user=self.user)
        }
        self.assertEqual(rows.get('habit_platform'), 'instagram')
        self.assertEqual(rows.get('habit_platform_label'), 'Instagram')

    def test_display_only_question_in_payload_is_skipped(self):
        s = Survey.objects.create(slug='dpo_sub', title_en='D', title_ko='D')
        intro = SurveyQuestion.objects.create(
            survey=s, order=1, type=DISPLAY_ONLY, required=False,
            content_en='hi', prompt_en='', prompt_ko='',
        )
        real = SurveyQuestion.objects.create(
            survey=s, order=2, type=LIKERT_5,
            prompt_en='p', prompt_ko='p',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='anytime',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=5005,
        )
        r = self.client.post(
            f'/api/surveys/{s.slug}/responses/',
            data={'answers': [
                # display_only block somehow shows up in the payload — must
                # be silently skipped, not crash the submit.
                {'question_id': intro.id, 'value': 'whatever'},
                {'question_id': real.id, 'value': 4},
            ]},
            format='json',
        )
        self.assertEqual(r.status_code, 201)
        # Only the real question got a SurveyAnswer row.
        self.assertEqual(
            SurveyAnswer.objects.filter(response__user=self.user, response__survey=s).count(),
            1,
        )


# ---------------------------------------------------------------------------
# SOTD scheduling: prefer SOTD over daily_base on the same date
# ---------------------------------------------------------------------------
class TodayDailyPrefersSotdTests(TestCase):
    def setUp(self):
        from datetime import date as _date

        self.today = _date(2026, 5, 5)  # Tuesday — sotd_d02 day per spec
        self.user = User.objects.create(
            username='sotd_pref', email='sp@x.com', user_group='group_w_first',
        )

    def test_sotd_takes_priority_over_daily_base(self):
        from unittest.mock import patch

        diary = Survey.objects.create(slug='daily_base', title_en='D', title_ko='D')
        sotd = Survey.objects.create(slug='sotd_d02_rsds', title_en='S', title_ko='S')
        SurveyQuestion.objects.create(survey=diary, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        SurveyQuestion.objects.create(survey=sotd, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        # Both scheduled on the same date; daily_base seq=2 (lower), sotd seq=102.
        ScheduledSurvey.objects.create(
            survey=diary, cadence=CADENCE_DAILY, sequence_index=2,
            window_start=self.today, window_end=self.today, allow_late=False,
        )
        ScheduledSurvey.objects.create(
            survey=sotd, cadence=CADENCE_DAILY, sequence_index=102,
            window_start=self.today, window_end=self.today, allow_late=False,
        )
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            picked = get_today_daily(self.user)
        self.assertIsNotNone(picked)
        # Without the SOTD-preference, default ordering by sequence_index
        # would return daily_base (seq=2 < seq=102). The preference flips
        # the SOTD to the front.
        self.assertEqual(picked.survey.slug, 'sotd_d02_rsds')

    def test_daily_base_returned_when_no_sotd_scheduled(self):
        from unittest.mock import patch

        diary = Survey.objects.create(slug='daily_base', title_en='D', title_ko='D')
        SurveyQuestion.objects.create(survey=diary, order=1, type=LIKERT_5,
                                      prompt_en='p', prompt_ko='p')
        ScheduledSurvey.objects.create(
            survey=diary, cadence=CADENCE_DAILY, sequence_index=3,
            window_start=self.today, window_end=self.today, allow_late=False,
        )
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            picked = get_today_daily(self.user)
        self.assertIsNotNone(picked)
        self.assertEqual(picked.survey.slug, 'daily_base')


# ---------------------------------------------------------------------------
# Study schedule shift: May 3 → May 4 (migration 0012)
# ---------------------------------------------------------------------------
class StudyScheduleMay4Tests(TestCase):
    """Verifies the +1 day shift landed correctly on the study slugs and
    didn't touch mock/demo schedule rows (which have their own dates).
    """

    def test_study_rows_start_may_4(self):
        from datetime import date as _date

        # daily_base seq=1 should now be May 4 after migration 0012.
        row = (
            ScheduledSurvey.objects
            .filter(cadence='daily', survey__slug='daily_base', sequence_index=1)
            .first()
        )
        if row is None:
            # Migrations seed only when surveys exist. In a fresh test DB
            # without `setup_survey_state`, the rows aren't there — skip.
            self.skipTest('study schedule rows not seeded in this DB')
        self.assertEqual(row.window_start, _date(2026, 5, 4))

    def test_pre_study_lands_day_before_kickoff(self):
        from datetime import date as _date

        row = (
            ScheduledSurvey.objects
            .filter(cadence='biweekly', survey__slug='pre_study')
            .first()
        )
        if row is None:
            self.skipTest('pre_study row not seeded in this DB')
        # May 3 = day 0 = day before May 4 kickoff.
        self.assertEqual(row.window_start, _date(2026, 5, 3))

    def test_endpoint_opens_may_31(self):
        from datetime import date as _date

        row = (
            ScheduledSurvey.objects
            .filter(cadence='endpoint', survey__slug='study_endpoint')
            .first()
        )
        if row is None:
            self.skipTest('study_endpoint row not seeded in this DB')
        self.assertEqual(row.window_start, _date(2026, 5, 31))
        self.assertIsNone(row.window_end)


# ---------------------------------------------------------------------------
# View-layer routing: Detail / Submit / Results return 404 for off-route users
# ---------------------------------------------------------------------------
class ViewRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_w = User.objects.create(
            username='vrw', email='vrw@x.com', user_group='group_w_first',
        )
        cls.user_q = User.objects.create(
            username='vrq', email='vrq@x.com', user_group='group_q_first',
        )
        cls.sw = Survey.objects.create(slug='mid_study_w', title_en='W', title_ko='W')
        cls.sq = Survey.objects.create(slug='mid_study_q', title_en='Q', title_ko='Q')
        SurveyQuestion.objects.create(
            survey=cls.sw, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        SurveyQuestion.objects.create(
            survey=cls.sq, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )

    def _client(self, user):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_detail_blocks_w_user_from_q_survey(self):
        r = self._client(self.user_w).get('/api/surveys/mid_study_q/')
        self.assertEqual(r.status_code, 404)

    def test_detail_allows_q_user_for_q_survey(self):
        r = self._client(self.user_q).get('/api/surveys/mid_study_q/')
        self.assertEqual(r.status_code, 200)

    def test_detail_allows_unsuffixed_for_any_user(self):
        s = Survey.objects.create(slug='daily_base', title_en='D', title_ko='D')
        SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        for u in (self.user_w, self.user_q):
            r = self._client(u).get('/api/surveys/daily_base/')
            self.assertEqual(r.status_code, 200)

    def test_submit_blocks_off_route_user(self):
        from datetime import date as _date

        ScheduledSurvey.objects.create(
            survey=self.sw, cadence='biweekly', window_start=_date(2026, 1, 1),
            window_end=_date(2030, 1, 1), allow_late=True, sequence_index=99,
        )
        r = self._client(self.user_q).post(
            '/api/surveys/mid_study_w/responses/',
            data={'answers': []}, format='json',
        )
        self.assertEqual(r.status_code, 404)

    def test_results_blocks_off_route_user(self):
        # results_hidden=True would also 404; explicitly set False so we
        # know it's the routing check that's firing.
        self.sw.results_hidden = False
        self.sw.save()
        r = self._client(self.user_q).get('/api/surveys/mid_study_w/results/')
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# Editable surveys: replace existing answers, my_response endpoint,
# closed → 410, target_user_group routing, priority sort
# ---------------------------------------------------------------------------
class EditableSurveyTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient

        self.user = User.objects.create(username='ed', email='ed@x.com')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_resubmit_replaces_existing_answers_when_editable(self):
        s = Survey.objects.create(
            slug='ed_s', title_en='E', title_ko='E', editable=True,
        )
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='endpoint',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=701,
        )
        url = f'/api/surveys/{s.slug}/responses/'

        # First submit: 201, value=2
        r1 = self.client.post(url, data={'answers': [{'question_id': q.id, 'value': 2}]},
                              format='json')
        self.assertEqual(r1.status_code, 201)
        # Second submit: 201 (because editable), value=4 — answer REPLACED
        r2 = self.client.post(url, data={'answers': [{'question_id': q.id, 'value': 4}]},
                              format='json')
        self.assertEqual(r2.status_code, 201)
        # One response row, one answer row — both updated.
        self.assertEqual(SurveyResponse.objects.filter(user=self.user, survey=s).count(), 1)
        ans = SurveyAnswer.objects.get(response__user=self.user, response__survey=s)
        self.assertEqual(ans.value, 4)

    def test_closed_survey_returns_410_on_submit(self):
        s = Survey.objects.create(
            slug='cl_s', title_en='C', title_ko='C', closed=True,
        )
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='endpoint',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=702,
        )
        r = self.client.post(
            f'/api/surveys/{s.slug}/responses/',
            data={'answers': [{'question_id': q.id, 'value': 2}]},
            format='json',
        )
        self.assertEqual(r.status_code, 410)

    def test_my_response_returns_404_when_no_response(self):
        s = Survey.objects.create(slug='mr_s', title_en='M', title_ko='M')
        SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        r = self.client.get(f'/api/surveys/{s.slug}/my_response/')
        self.assertEqual(r.status_code, 404)

    def test_my_response_returns_user_answers_for_pre_fill(self):
        s = Survey.objects.create(
            slug='mr2_s', title_en='M', title_ko='M', editable=True,
        )
        q = SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='endpoint',
            window_start=__import__('datetime').date(2026, 1, 1),
            window_end=None, allow_late=True, sequence_index=703,
        )
        # Submit once, then GET my_response.
        self.client.post(
            f'/api/surveys/{s.slug}/responses/',
            data={'answers': [{'question_id': q.id, 'value': 5}]},
            format='json',
        )
        r = self.client.get(f'/api/surveys/{s.slug}/my_response/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn('id', body)
        self.assertEqual(body['answers'], [{'question_id': q.id, 'value': 5}])


class TargetUserGroupSchedulingTests(TestCase):
    """ScheduledSurvey.target_user_group restricts a row to one group only."""

    def setUp(self):
        from datetime import date as _date

        self.today = _date(2026, 5, 8)  # Day 5
        self.user_w = User.objects.create(
            username='tg_w', email='tg_w@x.com', user_group='group_w_first',
        )
        self.user_q = User.objects.create(
            username='tg_q', email='tg_q@x.com', user_group='group_q_first',
        )

    def test_target_group_blocks_other_group(self):
        from unittest.mock import patch

        s = Survey.objects.create(slug='feature_eval_w', title_en='F', title_ko='F')
        SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        # One row with target_user_group='group_w_first'
        ScheduledSurvey.objects.create(
            survey=s, cadence='endpoint',
            window_start=self.today, window_end=None,
            allow_late=True, sequence_index=802,
            target_user_group='group_w_first',
        )
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            idx_w = get_survey_index(self.user_w)
            idx_q = get_survey_index(self.user_q)
        slugs_w = {s.survey.slug for s in idx_w['available_now']}
        slugs_q = {s.survey.slug for s in idx_q['available_now']}
        self.assertIn('feature_eval_w', slugs_w)
        self.assertNotIn('feature_eval_w', slugs_q)

    def test_target_group_overrides_slug_suffix_routing(self):
        """A `_w`-suffixed slug with target_user_group='group_q_first' must
        reach q-users — schedule-level routing wins over slug-suffix.

        This is the Day-19 case for feature_eval_w: q-first users get a
        second scheduled row pointing at the same Survey content so they
        can evaluate Ver.W after the biweekly crossover.
        """
        from unittest.mock import patch

        s = Survey.objects.create(slug='feature_eval_w', title_en='F', title_ko='F')
        SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        # Same survey, scheduled for the OTHER group via target_user_group.
        ScheduledSurvey.objects.create(
            survey=s, cadence='endpoint',
            window_start=self.today, window_end=None,
            allow_late=True, sequence_index=803,
            target_user_group='group_q_first',
        )
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            idx_q = get_survey_index(self.user_q)
            idx_w = get_survey_index(self.user_w)
        # q-user sees it (target_user_group beats _w suffix).
        slugs_q = {x.survey.slug for x in idx_q['available_now']}
        self.assertIn('feature_eval_w', slugs_q)
        # w-user does NOT — only the q-targeted row exists in this test.
        slugs_w = {x.survey.slug for x in idx_w['available_now']}
        self.assertNotIn('feature_eval_w', slugs_w)


class PrioritySortTests(TestCase):
    def setUp(self):
        from datetime import date as _date

        self.today = _date(2026, 5, 18)
        self.user = User.objects.create(
            username='ps', email='ps@x.com', user_group='group_w_first',
        )

    def test_higher_priority_surveys_surface_first(self):
        from unittest.mock import patch

        # Three surveys with different priorities, all available now.
        for slug, prio in [('low_pri', 10), ('high_pri', 100), ('mid_pri', 50)]:
            s = Survey.objects.create(slug=slug, title_en=slug, title_ko=slug, priority=prio)
            SurveyQuestion.objects.create(
                survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
            )
            ScheduledSurvey.objects.create(
                survey=s, cadence='anytime',
                window_start=self.today, window_end=None,
                allow_late=True, sequence_index={'low_pri': 901, 'high_pri': 902, 'mid_pri': 903}[slug],
            )
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            idx = get_survey_index(self.user)
        slugs = [s.survey.slug for s in idx['available_now']]
        self.assertEqual(slugs, ['high_pri', 'mid_pri', 'low_pri'])


class EditableIndexBucketingTests(TestCase):
    """Editable surveys stay in available_now after submission until
    `closed=True`, so respondents can re-open and edit their answers.
    Once closed, the row drops to completed."""

    def setUp(self):
        from datetime import date as _date

        self.today = _date(2026, 5, 18)
        self.user = User.objects.create(
            username='eb', email='eb@x.com', user_group='group_w_first',
        )

    def _setup_editable(self, slug):
        s = Survey.objects.create(
            slug=slug, title_en='E', title_ko='E', editable=True,
        )
        SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='p', prompt_ko='p',
        )
        ScheduledSurvey.objects.create(
            survey=s, cadence='endpoint',
            window_start=self.today, window_end=None,
            allow_late=True, sequence_index=910,
        )
        return s

    def test_answered_editable_open_stays_in_available_not_completed(self):
        from unittest.mock import patch

        s = self._setup_editable('eb_open')
        SurveyResponse.objects.create(user=self.user, survey=s)
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            idx = get_survey_index(self.user)
        avail_slugs = {x.survey.slug for x in idx['available_now']}
        comp_slugs = {x.survey.slug for x in idx['completed']}
        self.assertIn('eb_open', avail_slugs)
        self.assertNotIn('eb_open', comp_slugs)

    def test_answered_editable_closed_moves_to_completed(self):
        from unittest.mock import patch

        s = self._setup_editable('eb_closed')
        SurveyResponse.objects.create(user=self.user, survey=s)
        s.closed = True
        s.save(update_fields=['closed'])
        with patch('surveys.scheduling._today_la_7am', return_value=self.today):
            idx = get_survey_index(self.user)
        avail_slugs = {x.survey.slug for x in idx['available_now']}
        comp_slugs = {x.survey.slug for x in idx['completed']}
        self.assertNotIn('eb_closed', avail_slugs)
        self.assertIn('eb_closed', comp_slugs)


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
