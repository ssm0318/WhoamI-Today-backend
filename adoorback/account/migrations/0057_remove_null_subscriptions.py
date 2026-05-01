"""Remove legacy Subscription rows where subscription_type is NULL.

These were created by the old CheckInSubscribeAdd endpoint and the
close-friend auto-subscribe signal before they were updated to use
per-component subscription_type values (battery, mood, thought, song).
"""
from django.db import migrations


def remove_null_subscriptions(apps, schema_editor):
    Subscription = apps.get_model('account', 'Subscription')
    deleted_count, _ = Subscription.objects.filter(
        subscription_type__isnull=True,
    ).delete()
    if deleted_count:
        print(f'  Deleted {deleted_count} legacy NULL subscription row(s)')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0056_rename_account_fri_evaluat_idx_account_fri_evaluat_a9f25b_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(remove_null_subscriptions, noop),
    ]
