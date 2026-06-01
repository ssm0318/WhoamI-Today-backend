# Generated manually for the 2026 final-study reimbursement audit.

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import migrations


SOURCE_SURVEY = 'survey'


def _routes_to_user(survey, user):
    slug = survey.slug
    user_group = getattr(user, 'user_group', '') or ''
    if slug.endswith('_w'):
        return user_group == 'group_w_first'
    if slug.endswith('_q'):
        return user_group == 'group_q_first'
    return True


def _schedule_routes_to_user(scheduled, user):
    target = getattr(scheduled, 'target_user_group', '') or ''
    if target:
        return getattr(user, 'user_group', '') == target
    return _routes_to_user(scheduled.survey, user)


def _logical_response_date(response):
    la_tz = ZoneInfo('America/Los_Angeles')
    return (response.submitted_at.astimezone(la_tz) - timedelta(hours=7)).date()


def _scheduled_survey_for_response(ScheduledSurvey, response):
    rows = [
        row
        for row in (
            ScheduledSurvey.objects
            .filter(survey=response.survey)
            .select_related('survey')
        )
        if _schedule_routes_to_user(row, response.user)
    ]
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    logical_date = _logical_response_date(response)
    matching_window = [
        row for row in rows
        if row.window_start <= logical_date and (
            row.window_end is None or row.window_end >= logical_date
        )
    ]
    if matching_window:
        return sorted(matching_window, key=lambda row: (row.window_start, row.sequence_index))[0]

    return None


def _point_award_values_for_response(Survey, SurveyResponse, response):
    prereq_slug = response.survey.point_prereq_slug or ''
    if not prereq_slug:
        return response.survey.point_value, ''

    prereq_completed = SurveyResponse.objects.filter(
        user=response.user,
        survey__slug=prereq_slug,
        submitted_at__lte=response.submitted_at,
    ).exists()
    if prereq_completed:
        return response.survey.point_value, ''

    prereq = Survey.objects.filter(slug=prereq_slug).first()
    prereq_title = prereq.slug if prereq else prereq_slug
    return 0, f'Prereq {prereq_title} not completed at submit time.'


def backfill_legacy_point_awards(apps, schema_editor):
    PointAward = apps.get_model('surveys', 'PointAward')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    Survey = apps.get_model('surveys', 'Survey')
    SurveyResponse = apps.get_model('surveys', 'SurveyResponse')

    awarded_response_ids = set(
        PointAward.objects
        .filter(source_kind=SOURCE_SURVEY, response__isnull=False)
        .values_list('response_id', flat=True)
    )
    awarded_scheduled_ids_by_user = {}
    scheduled_awards = (
        PointAward.objects
        .filter(source_kind=SOURCE_SURVEY, scheduled_survey__isnull=False)
        .values_list('user_id', 'scheduled_survey_id')
    )
    for user_id, scheduled_id in scheduled_awards:
        awarded_scheduled_ids_by_user.setdefault(user_id, set()).add(scheduled_id)

    responses = (
        SurveyResponse.objects
        .filter(survey__point_value__gt=0)
        .exclude(id__in=awarded_response_ids)
        .select_related('survey', 'user')
        .order_by('user_id', 'submitted_at', 'id')
    )
    for response in responses.iterator():
        scheduled = _scheduled_survey_for_response(ScheduledSurvey, response)
        user_scheduled_ids = awarded_scheduled_ids_by_user.setdefault(response.user_id, set())
        if scheduled is not None and scheduled.id in user_scheduled_ids:
            continue

        awarded_points, note = _point_award_values_for_response(
            Survey,
            SurveyResponse,
            response,
        )
        defaults = {
            'source_slug': response.survey.slug,
            'response': response,
            'awarded_points': awarded_points,
            'note': note,
        }
        if scheduled is not None:
            _award, created = PointAward.objects.get_or_create(
                user=response.user,
                source_kind=SOURCE_SURVEY,
                scheduled_survey=scheduled,
                defaults=defaults,
            )
            if created:
                user_scheduled_ids.add(scheduled.id)
            continue

        PointAward.objects.get_or_create(
            user=response.user,
            source_kind=SOURCE_SURVEY,
            response=response,
            defaults=defaults,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0046_ensure_sotd_allow_late'),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_point_awards, migrations.RunPython.noop),
    ]
