from django.db import migrations, transaction
from django.db.models import Q


def migrate_friends_to_connections(apps, schema_editor):
    User = apps.get_model('account', 'User')
    Connection = apps.get_model('account', 'Connection')

    def is_connected(user1, user2):
        return Connection.objects.filter(
            Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1)
        ).exists()
    
    with transaction.atomic():
        for user in User.objects.all():
            friends = user.friends.all()

            for friend in friends:
                if not is_connected(user, friend):
                    Connection.objects.create(
                        user1=user,
                        user2=friend,
                        user1_choice='friend',
                        user2_choice='friend',
                    )


def reverse_migration(apps, schema_editor):
    Connection = apps.get_model('account', 'Connection')
    Connection.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('account', '0009_friendrequest_requester_choice_connection_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_friends_to_connections, reverse_migration),
    ]