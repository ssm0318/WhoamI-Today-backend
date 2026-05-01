from django.contrib.auth import get_user_model

from account.models import Connection
from surveys.models import (
    CADENCE_DAILY, FREE_TEXT, LIKERT_5, ScheduledSurvey, Survey, SurveyAnswer,
    SurveyQuestion, SurveyResponse,
)

User = get_user_model()


def _schedule_daily(survey, schedule_date):
    """Create a ScheduledSurvey row for `survey` on `schedule_date` (cadence=daily).

    sequence_index is auto-assigned to keep test setups simple — the
    (cadence, sequence_index) unique constraint is satisfied as long as each
    helper call gets a fresh number. allow_late=False matches production
    daily semantics.
    """
    next_seq = ScheduledSurvey.objects.filter(cadence=CADENCE_DAILY).count() + 1
    return ScheduledSurvey.objects.create(
        survey=survey,
        cadence=CADENCE_DAILY,
        window_start=schedule_date,
        window_end=schedule_date,
        allow_late=False,
        sequence_index=next_seq,
    )


def make_user(name):
    return User.objects.create(username=name, email=f'{name}@x.com')


def make_likert_survey(slug='s', n_questions=2, schedule_date=None):
    s = Survey.objects.create(slug=slug, title_en='T', title_ko='T')
    for i in range(1, n_questions + 1):
        SurveyQuestion.objects.create(
            survey=s,
            order=i,
            type=LIKERT_5,
            prompt_en=f'Q{i}',
            prompt_ko=f'Q{i}',
            reverse_scored=(i == 2),
        )
    if schedule_date is not None:
        _schedule_daily(s, schedule_date)
    return s


def make_mixed_survey(slug='m', n_likert=2, n_free_text=1, schedule_date=None):
    """Survey with a likert panel + a free-text panel for testing mixed-type aggregation."""
    s = Survey.objects.create(slug=slug, title_en='T', title_ko='T')
    order = 1
    for i in range(n_likert):
        SurveyQuestion.objects.create(
            survey=s, order=order, type=LIKERT_5,
            prompt_en=f'L{i+1}', prompt_ko=f'L{i+1}',
            reverse_scored=(i == 1),
        )
        order += 1
    for i in range(n_free_text):
        SurveyQuestion.objects.create(
            survey=s, order=order, type=FREE_TEXT,
            prompt_en=f'F{i+1}', prompt_ko=f'F{i+1}',
        )
        order += 1
    if schedule_date is not None:
        _schedule_daily(s, schedule_date)
    return s


def connect(a, b, *, a_choice='friend', b_choice='friend'):
    if a.id < b.id:
        Connection.objects.create(
            user1=a, user2=b, user1_choice=a_choice, user2_choice=b_choice,
        )
    else:
        Connection.objects.create(
            user1=b, user2=a, user1_choice=b_choice, user2_choice=a_choice,
        )


def respond(user, survey, values):
    r = SurveyResponse.objects.create(user=user, survey=survey)
    for q, v in zip(survey.questions.order_by('order'), values):
        SurveyAnswer.objects.create(response=r, question=q, value=v)
    return r
