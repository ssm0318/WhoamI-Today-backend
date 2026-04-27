from django.db import migrations


def backfill_is_public(apps, schema_editor):
    User = apps.get_model('account', 'User')
    User.objects.filter(is_public__isnull=True).update(is_public=True)


def reverse_backfill(apps, schema_editor):
    User = apps.get_model('account', 'User')
    User.objects.update(is_public=None)


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0051_user_is_public'),
    ]

    operations = [
        migrations.RunPython(backfill_is_public, reverse_backfill),
    ]
