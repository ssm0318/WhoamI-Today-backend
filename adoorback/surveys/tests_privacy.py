from django.contrib.auth import get_user_model
from django.test import TestCase

from account.models import Connection
from chat.wit_bot import ensure_wit_bot_user
from surveys.aggregation import build_likert_distribution, compute_user_percentile
from surveys.models import (
    Survey, SurveyAnswer, SurveyQuestion, SurveyResponse,
)
from surveys.privacy import (
    MIN_GROUP_DELTA, MIN_GROUP_SIZE, compute_bucket_eligibility, get_visible_friend_ids,
)


User = get_user_model()


def _connect(a, b, *, a_choice='friend', b_choice='friend'):
    if a.id < b.id:
        Connection.objects.create(
            user1=a, user2=b, user1_choice=a_choice, user2_choice=b_choice,
        )
    else:
        Connection.objects.create(
            user1=b, user2=a, user1_choice=b_choice, user2_choice=a_choice,
        )


def _make_likert_survey(slug='s_likert', n_questions=2):
    s = Survey.objects.create(slug=slug, type=Survey.LIKERT_5, title_en='T', title_ko='T')
    for i in range(1, n_questions + 1):
        SurveyQuestion.objects.create(
            survey=s, order=i, prompt_en=f'Q{i}', prompt_ko=f'Q{i}',
            reverse_scored=(i == 2),
        )
    return s


def _respond(user, survey, values):
    r = SurveyResponse.objects.create(user=user, survey=survey)
    for q, v in zip(survey.questions.order_by('order'), values):
        SurveyAnswer.objects.create(response=r, question=q, value=v)
    return r


class PrivacyGateTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create(username='viewer', email='v@x.com')

    def test_too_few_friends(self):
        s = _make_likert_survey('a')
        for i in range(MIN_GROUP_SIZE - 1):  # 4
            f = User.objects.create(username=f'f{i}', email=f'f{i}@x.com')
            _connect(self.viewer, f)
            _respond(f, s, [3, 3])
        report = compute_bucket_eligibility(self.viewer, s)
        self.assertEqual(report['friends']['suppressed_reason'], 'too_few_friends')

    def test_too_few_responders(self):
        s = _make_likert_survey('b')
        for i in range(MIN_GROUP_SIZE):
            f = User.objects.create(username=f'f{i}', email=f'f{i}@x.com')
            _connect(self.viewer, f)
            if i < MIN_GROUP_SIZE - 1:  # only 4 respond
                _respond(f, s, [3, 3])
        report = compute_bucket_eligibility(self.viewer, s)
        self.assertEqual(report['friends']['suppressed_reason'], 'too_few_responders')

    def test_delta_too_small(self):
        s = _make_likert_survey('c')
        for i in range(MIN_GROUP_SIZE):
            f = User.objects.create(username=f'f{i}', email=f'f{i}@x.com')
            _connect(self.viewer, f, a_choice='close_friend', b_choice='close_friend')
            _respond(f, s, [3, 3])
        report = compute_bucket_eligibility(self.viewer, s)
        # close_friends_count = 5, cf_responders = 5; friend_responders also 5; delta = 0
        self.assertEqual(report['close_friends']['suppressed_reason'], 'delta_too_small')

    def test_both_available_when_delta_passes(self):
        s = _make_likert_survey('d')
        # 5 close-friends respond, plus 5 friends-only respond → friend_responders = 10, cf_responders = 5
        for i in range(MIN_GROUP_SIZE):
            f = User.objects.create(username=f'cf{i}', email=f'cf{i}@x.com')
            _connect(self.viewer, f, a_choice='close_friend', b_choice='close_friend')
            _respond(f, s, [3, 3])
        for i in range(MIN_GROUP_DELTA):
            f = User.objects.create(username=f'fr{i}', email=f'fr{i}@x.com')
            _connect(self.viewer, f)
            _respond(f, s, [4, 2])
        report = compute_bucket_eligibility(self.viewer, s)
        self.assertTrue(report['friends']['available'])
        self.assertTrue(report['close_friends']['available'])

    def test_wit_bot_excluded_from_friend_count(self):
        bot = ensure_wit_bot_user()
        _connect(self.viewer, bot)  # defensive: even if a Connection row exists
        ids = get_visible_friend_ids(self.viewer)
        self.assertNotIn(bot.id, ids)


class AggregationTests(TestCase):
    def test_aggregated_likert_with_reverse_scoring(self):
        s = _make_likert_survey('agg')
        u1 = User.objects.create(username='u1', email='u1@x.com')
        u2 = User.objects.create(username='u2', email='u2@x.com')
        # Q1 normal, Q2 reverse-scored
        # u1: q1=5, q2=1 (reverse → 5) → score 10
        # u2: q1=3, q2=3 (reverse → 3) → score 6
        _respond(u1, s, [5, 1])
        _respond(u2, s, [3, 3])
        dist = build_likert_distribution(s, [u1.id, u2.id], viewer_id=u1.id)
        self.assertEqual(dist['min_score'], 2)
        self.assertEqual(dist['max_score'], 10)
        self.assertEqual(dist['user_score'], 10)
        score_to_count = {b['score']: b['count'] for b in dist['bins']}
        self.assertEqual(score_to_count[10], 1)
        self.assertEqual(score_to_count[6], 1)

    def test_percentile_rank(self):
        bins = [{'score': i, 'count': 0} for i in range(2, 11)]
        bins[0]['count'] = 2  # score=2
        bins[4]['count'] = 1  # score=6 (the viewer's score)
        bins[8]['count'] = 1  # score=10
        dist = {
            'kind': 'aggregated_likert', 'bins': bins,
            'min_score': 2, 'max_score': 10, 'user_score': 6,
        }
        # below=2, equal=1, total=4 → (2 + 0.5)/4 = 0.625
        self.assertAlmostEqual(compute_user_percentile(dist, 6), 0.625)
