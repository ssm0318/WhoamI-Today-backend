import os
import django
from django.utils import timezone
from datetime import timedelta
from zoneinfo import ZoneInfo
import random

# Initialize Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "adoorback.settings")
django.setup()

from django.contrib.auth import get_user_model
from account.models import DiscoverFeed, DiscoverFeedMusic, FriendRequest, Interest, Persona
from note.models import Note, ShareType
from qna.models import Question, Response as QnaResponse
from adoorback.models import Mission
from check_in.models import CheckIn as CheckInModel, Song
from adoorback.utils.mission_day import get_today_la_boundary

User = get_user_model()

def seed_digest():
    print("Starting Digest Seed Process...")

    la_tz = ZoneInfo('America/Los_Angeles')
    today_7am_la = get_today_la_boundary()
    yesterday_7am_la = today_7am_la - timedelta(days=1)
    
    # We want timestamps right in the middle of yesterday
    yesterday_mid = yesterday_7am_la + timedelta(hours=12)
    # And some older ones for the curated feed
    older_time = yesterday_7am_la - timedelta(days=3)

    # 1. Ensure adoor_1 exists and is ver.W
    adoor_1, created = User.objects.get_or_create(username='adoor_1', defaults={
        'email': 'adoor_1@example.com',
        'current_ver': 'version_w'
    })
    if not created:
        adoor_1.current_ver = 'version_w'
        adoor_1.save()
    print(f"User adoor_1 configured. (version_w)")

    # Create traits
    interest_1, _ = Interest.objects.get_or_create(content='Reading')
    interest_2, _ = Interest.objects.get_or_create(content='Movies')
    persona_1, _ = Persona.objects.get_or_create(content='Introvert')
    
    adoor_1.user_interests.add(interest_1, interest_2)
    adoor_1.user_personas.add(persona_1)

    # 2. Create test users
    test_users = []
    for i in range(1, 15):
        user, _ = User.objects.get_or_create(username=f'test_w_{i}', defaults={
            'email': f'test_w_{i}@example.com',
            'current_ver': 'version_w'
        })
        user.current_ver = 'version_w'
        user.save()
        test_users.append(user)

    friend_user = test_users[0]  # test_w_1 will be a friend
    mutual_trait_user = test_users[1]  # test_w_2 will share traits
    no_trait_user = test_users[2]      # test_w_3 will share no traits
    old_post_user = test_users[3]      # test_w_4 will write older posts
    private_post_user = test_users[4]  # test_w_5 will write private posts
    music_users = test_users[1:]

    print("Cleaning up previous digest test content...")
    DiscoverFeed.objects.filter(user=adoor_1).delete()
    DiscoverFeedMusic.objects.filter(user=adoor_1).delete()
    Note.objects.filter(author__in=test_users).delete()
    QnaResponse.objects.filter(author__in=test_users).delete()
    Song.objects.filter(user__in=test_users).delete()
    CheckInModel.objects.filter(user__in=test_users).delete()

    # 3. Setup Friendships
    print("Setting up relationships...")
    friend_request, _ = FriendRequest.objects.get_or_create(requester=adoor_1, requestee=friend_user)
    friend_request.accepted = True
    friend_request.save()

    # 4. Setup Traits for Recommendation Score testing
    mutual_trait_user.user_interests.add(interest_1, interest_2)
    mutual_trait_user.user_personas.add(persona_1)
    
    old_post_user.user_interests.add(interest_1)

    # 5. Mission & Question setup
    print("Setting up Yesterday's Mission & Question...")
    yesterday_day_of_year = yesterday_7am_la.timetuple().tm_yday
    missions = list(Mission.objects.all().order_by('id'))
    if not missions:
        mission = Mission.objects.create(prompt="What made you smile yesterday?", type="Daily")
        missions = [mission]
    yesterday_mission = missions[yesterday_day_of_year % len(missions)]
    older_mission, _ = Mission.objects.get_or_create(
        prompt="Post a place you have been this week",
        defaults={'type': 'text'}
    )

    yesterday_question, _ = Question.objects.get_or_create(
        content="If you could teleport anywhere, where would you go?",
        defaults={'author': adoor_1, 'selected_dates': [yesterday_7am_la.date()]}
    )
    if yesterday_7am_la.date() not in yesterday_question.selected_dates:
        yesterday_question.selected_dates.append(yesterday_7am_la.date())
        yesterday_question.save()

    # Helper function to create Notes bypassing auto_now_add
    def create_note(author, content, share_type, visibility, created_at, mission=None):
        note = Note.objects.create(
            author=author,
            content=content,
            share_type=share_type,
            visibility=[visibility]
        )
        if mission:
            note.mission_prompt = mission.prompt
            if hasattr(note, 'mission_id'):
                note.mission_id = mission.id
            note.save()
        Note.objects.filter(id=note.id).update(created_at=created_at)
        return note

    def create_response(author, question, content, visibility, created_at):
        resp = QnaResponse.objects.create(
            author=author,
            question=question,
            content=content,
            visibility=[visibility]
        )
        QnaResponse.objects.filter(id=resp.id).update(created_at=created_at)
        return resp

    print("Generating Posts...")
    # 6. Yesterday's Mission Notes
    create_note(mutual_trait_user, "Saw a cute dog!", ShareType.MISSION, 'public', yesterday_mid, yesterday_mission)
    create_note(no_trait_user, "Ate good food.", ShareType.MISSION, 'public', yesterday_mid + timedelta(hours=1), yesterday_mission)
    create_note(friend_user, "My friend's post (should be hidden in digest).", ShareType.MISSION, 'public', yesterday_mid, yesterday_mission)
    create_note(private_post_user, "Secret mission.", ShareType.MISSION, 'private', yesterday_mid, yesterday_mission)

    # 7. Yesterday's Question Responses
    create_response(mutual_trait_user, yesterday_question, "Hawaii, right now.", 'public', yesterday_mid)
    create_response(no_trait_user, yesterday_question, "Mars, to see aliens.", 'public', yesterday_mid + timedelta(minutes=30))
    create_response(friend_user, yesterday_question, "To your house!", 'public', yesterday_mid)

    # 8. Regular Notes (Yesterday) - these become 'yesterday_post' recommended
    create_note(mutual_trait_user, "Just a regular post from yesterday.", ShareType.REGULAR, 'public', yesterday_mid)
    create_note(no_trait_user, "Another random thought.", ShareType.REGULAR, 'public', yesterday_mid)
    create_note(mutual_trait_user, "Found a quiet bookstore I want to revisit.", ShareType.MISSION, 'public', yesterday_mid + timedelta(hours=2), older_mission)

    # 9. Older Regular Notes (Curated Feed) - test scoring
    create_note(old_post_user, "This is an older curated post from someone with 1 mutual trait.", ShareType.REGULAR, 'public', older_time)
    create_note(mutual_trait_user, "This is an older post from someone with many mutual traits!", ShareType.REGULAR, 'public', older_time)
    create_note(no_trait_user, "This is an older post with 0 mutual traits.", ShareType.REGULAR, 'public', older_time)
    create_note(mutual_trait_user, "Found a quiet bookstore I want to revisit.", ShareType.MISSION, 'public', older_time + timedelta(hours=2), older_mission)

    # 10. Music / Songs
    print("Generating Songs & Check-ins...")
    spotify_track_ids = [
        "7jGLLyS5xOjEUA99KLchRM",
        "262oxM5SmAUEzvSKQNx6y4",
        "3G60LDs11Rla1QEnC53NWS",
        "0CatzXH85XWyBqqdB6qPMB",
        "0anQVQgfAippTU2lWXo6H5",
        "0pitCt3vthIiTBUFTXSUsi",
        "3Jqqlx4W1nUJb1PquxXpXS",
        "0WQtSiD8Ui01GrTJ0dXyHh",
        "69lshv2ZQHVYqwKEkj0qwa",
        "7qiZfU4dYlWllzX7mPBI3",
        "1BxfuPKGuaTgP7aM0Bbdwr",
        "7MXVkk9YMctZqd1Srtv4MB",
        "0e7ipj03S05BNilyu5bRzt",
        "1XrfEfQj3x4XfIM1nxMJJw",
    ]
    for idx, user_obj in enumerate(music_users):
        # Deactivate old check-ins
        CheckInModel.objects.filter(user=user_obj).update(is_active=False)
        
        # Create active check-in
        check_in = CheckInModel.objects.create(
            user=user_obj,
            is_active=True,
            visibility=['public'],
            song_visibility='public'
        )
        CheckInModel.objects.filter(id=check_in.id).update(created_at=yesterday_mid)

        # Create song
        # Repeat the first track for a few users so the digest can show grouped listeners.
        track_id = spotify_track_ids[0] if idx in (0, 1, 2) else spotify_track_ids[idx % len(spotify_track_ids)]
        song = Song.objects.create(
            user=user_obj,
            track_id=track_id,
            is_active=True
        )
        Song.objects.filter(id=song.id).update(created_at=yesterday_mid)

    DiscoverFeed.objects.filter(user=adoor_1).delete()
    DiscoverFeedMusic.objects.filter(user=adoor_1).delete()

    print("=============================================")
    print("Seed process completed successfully!")
    print("Generated data for user 'adoor_1' to test Discover W Digest.")
    print("Refresh your app to trigger feed generation.")
    print("=============================================")

if __name__ == '__main__':
    seed_digest()
