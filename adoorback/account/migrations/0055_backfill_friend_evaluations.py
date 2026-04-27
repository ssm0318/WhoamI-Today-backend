from django.db import migrations


def backfill_evaluations(apps, schema_editor):
    """Create skipped FriendEvaluation records for all existing accepted FriendRequests,
    so existing users are not affected by the new evaluation requirement."""
    FriendRequest = apps.get_model('account', 'FriendRequest')
    FriendEvaluation = apps.get_model('account', 'FriendEvaluation')

    accepted_requests = FriendRequest.objects.filter(
        accepted=True, deleted__isnull=True
    )

    evaluations_to_create = []
    for fr in accepted_requests:
        # Requester's evaluation
        evaluations_to_create.append(FriendEvaluation(
            evaluator=fr.requester,
            evaluated_user=fr.requestee,
            friend_request=fr,
            context='request',
            skipped=True,
        ))
        # Requestee's evaluation
        evaluations_to_create.append(FriendEvaluation(
            evaluator=fr.requestee,
            evaluated_user=fr.requester,
            friend_request=fr,
            context='accept',
            skipped=True,
        ))

    FriendEvaluation.objects.bulk_create(evaluations_to_create, ignore_conflicts=True)


def reverse_backfill(apps, schema_editor):
    """Remove all backfilled skipped evaluations."""
    FriendEvaluation = apps.get_model('account', 'FriendEvaluation')
    FriendEvaluation.objects.filter(skipped=True, closeness__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0054_create_friend_evaluation'),
    ]

    operations = [
        migrations.RunPython(backfill_evaluations, reverse_backfill),
    ]
