from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0042_user_name_friends_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='name',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
