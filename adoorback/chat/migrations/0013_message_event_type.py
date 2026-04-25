# Generated for member add/leave system messages

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0012_wit_admin_flags_notnull"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="event_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Message"),
                    ("member_added", "Member Added"),
                    ("member_left", "Member Left"),
                ],
                default="",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="event_target_users",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
