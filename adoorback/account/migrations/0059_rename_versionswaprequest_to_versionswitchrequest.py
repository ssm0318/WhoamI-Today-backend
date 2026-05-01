from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0058_versionswaprequest_and_more'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='VersionSwapRequest',
            new_name='VersionSwitchRequest',
        ),
        migrations.RemoveConstraint(
            model_name='versionswitchrequest',
            name='unique_pending_version_swap_request',
        ),
        migrations.AddConstraint(
            model_name='versionswitchrequest',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status', 'pending'), ('deleted__isnull', True)),
                fields=('user',),
                name='unique_pending_version_switch_request',
            ),
        ),
        migrations.AlterField(
            model_name='versionswitchrequest',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='version_switch_requests',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RenameIndex(
            model_name='versionswitchrequest',
            new_name='account_ver_created_7033ae_idx',
            old_name='account_ver_created_2c4819_idx',
        ),
    ]
