# Generated by Django 3.2.13 on 2023-10-22 08:15

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0011_auto_20230908_2232'),
    ]

    operations = [
        migrations.CreateModel(
            name='FriendGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('friends', models.ManyToManyField(blank=True, to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='friend_groups', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]