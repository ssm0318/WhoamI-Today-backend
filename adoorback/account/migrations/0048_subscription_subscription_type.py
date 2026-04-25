from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0047_backfill_per_category_friends_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='subscription_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('battery', 'Battery'),
                    ('mood', 'Mood'),
                    ('thought', 'Thought'),
                    ('song', 'Song'),
                    ('mission_of_the_day', 'Mission of the day'),
                    ('question_of_the_day', 'Question of the day'),
                    ('photo_of_the_day', 'Photo of the day'),
                    ('check_in', 'Check-in (Ver.Q)'),
                    ('post', 'Post (Ver.Q)'),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.RemoveConstraint(
            model_name='subscription',
            name='unique_subscription',
        ),
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.UniqueConstraint(
                condition=models.Q(('deleted__isnull', True), ('subscription_type__isnull', False)),
                fields=('subscriber', 'subscribed_to', 'subscription_type'),
                name='unique_subscription_by_type',
            ),
        ),
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.UniqueConstraint(
                condition=models.Q(('deleted__isnull', True), ('subscription_type__isnull', True)),
                fields=('subscriber', 'subscribed_to', 'content_type'),
                name='unique_subscription',
            ),
        ),
    ]
