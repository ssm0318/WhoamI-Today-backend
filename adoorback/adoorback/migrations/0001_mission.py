from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Mission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('prompt', models.TextField()),
                ('type', models.CharField(choices=[('song', 'Song'), ('question', 'Question'), ('text', 'Text'), ('compliment', 'Compliment')], max_length=20)),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]
