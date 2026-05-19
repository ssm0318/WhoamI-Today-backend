import re

from django.db import migrations


FEATURE_SURVEY_SLUG = 'feature_eval_w'
TEMP_ORDER_BASE = 30000


def _is_feature_followup(slug):
    return slug.endswith('_enjoy') or slug.endswith('_dislike')


def _is_feature_rating(question):
    slug = question.slug or ''
    return (
        re.match(r'^goal\d+_feat_', slug) is not None
        and not _is_feature_followup(slug)
        and question.type in ('likert_5', 'likert_5_na')
    )


def _feature_label(question):
    text = question.prompt_en or question.prompt or question.slug
    match = re.search(r'\*\*(.*?)\*\*', text)
    label = match.group(1) if match else question.slug.replace('_', ' ')
    label = re.sub(r'\s+', ' ', label).strip()
    return label[:1].lower() + label[1:] if label else 'this'


def _followup_prompt(question, suffix):
    verb = 'enjoy' if suffix == 'enjoy' else 'dislike'
    return f'What, if anything, did you {verb} most about the {_feature_label(question)} feature?'


def _rating_prompt(question):
    text = question.prompt_en or question.prompt
    return text.replace('I was satisfied with this feature.', 'I liked this feature.')


def _set_translated_text(obj, field, value):
    setattr(obj, field, value)
    setattr(obj, f'{field}_en', value)
    setattr(obj, f'{field}_ko', value)


def apply_feature_eval_w_followups(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    SurveyQuestion = apps.get_model('surveys', 'SurveyQuestion')

    survey = Survey.objects.filter(slug=FEATURE_SURVEY_SLUG).first()
    if not survey:
        return

    original_questions = list(
        SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id')
    )
    if not original_questions:
        return

    for offset, question in enumerate(original_questions, start=1):
        question.order = TEMP_ORDER_BASE + offset
        question.save(update_fields=['order'])

    questions_by_slug = {
        q.slug: q
        for q in SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id')
        if q.slug
    }
    next_temp_order = TEMP_ORDER_BASE + len(original_questions) + 1

    for original in original_questions:
        if not _is_feature_rating(original):
            continue

        rating = questions_by_slug.get(original.slug)
        if rating is None:
            continue

        rating.type = 'likert_5'
        _set_translated_text(rating, 'prompt', _rating_prompt(rating))
        rating.na_option = ''
        rating.na_option_en = ''
        rating.na_option_ko = ''
        rating.result_hidden = True
        rating.save(
            update_fields=[
                'type',
                'prompt',
                'prompt_en',
                'prompt_ko',
                'na_option',
                'na_option_en',
                'na_option_ko',
                'result_hidden',
            ]
        )

        for suffix in ('enjoy', 'dislike'):
            slug = f'{rating.slug}_{suffix}'
            prompt = _followup_prompt(rating, suffix)
            followup = questions_by_slug.get(slug)
            if followup is None:
                followup = SurveyQuestion.objects.create(
                    survey=survey,
                    order=next_temp_order,
                    slug=slug,
                    type='free_text',
                    prompt=prompt,
                    prompt_en=prompt,
                    prompt_ko=prompt,
                    min_length=0,
                    required=False,
                    result_hidden=True,
                )
                next_temp_order += 1
                questions_by_slug[slug] = followup
            else:
                followup.type = 'free_text'
                _set_translated_text(followup, 'prompt', prompt)
                followup.min_length = 0
                followup.required = False
                followup.result_hidden = True
                followup.save(
                    update_fields=[
                        'type',
                        'prompt',
                        'prompt_en',
                        'prompt_ko',
                        'min_length',
                        'required',
                        'result_hidden',
                    ]
                )

    refreshed_by_id = {
        q.id: q
        for q in SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id')
    }
    questions_by_slug = {
        q.slug: q
        for q in SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id')
        if q.slug
    }
    final_order = []
    seen_ids = set()

    for original in original_questions:
        question = refreshed_by_id.get(original.id)
        if question is None:
            continue
        if _is_feature_followup(question.slug or ''):
            continue
        final_order.append(question)
        seen_ids.add(question.id)

        if _is_feature_rating(question):
            for suffix in ('enjoy', 'dislike'):
                followup = questions_by_slug.get(f'{question.slug}_{suffix}')
                if followup and followup.id not in seen_ids:
                    final_order.append(followup)
                    seen_ids.add(followup.id)

    for question in SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id'):
        if question.id not in seen_ids:
            final_order.append(question)
            seen_ids.add(question.id)

    for order, question in enumerate(final_order, start=1):
        question.order = order
        question.save(update_fields=['order'])


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0037_closeness_surveys_one_shot'),
    ]

    operations = [
        migrations.RunPython(apply_feature_eval_w_followups, migrations.RunPython.noop),
    ]
