from django.db import migrations


CHECK_IN_COMPONENT_TYPES = ('battery', 'mood', 'thought', 'song')


def expand_check_in_subscriptions(apps, schema_editor):
    """Existing single-row check-in subscription -> 4 rows (battery/mood/thought/song)."""
    Subscription = apps.get_model('account', 'Subscription')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    try:
        check_in_ct = ContentType.objects.get(app_label='check_in', model='checkin')
    except ContentType.DoesNotExist:
        return

    legacy_rows = list(Subscription.objects.filter(
        content_type=check_in_ct,
        subscription_type__isnull=True,
        deleted__isnull=True,
    ))

    new_rows = []
    for row in legacy_rows:
        row.subscription_type = CHECK_IN_COMPONENT_TYPES[0]
        row.save(update_fields=['subscription_type'])
        for stype in CHECK_IN_COMPONENT_TYPES[1:]:
            new_rows.append(Subscription(
                subscriber=row.subscriber,
                subscribed_to=row.subscribed_to,
                content_type=check_in_ct,
                subscription_type=stype,
            ))

    if new_rows:
        Subscription.objects.bulk_create(new_rows)


def collapse_check_in_subscriptions(apps, schema_editor):
    """Reverse: collapse battery/mood/thought/song rows back to a single legacy row."""
    Subscription = apps.get_model('account', 'Subscription')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    try:
        check_in_ct = ContentType.objects.get(app_label='check_in', model='checkin')
    except ContentType.DoesNotExist:
        return

    pairs = Subscription.objects.filter(
        content_type=check_in_ct,
        subscription_type__in=CHECK_IN_COMPONENT_TYPES,
        deleted__isnull=True,
    ).values_list('subscriber_id', 'subscribed_to_id').distinct()

    for subscriber_id, subscribed_to_id in pairs:
        Subscription.objects.filter(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id,
            content_type=check_in_ct,
            subscription_type__in=CHECK_IN_COMPONENT_TYPES,
        ).delete()
        Subscription.objects.create(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id,
            content_type=check_in_ct,
            subscription_type=None,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0048_subscription_subscription_type'),
    ]

    operations = [
        migrations.RunPython(expand_check_in_subscriptions, collapse_check_in_subscriptions),
    ]
