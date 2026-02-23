from django.db import migrations

def update_visibility(apps, schema_editor):
    CheckIn = apps.get_model('check_in', 'CheckIn')
    # Update check-ins where visibility is empty ([])
    CheckIn.objects.filter(visibility=[]).update(visibility=['public'])

class Migration(migrations.Migration):

    dependencies = [
        ('check_in', '0008_alter_checkin_visibility'),
    ]

    operations = [
        migrations.RunPython(update_visibility),
    ]
