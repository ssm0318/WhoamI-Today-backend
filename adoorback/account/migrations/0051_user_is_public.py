from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0050_backfill_subscription_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_public',
            field=models.BooleanField(null=True, blank=True),
        ),
    ]
