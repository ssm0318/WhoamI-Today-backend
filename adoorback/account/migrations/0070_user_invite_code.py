from django.db import migrations, models

import account.models


def backfill_invite_codes(apps, schema_editor):
    User = apps.get_model('account', 'User')
    used_codes = set(
        User.objects.exclude(invite_code__isnull=True)
        .exclude(invite_code='')
        .values_list('invite_code', flat=True)
    )

    for user in User.objects.filter(models.Q(invite_code__isnull=True) | models.Q(invite_code='')):
        code = account.models.generate_invite_code()
        while code in used_codes:
            code = account.models.generate_invite_code()
        user.invite_code = code
        user.save(update_fields=['invite_code'])
        used_codes.add(code)


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0069_alter_discoverfeed_category_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='invite_code',
            field=models.CharField(blank=True, max_length=12, null=True, unique=True),
        ),
        migrations.RunPython(backfill_invite_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='invite_code',
            field=models.CharField(
                blank=True,
                default=account.models.generate_invite_code,
                max_length=12,
                null=True,
                unique=True,
            ),
        ),
    ]
