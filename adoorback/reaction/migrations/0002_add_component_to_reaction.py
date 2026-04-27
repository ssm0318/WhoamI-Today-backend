from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reaction', '0001_initial'),
    ]

    operations = [
        # 1. Add nullable component field
        migrations.AddField(
            model_name='reaction',
            name='component',
            field=models.CharField(
                blank=True,
                choices=[
                    ('battery', 'Battery'),
                    ('mood', 'Mood'),
                    ('thought', 'Thought'),
                    ('song', 'Song'),
                ],
                max_length=20,
                null=True,
            ),
        ),
        # 2. Remove old unique constraint
        migrations.RemoveConstraint(
            model_name='reaction',
            name='unique_reaction',
        ),
        # 3. Add two new constraints: one for non-component reactions, one for component reactions
        migrations.AddConstraint(
            model_name='reaction',
            constraint=models.UniqueConstraint(
                condition=models.Q(('deleted__isnull', True), ('component__isnull', True)),
                fields=('user', 'emoji', 'content_type', 'object_id'),
                name='unique_reaction_no_component',
            ),
        ),
        migrations.AddConstraint(
            model_name='reaction',
            constraint=models.UniqueConstraint(
                condition=models.Q(('deleted__isnull', True), ('component__isnull', False)),
                fields=('user', 'emoji', 'content_type', 'object_id', 'component'),
                name='unique_reaction_with_component',
            ),
        ),
    ]
