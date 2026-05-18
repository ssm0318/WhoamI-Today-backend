from django.db import migrations


SURVEY_UPDATES = {
    'mid_study_w': {
        'description': "Now that you've finished the first half, we'd like to hear what your experience was like. About 30 minutes. Take your time.",
        'description_en': "Now that you've finished the first half, we'd like to hear what your experience was like. About 30 minutes. Take your time.",
    },
    'mid_study_q': {
        'description': "Now that you've finished the first half, we'd like to hear what your experience was like. About 17 minutes. Take your time.",
        'description_en': "Now that you've finished the first half, we'd like to hear what your experience was like. About 17 minutes. Take your time.",
    },
    'post_study_w': {
        'description': "You've now finished both halves. This survey asks about the second half only. About 30 minutes.",
        'description_en': "You've now finished both halves. This survey asks about the second half only. About 30 minutes.",
    },
    'post_study_q': {
        'description': "You've now finished both halves. This survey asks about the second half only. About 17 minutes.",
        'description_en': "You've now finished both halves. This survey asks about the second half only. About 17 minutes.",
    },
    'feature_eval_w': {
        'title': 'Ver. W features',
        'title_en': 'Ver. W features',
        'description': 'Rate how much you liked each Ver. W feature you used, and tell us briefly what you enjoyed and disliked about each. You can come back and edit your answers while this survey remains open.',
        'description_en': 'Rate how much you liked each Ver. W feature you used, and tell us briefly what you enjoyed and disliked about each. You can come back and edit your answers while this survey remains open.',
    },
    'goal_comparison_p1': {
        'title': 'How did Phase 1 go?',
        'title_en': 'How did Phase 1 go?',
        'description': 'Answer a few questions about different parts of your WIT experience during Phase 1. You can come back and edit while this survey remains open.',
        'description_en': 'Answer a few questions about different parts of your WIT experience during Phase 1. You can come back and edit while this survey remains open.',
    },
    'goal_comparison_p2': {
        'title': 'How did Phase 2 go?',
        'title_en': 'How did Phase 2 go?',
        'description': 'Answer a few questions about different parts of your WIT experience during Phase 2. You can come back and edit while this survey remains open.',
        'description_en': 'Answer a few questions about different parts of your WIT experience during Phase 2. You can come back and edit while this survey remains open.',
    },
    'study_endpoint': {
        'description': "A few questions about how you'd want WIT to fit into your life going forward — or whether it should at all. About 12 minutes.",
        'description_en': "A few questions about how you'd want WIT to fit into your life going forward — or whether it should at all. About 12 minutes.",
    },
    'anytime_reflection': {
        'description': "Got something to share that doesn't fit the other surveys? Bug, idea, mission suggestion, question for the cohort, weird thing that happened — submit as many times as you want.",
        'description_en': "Got something to share that doesn't fit the other surveys? Bug, idea, mission suggestion, question for the cohort, weird thing that happened — submit as many times as you want.",
    },
    'phase2_friend_closeness': {
        'description': 'Same idea as last time — for each friend on your list, please re-rate how close you feel right now and how often you see them in person.',
        'description_en': 'Same idea as last time — for each friend on your list, please re-rate how close you feel right now and how often you see them in person.',
        'description_ko': '지난번과 같은 방식이에요. 친구 한 명 한 명에 대해 지금 얼마나 가까운지와 오프라인에서 얼마나 자주 만나는지를 다시 평가해 주세요.',
    },
    'sotd_d26_transition': {
        'description': "You've been on WIT for almost a month now. A few quick reflections — this one is just gut reactions.",
        'description_en': "You've been on WIT for almost a month now. A few quick reflections — this one is just gut reactions.",
    },
}

QUESTION_UPDATES = {
    ('feature_eval_w', 'feature_eval_intro'): {
        'content': "**Ver. W features.** For each feature, rate how much you liked it and briefly say what you enjoyed and disliked. You don't have to fill it in all at once — your answers save as you go and you can come back to edit them while this survey remains open.",
        'content_en': "**Ver. W features.** For each feature, rate how much you liked it and briefly say what you enjoyed and disliked. You don't have to fill it in all at once — your answers save as you go and you can come back to edit them while this survey remains open.",
    },
    ('sotd_d26_transition', 'transition_keep_using'): {
        'prompt': 'If WIT stayed available in the future, would you keep using it?',
        'prompt_en': 'If WIT stayed available in the future, would you keep using it?',
    },
    ('sotd_d26_transition', 'transition_outro'): {
        'content': '**Thanks for these gut reactions.** There may be a longer survey available too. Take your time with it; it can stay open through Sunday.',
        'content_en': '**Thanks for these gut reactions.** There may be a longer survey available too. Take your time with it; it can stay open through Sunday.',
    },
    ('study_endpoint', 'cadence_block_intro'): {
        'content': '**Part 1: Rhythms.** Several things on WIT happen on a daily rhythm — daily questions, the mission of the day, survey of the day, the daily digest. How would you actually want these to show up?',
        'content_en': '**Part 1: Rhythms.** Several things on WIT happen on a daily rhythm — daily questions, the mission of the day, survey of the day, the daily digest. How would you actually want these to show up?',
    },
    ('study_endpoint', 'cadence_general_freq'): {
        'prompt': '**Overall** — how often would feel natural to actually open WIT and check in?',
        'prompt_en': '**Overall** — how often would feel natural to actually open WIT and check in?',
    },
    ('study_endpoint', 'data_block_intro'): {
        'content': "**Part 2: Your data going forward.** How would you like us to handle your data?",
        'content_en': "**Part 2: Your data going forward.** How would you like us to handle your data?",
    },
    ('study_endpoint', 'keep_block_intro'): {
        'content': "**Part 3: Your account.** Going forward, we'll be keeping the **Ver.W** version of WIT (the one with check-ins, mission of the day, daily digest). Ver.Q won't continue.\n\nPlease decide based on whether you'd actually want this in your life.",
        'content_en': "**Part 3: Your account.** Going forward, we'll be keeping the **Ver.W** version of WIT (the one with check-ins, mission of the day, daily digest). Ver.Q won't continue.\n\nPlease decide based on whether you'd actually want this in your life.",
    },
    ('study_endpoint', 'friend_graph_block_intro'): {
        'content': '**Part 4: Your connections.** How would you like your WIT connections to carry over?',
        'content_en': '**Part 4: Your connections.** How would you like your WIT connections to carry over?',
    },
    ('study_endpoint', 'profile_block_intro'): {
        'content': '**Part 5: Your profile.** How would you like your profile setup to carry over?',
        'content_en': '**Part 5: Your profile.** How would you like your profile setup to carry over?',
    },
    ('study_endpoint', 'goodbye_block_intro'): {
        'content': '**Last part.** Anything you want us to know — about WIT, social media in general, or this experience — as you wrap up?',
        'content_en': '**Last part.** Anything you want us to know — about WIT, social media in general, or this experience — as you wrap up?',
    },
    ('study_endpoint', 'future_contact'): {
        'prompt': 'Could we contact you in the future about WIT updates or follow-up opportunities?',
        'prompt_en': 'Could we contact you in the future about WIT updates or follow-up opportunities?',
    },
}

OPTION_UPDATES = {
    ('study_endpoint', 'future_contact', 'yes_anything'): {
        'label': 'Yes, anything related to WIT',
        'label_en': 'Yes, anything related to WIT',
    },
    ('study_endpoint', 'future_contact', 'yes_specific'): {
        'label': 'Yes, but only for follow-up questions',
        'label_en': 'Yes, but only for follow-up questions',
    },
}


def clean_copy(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    SurveyQuestion = apps.get_model('surveys', 'SurveyQuestion')
    SurveyOption = apps.get_model('surveys', 'SurveyOption')

    for slug, updates in SURVEY_UPDATES.items():
        Survey.objects.filter(slug=slug).update(**updates)

    for slug in ('post_study_w', 'post_study_q'):
        survey = Survey.objects.filter(slug=slug).first()
        if survey:
            tokens = dict(survey.tokens or {})
            tokens['phase_window'] = 'the second half'
            survey.tokens = tokens
            survey.save(update_fields=['tokens'])

    for (survey_slug, question_slug), updates in QUESTION_UPDATES.items():
        SurveyQuestion.objects.filter(
            survey__slug=survey_slug,
            slug=question_slug,
        ).update(**updates)

    for (survey_slug, question_slug, value), updates in OPTION_UPDATES.items():
        SurveyOption.objects.filter(
            question__survey__slug=survey_slug,
            question__slug=question_slug,
            value=value,
        ).update(**updates)

    SurveyQuestion.objects.filter(slug='continue_using').update(
        prompt='I would like to continue using this version of WIT in the future.',
        prompt_en='I would like to continue using this version of WIT in the future.',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0028_update_habit_platform_copy'),
    ]

    operations = [
        migrations.RunPython(clean_copy, migrations.RunPython.noop),
    ]
