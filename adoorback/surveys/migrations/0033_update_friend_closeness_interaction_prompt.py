from django.db import migrations


SURVEY_UPDATES = {
    'phase1_friend_closeness': {
        'old': {
            'description_en': "When you added each friend on WIT, you rated how close you felt to them on a 1–5 scale. Now that Phase 1 is wrapping up, we'd like to hear those ratings again, plus a quick note on how often you see them in person. The whole thing should take a couple of minutes — there's one short card per friend.",
            'description_ko': "WIT에서 친구를 추가할 때 1~5점으로 친밀감을 평가하셨어요. Phase 1이 마무리되는 지금, 같은 친구들에 대해 다시 한 번 평가해 주세요. 오프라인에서 얼마나 자주 만나는지도 함께 알려주세요. 친구당 한 장씩, 몇 분이면 끝납니다.",
        },
        'new': {
            'description_en': "When you added each friend on WIT, you rated how close you felt to them on a 1–5 scale. Now that Phase 1 is wrapping up, we'd like to hear those ratings again, plus a quick note on how often you interact in person. The whole thing should take a couple of minutes — there's one short card per friend.",
            'description_ko': "WIT에서 친구를 추가할 때 1~5점으로 친밀감을 평가하셨어요. Phase 1이 마무리되는 지금, 같은 친구들에 대해 다시 한 번 평가해 주세요. 직접 만나 얼마나 자주 교류하는지도 함께 알려주세요. 친구당 한 장씩, 몇 분이면 끝납니다.",
        },
    },
    'phase2_friend_closeness': {
        'old': {
            'description_en': "Same idea as last time — for each friend on your list, please re-rate how close you feel right now and how often you see them in person.",
            'description_ko': "지난번과 같은 방식이에요. 친구 한 명 한 명에 대해 지금 얼마나 가까운지와 오프라인에서 얼마나 자주 만나는지를 다시 평가해 주세요.",
        },
        'new': {
            'description_en': "Same idea as last time — for each friend on your list, please re-rate how close you feel right now and how often you interact in person.",
            'description_ko': "지난번과 같은 방식이에요. 친구 한 명 한 명에 대해 지금 얼마나 가까운지와 직접 만나 얼마나 자주 교류하는지를 다시 평가해 주세요.",
        },
    },
}

QUESTION_UPDATES = {
    'phase1_friend_closeness_intro': {
        'old': {
            'content_en': "One card per friend. For each friend below you'll see what you said about them when you added them, then rate how close you feel now and how often you see them offline. Tap their name to open their profile if you need a refresher on who they are.",
            'content_ko': "친구 한 명당 한 장씩 카드가 나옵니다. 친구를 추가할 때 평가했던 내용이 먼저 보이고, 그 다음 지금 얼마나 가까운지와 오프라인에서 얼마나 자주 만나는지를 평가하시면 돼요. 이름을 누르면 프로필이 열려요.",
        },
        'new': {
            'content_en': "One card per friend. For each friend below you'll see what you said about them when you added them, then rate how close you feel now and how often you interact in person. Tap their name to open their profile if you need a refresher on who they are.",
            'content_ko': "친구 한 명당 한 장씩 카드가 나옵니다. 친구를 추가할 때 평가했던 내용이 먼저 보이고, 그 다음 지금 얼마나 가까운지와 직접 만나 얼마나 자주 교류하는지를 평가하시면 돼요. 이름을 누르면 프로필이 열려요.",
        },
    },
    'phase2_friend_closeness_intro': {
        'old': {
            'content_en': "One card per friend. For each friend below you'll see what you said about them when you added them, then rate how close you feel now and how often you see them offline. Tap their name to open their profile if you need a refresher on who they are.",
            'content_ko': "친구 한 명당 한 장씩 카드가 나옵니다. 친구를 추가할 때 평가했던 내용이 먼저 보이고, 그 다음 지금 얼마나 가까운지와 오프라인에서 얼마나 자주 만나는지를 평가하시면 돼요. 이름을 누르면 프로필이 열려요.",
        },
        'new': {
            'content_en': "One card per friend. For each friend below you'll see what you said about them when you added them, then rate how close you feel now and how often you interact in person. Tap their name to open their profile if you need a refresher on who they are.",
            'content_ko': "친구 한 명당 한 장씩 카드가 나옵니다. 친구를 추가할 때 평가했던 내용이 먼저 보이고, 그 다음 지금 얼마나 가까운지와 직접 만나 얼마나 자주 교류하는지를 평가하시면 돼요. 이름을 누르면 프로필이 열려요.",
        },
    },
    'phase1_friend_closeness_offline': {
        'old': {
            'prompt_en': 'How often do you usually see {{friend_name}} in person, outside of school/work?',
            'prompt_ko': '{{friend_name}} 님과 학교/직장 외에 오프라인에서 얼마나 자주 만나나요?',
        },
        'new': {
            'prompt_en': 'How often do you usually interact with {{friend_name}} in person?',
            'prompt_ko': '{{friend_name}} 님과 직접 만나 얼마나 자주 교류하나요?',
        },
    },
    'phase2_friend_closeness_offline': {
        'old': {
            'prompt_en': 'How often do you usually see {{friend_name}} in person, outside of school/work?',
            'prompt_ko': '{{friend_name}} 님과 학교/직장 외에 오프라인에서 얼마나 자주 만나나요?',
        },
        'new': {
            'prompt_en': 'How often do you usually interact with {{friend_name}} in person?',
            'prompt_ko': '{{friend_name}} 님과 직접 만나 얼마나 자주 교류하나요?',
        },
    },
}


def apply_updates(apps, *, key):
    Survey = apps.get_model('surveys', 'Survey')
    SurveyQuestion = apps.get_model('surveys', 'SurveyQuestion')

    for slug, values in SURVEY_UPDATES.items():
        Survey.objects.filter(slug=slug).update(**values[key])

    for slug, values in QUESTION_UPDATES.items():
        SurveyQuestion.objects.filter(slug=slug).update(**values[key])


def update_copy(apps, schema_editor):
    apply_updates(apps, key='new')


def restore_copy(apps, schema_editor):
    apply_updates(apps, key='old')


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0032_survey_deadline_windows'),
    ]

    operations = [
        migrations.RunPython(update_copy, reverse_code=restore_copy),
    ]
