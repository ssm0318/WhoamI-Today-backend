from django.db import migrations

def copy_actors(apps, schema_editor):
    Notification = apps.get_model('notification', 'Notification')
    for notification in Notification.objects.all():
        notification.new_actors.set(notification.actors.all())

class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0002_notificationactor_notification_new_actors'),
    ]

    operations = [
        migrations.RunPython(copy_actors),
    ]