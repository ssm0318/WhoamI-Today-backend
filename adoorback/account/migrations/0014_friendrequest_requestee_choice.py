# Generated by Django 4.2.14 on 2024-12-29 03:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0013_alter_connection_user1_choice_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='friendrequest',
            name='requestee_choice',
            field=models.CharField(choices=[('friend', 'Friend'), ('neighbor', 'Neighbor')], max_length=10, null=True),
        ),
    ]
