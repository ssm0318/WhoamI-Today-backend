from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0052_backfill_is_public'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='is_public',
            field=models.BooleanField(default=True),
        ),
    ]
