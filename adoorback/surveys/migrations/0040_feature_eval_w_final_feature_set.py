from django.db import migrations


FEATURE_SURVEY_SLUG = 'feature_eval_w'
TEMP_ORDER_BASE = 30000
DEPRECATED_HIDE_RULE = {
    'depends_on': '__deprecated_feature_never_shown__',
    'show_when_value': '__show__',
}

SOCIAL_BATTERY_LEVEL_QUESTIONS = [
    {
        'slug': 'goal2_feat_social_battery_level',
        'type': 'likert_5',
        'prompt': '**Social battery level** — I liked this feature.',
        'low_label': 'Strongly disagree',
        'high_label': 'Strongly agree',
        'required': True,
    },
    {
        'slug': 'goal2_feat_social_battery_level_enjoy',
        'type': 'free_text',
        'prompt': 'What, if anything, did you enjoy most about the social battery level feature?',
        'required': False,
    },
    {
        'slug': 'goal2_feat_social_battery_level_dislike',
        'type': 'free_text',
        'prompt': 'What, if anything, did you dislike most about the social battery level feature?',
        'required': False,
    },
]

DEPRECATED_FEATURE_SLUGS = [
    'goal2_feat_chatstatus',
    'goal2_feat_chatstatus_enjoy',
    'goal2_feat_chatstatus_dislike',
    'goal4_feat_social_battery',
    'goal4_feat_social_battery_enjoy',
    'goal4_feat_social_battery_dislike',
]


def _set_text(obj, field, value):
    setattr(obj, field, value)
    setattr(obj, f'{field}_en', value)
    setattr(obj, f'{field}_ko', value)


def _upsert_social_battery_question(SurveyQuestion, survey, spec, order):
    question = SurveyQuestion.objects.filter(survey=survey, slug=spec['slug']).first()
    if question is None:
        question = SurveyQuestion(survey=survey, slug=spec['slug'])
    question.order = order
    question.type = spec['type']
    _set_text(question, 'prompt', spec['prompt'])
    _set_text(question, 'description', spec.get('description', ''))
    _set_text(question, 'low_label', spec.get('low_label', ''))
    _set_text(question, 'high_label', spec.get('high_label', ''))
    question.na_option = ''
    question.na_option_en = ''
    question.na_option_ko = ''
    question.min_length = 0 if spec['type'] == 'free_text' else None
    question.required = spec['required']
    question.result_hidden = True
    question.reverse_scored = False
    question.conditional_display = {}
    question.save()
    return question


def apply_feature_eval_w_final_feature_set(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    SurveyQuestion = apps.get_model('surveys', 'SurveyQuestion')

    survey = Survey.objects.filter(slug=FEATURE_SURVEY_SLUG).first()
    if survey is None:
        return

    original_questions = list(
        SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id')
    )
    if not original_questions:
        return

    for offset, question in enumerate(original_questions, start=1):
        question.order = TEMP_ORDER_BASE + offset
        question.save(update_fields=['order'])

    next_temp_order = TEMP_ORDER_BASE + len(original_questions) + 1
    for spec in SOCIAL_BATTERY_LEVEL_QUESTIONS:
        _upsert_social_battery_question(SurveyQuestion, survey, spec, next_temp_order)
        next_temp_order += 1

    for question in SurveyQuestion.objects.filter(survey=survey, slug__in=DEPRECATED_FEATURE_SLUGS):
        question.required = False
        question.result_hidden = True
        question.conditional_display = DEPRECATED_HIDE_RULE
        question.save(update_fields=['required', 'result_hidden', 'conditional_display'])

    questions_by_slug = {
        q.slug: q
        for q in SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id')
        if q.slug
    }
    social_questions = [
        questions_by_slug[spec['slug']]
        for spec in SOCIAL_BATTERY_LEVEL_QUESTIONS
        if spec['slug'] in questions_by_slug
    ]
    social_ids = {q.id for q in social_questions}
    deprecated = [
        q for q in SurveyQuestion.objects.filter(survey=survey, slug__in=DEPRECATED_FEATURE_SLUGS).order_by('order', 'id')
    ]
    deprecated_ids = {q.id for q in deprecated}

    final_order = []
    inserted_social = False
    inserted_ids = set()
    for question in SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id'):
        if question.id in deprecated_ids or question.id in social_ids:
            continue
        final_order.append(question)
        inserted_ids.add(question.id)
        if question.slug == 'goal2_feat_browse_dislike':
            final_order.extend(social_questions)
            inserted_ids.update(social_ids)
            inserted_social = True

    if not inserted_social:
        insert_after = questions_by_slug.get('goal2_feat_browse')
        rebuilt = []
        for question in final_order:
            rebuilt.append(question)
            if insert_after is not None and question.id == insert_after.id:
                rebuilt.extend(social_questions)
                inserted_ids.update(social_ids)
                inserted_social = True
        final_order = rebuilt

    if not inserted_social:
        final_order.extend(social_questions)
        inserted_ids.update(social_ids)

    final_order.extend(deprecated)
    for question in SurveyQuestion.objects.filter(survey=survey).order_by('order', 'id'):
        if question.id not in inserted_ids and question.id not in deprecated_ids:
            final_order.append(question)

    seen = set()
    deduped_order = []
    for question in final_order:
        if question.id in seen:
            continue
        seen.add(question.id)
        deduped_order.append(question)

    for order, question in enumerate(deduped_order, start=1):
        question.order = order
        question.save(update_fields=['order'])


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0039_seed_recovery_surveys'),
    ]

    operations = [
        migrations.RunPython(apply_feature_eval_w_final_feature_set, migrations.RunPython.noop),
    ]
