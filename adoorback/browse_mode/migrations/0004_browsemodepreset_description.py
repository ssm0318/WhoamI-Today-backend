from django.db import migrations, models


class Migration(migrations.Migration):
    """Add description text to BrowseModePreset.

    Single-step migration: the column has `blank=True, default=''`, so existing
    rows are populated with an empty string at column-add time — no separate
    backfill / NOT NULL step needed.
    """

    dependencies = [
        ("browse_mode", "0003_browsemodepreset_default_battery"),
    ]

    operations = [
        migrations.AddField(
            model_name="browsemodepreset",
            name="description",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
    ]
