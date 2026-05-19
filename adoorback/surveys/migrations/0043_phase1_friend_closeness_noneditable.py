from django.db import migrations


def make_phase1_friend_closeness_noneditable(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    Survey.objects.filter(slug='phase1_friend_closeness').update(
        editable=False,
        repeatable=False,
    )


def restore_phase1_friend_closeness_one_shot(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    Survey.objects.filter(slug='phase1_friend_closeness').update(editable=False)


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0042_seed_friend_closeness_part2_recovery'),
    ]

    operations = [
        migrations.RunPython(
            make_phase1_friend_closeness_noneditable,
            reverse_code=restore_phase1_friend_closeness_one_shot,
        ),
    ]
