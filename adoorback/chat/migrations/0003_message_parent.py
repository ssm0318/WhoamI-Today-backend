# Generated by Django 3.2.13 on 2024-03-23 08:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_userchatactivity'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='replies', to='chat.message'),
        ),
    ]
