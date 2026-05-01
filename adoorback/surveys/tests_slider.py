"""Slider question type — model, validation, and histogram aggregation tests."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import serializers as drf_serializers

from surveys.aggregation import SliderHistogramStrategy
from surveys.models import (
    RESULT_SLIDER_HISTOGRAM, SLIDER, Survey, SurveyAnswer, SurveyQuestion,
    SurveyResponse,
)
from surveys.serializers import validate_answer_value


User = get_user_model()


def _make_slider_question(survey, order=1, lo=0, hi=100):
    return SurveyQuestion.objects.create(
        survey=survey,
        order=order,
        type=SLIDER,
        prompt_en='Mood?', prompt_ko='기분?',
        low_label_en='Terrible', low_label_ko='끔찍해요',
        high_label_en="Couldn't be better", high_label_ko='최고예요',
        slider_min_value=lo,
        slider_max_value=hi,
    )


class SliderQuestionModelTests(TestCase):
    def setUp(self):
        self.survey = Survey.objects.create(slug='s', title_en='T', title_ko='T')

    def test_slider_question_creation_persists_all_fields(self):
        q = _make_slider_question(self.survey, lo=0, hi=100)
        q.refresh_from_db()
        self.assertEqual(q.type, SLIDER)
        self.assertEqual(q.slider_min_value, 0)
        self.assertEqual(q.slider_max_value, 100)
        self.assertEqual(q.low_label_en, 'Terrible')
        self.assertEqual(q.low_label_ko, '끔찍해요')
        self.assertEqual(q.high_label_en, "Couldn't be better")
        self.assertEqual(q.effective_result_kind, RESULT_SLIDER_HISTOGRAM)

    def test_slider_min_max_constraint_min_gte_max(self):
        q = SurveyQuestion(
            survey=self.survey, order=1, type=SLIDER,
            prompt_en='Q', prompt_ko='Q',
            slider_min_value=100, slider_max_value=100,
        )
        with self.assertRaises(ValidationError):
            q.full_clean()

        q.slider_min_value = 200  # min > max
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_slider_requires_min_and_max(self):
        q = SurveyQuestion(
            survey=self.survey, order=1, type=SLIDER,
            prompt_en='Q', prompt_ko='Q',
            slider_min_value=None, slider_max_value=None,
        )
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_non_slider_question_ignores_slider_fields(self):
        # Likert question without slider_min/max should clean fine.
        q = SurveyQuestion(
            survey=self.survey, order=1, type='likert_5',
            prompt_en='Q', prompt_ko='Q',
            low_label_en='lo', low_label_ko='lo',
            high_label_en='hi', high_label_ko='hi',
        )
        q.full_clean()  # should not raise


class SliderValueValidationTests(TestCase):
    def setUp(self):
        survey = Survey.objects.create(slug='s', title_en='T', title_ko='T')
        self.q = _make_slider_question(survey, lo=0, hi=100)

    def test_in_range_value_passes(self):
        validate_answer_value(self.q, 50)
        validate_answer_value(self.q, 0)    # boundary
        validate_answer_value(self.q, 100)  # boundary

    def test_value_above_max_rejected(self):
        with self.assertRaises(drf_serializers.ValidationError):
            validate_answer_value(self.q, 150)

    def test_value_below_min_rejected(self):
        with self.assertRaises(drf_serializers.ValidationError):
            validate_answer_value(self.q, -10)

    def test_non_integer_rejected(self):
        with self.assertRaises(drf_serializers.ValidationError):
            validate_answer_value(self.q, '50')
        with self.assertRaises(drf_serializers.ValidationError):
            validate_answer_value(self.q, 50.5)
        with self.assertRaises(drf_serializers.ValidationError):
            validate_answer_value(self.q, True)


class SliderHistogramAggregationTests(TestCase):
    def setUp(self):
        self.survey = Survey.objects.create(slug='s', title_en='T', title_ko='T')
        self.q = _make_slider_question(self.survey, lo=0, hi=100)

    def _seed_answers(self, values):
        responder_ids = []
        for i, v in enumerate(values):
            user = User.objects.create(username=f'u{i}', email=f'u{i}@x.com')
            response = SurveyResponse.objects.create(user=user, survey=self.survey)
            SurveyAnswer.objects.create(response=response, question=self.q, value=v)
            responder_ids.append(user.id)
        return responder_ids

    def test_uniform_distribution_across_10_bins(self):
        # 100 answers, 10 in each bin: values 0..9, 10..19, ..., 90..99 + one 100.
        values = list(range(100))  # 0..99 — 10 per bin (0-9 in bin 0, etc.)
        responder_ids = self._seed_answers(values)
        result = SliderHistogramStrategy().build(
            self.survey, [self.q], responder_ids, viewer_id=responder_ids[0],
        )
        self.assertEqual(result['kind'], RESULT_SLIDER_HISTOGRAM)
        self.assertEqual(result['min_value'], 0)
        self.assertEqual(result['max_value'], 100)
        self.assertEqual(len(result['bins']), 10)
        for b in result['bins']:
            self.assertEqual(b['count'], 10)
        self.assertEqual(result['mean'], round(sum(values) / 100, 2))
        self.assertEqual(result['median'], 49.5)
        self.assertEqual(result['user_value'], 0)

    def test_max_value_lands_in_last_bin(self):
        responder_ids = self._seed_answers([100])
        result = SliderHistogramStrategy().build(
            self.survey, [self.q], responder_ids, viewer_id=responder_ids[0],
        )
        # All 100 answers should be in the last bin only.
        self.assertEqual(result['bins'][-1]['count'], 1)
        for b in result['bins'][:-1]:
            self.assertEqual(b['count'], 0)

    def test_empty_responders_returns_null_stats(self):
        result = SliderHistogramStrategy().build(
            self.survey, [self.q], responder_ids=[], viewer_id=999,
        )
        self.assertIsNone(result['mean'])
        self.assertIsNone(result['median'])
        self.assertEqual(sum(b['count'] for b in result['bins']), 0)

    def test_mean_and_median(self):
        responder_ids = self._seed_answers([10, 20, 30, 40, 50])
        result = SliderHistogramStrategy().build(
            self.survey, [self.q], responder_ids, viewer_id=responder_ids[0],
        )
        self.assertEqual(result['mean'], 30.0)
        self.assertEqual(result['median'], 30.0)
        self.assertEqual(result['user_value'], 10)
