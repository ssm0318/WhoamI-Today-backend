from django.db import migrations


FEATURE_SURVEY_SLUGS = ['feature_eval_w', 'feature_eval_w_part2']
DEPRECATED_HIDE_RULE = {
    'depends_on': '__deprecated_feature_never_shown__',
    'show_when_value': '__show__',
}

FEATURE_RATING_SLUGS = [
    'goal1_feat_dailyq',
    'goal1_feat_qsend',
    'goal2_feat_browse',
    'goal2_feat_social_battery_level',
    'goal3_feat_checkin_reactions',
    'goal3_feat_emoji',
    'goal3_feat_private',
    'goal3_feat_profile_list',
    'goal3_feat_ping',
    'goal4_feat_close_filter',
    'goal4_feat_granular_sub',
    'goal5_feat_posts',
    'goal5_feat_checkins',
    'goal6_feat_playlist',
    'goal6_feat_widget',
    'goal6_feat_survey_digest',
    'goal6_feat_mission',
    'goal7_feat_discover',
    'goal7_feat_nth_degree',
    'goal7_feat_profile_decoration',
    'goal8_feat_nonpublic',
    'goal8_feat_view_as',
    'goal8_feat_retroactive',
]

PROMPT_UPDATES = {
    'goal3_feat_profile_list': '**Profile-list feed** — I liked this feature.',
    'goal6_feat_survey_digest': '**Survey of the Day** — I liked this feature.',
    'goal6_feat_survey_digest_enjoy': (
        'What, if anything, did you enjoy most about the survey of the day feature?'
    ),
    'goal6_feat_survey_digest_dislike': (
        'What, if anything, did you dislike most about the survey of the day feature?'
    ),
    'goal7_feat_discover': '**Daily Digest** — I liked this feature.',
    'goal7_feat_discover_enjoy': (
        'What, if anything, did you enjoy most about the Daily Digest feature?'
    ),
    'goal7_feat_discover_dislike': (
        'What, if anything, did you dislike most about the Daily Digest feature?'
    ),
}

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


def apply_feature_eval_w_copy_cleanup(apps, schema_editor):
    SurveyQuestion = apps.get_model('surveys', 'SurveyQuestion')

    for question in SurveyQuestion.objects.filter(
        survey__slug__in=FEATURE_SURVEY_SLUGS,
        slug__in=FEATURE_RATING_SLUGS,
    ):
        _set_text(question, 'description', '')
        question.save(update_fields=['description', 'description_en', 'description_ko'])

    for slug, prompt in PROMPT_UPDATES.items():
        for question in SurveyQuestion.objects.filter(
            survey__slug__in=FEATURE_SURVEY_SLUGS,
            slug=slug,
        ):
            _set_text(question, 'prompt', prompt)
            question.save(update_fields=['prompt', 'prompt_en', 'prompt_ko'])

    for question in SurveyQuestion.objects.filter(
        survey__slug__in=FEATURE_SURVEY_SLUGS,
        slug__in=DEPRECATED_FEATURE_SLUGS,
    ):
        _set_text(question, 'prompt', 'Deprecated feature (hidden)')
        _set_text(question, 'description', '')
        question.required = False
        question.result_hidden = True
        question.conditional_display = DEPRECATED_HIDE_RULE
        question.save(
            update_fields=[
                'prompt',
                'prompt_en',
                'prompt_ko',
                'description',
                'description_en',
                'description_ko',
                'required',
                'result_hidden',
                'conditional_display',
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0040_feature_eval_w_final_feature_set'),
    ]

    operations = [
        migrations.RunPython(apply_feature_eval_w_copy_cleanup, migrations.RunPython.noop),
    ]
