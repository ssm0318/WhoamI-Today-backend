"""Seed a few mock mission Notes for visual testing of the mission post UI.

Run with:
    DB_HOST=localhost python manage.py shell < adoorback/adoorback/test/seed_mission_notes.py

Creates mission Notes for adoor_1 (attempts 1, 2, 3) with a hardcoded prompt
snapshot so the prompt + attempt chip render in the feed. Independent of the
Mission model row — useful when the local DB Mission table is in a state
that prevents the ORM from querying it.
"""

from django.contrib.auth import get_user_model

from note.models import Note, ShareType

User = get_user_model()


SAMPLE_PROMPT = 'Share a song that matches your mood right now'


def seed():
    user = User.objects.filter(username='adoor_1').first()
    if user is None:
        print('adoor_1 not found — run set_seed(n) first.')
        return

    samples = [
        ('Just discovered this lo-fi track. Been on repeat all afternoon 🎧', 1),
        ('Sunday in the park kind of energy today.', 2),
        ('Comfort show pick: Dimension 20. No notes.', 3),
    ]

    created = 0
    for content, attempt in samples:
        existing = Note.objects.filter(
            author=user,
            share_type=ShareType.MISSION,
            mission_attempt_number=attempt,
            content=content,
        ).first()
        if existing:
            print(f'  attempt {attempt} already seeded (id={existing.id})')
            continue
        note = Note.objects.create(
            author=user,
            content=content,
            visibility=['public'],
            share_type=ShareType.MISSION,
            mission_prompt=SAMPLE_PROMPT,
            mission_attempt_number=attempt,
        )
        print(f'  attempt {attempt} -> Note id={note.id}')
        created += 1

    print(f'Seeded {created} mission note(s) for {user.username}.')
    print(f'Mission prompt used: "{SAMPLE_PROMPT}"')
    print('View these on the Discover feed or by visiting /users/adoor_1.')


seed()
