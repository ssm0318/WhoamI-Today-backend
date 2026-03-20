import logging
import os
import random
import sys
import csv

from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from faker import Faker

from account.models import FriendRequest, Connection, Interest, Persona
from adoorback.utils.content_types import get_comment_type, get_response_type, get_question_type, get_note_type
from chat.models import ChatRoom, Message
from check_in.models import CheckIn
from comment.models import Comment
from like.models import Like
from note.models import Note
from qna.algorithms.data_crawler import select_daily_questions
from qna.models import Response, Question, ResponseRequest

DEBUG = True


def set_seed(n):
    if DEBUG:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    User = get_user_model()
    faker = Faker()

    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser(
            username='admin', email='whoami.today.official@gmail.com', password='Adoor2020:)',
            question_history=",".join(map(str, faker.random_elements(
                elements=range(1, 1501),
                length=random.randint(3, 10),
                unique=True))))
    else:
        print("Superuser already exists!")

    # Seed User
    for _ in range(10):
        username = "adoor_" + str(_ + 1)
        if User.objects.filter(username=username).count() == 0:
            User.objects.create_user(username=username,
                                     email=faker.email(),
                                     password="Adoor2020:)")
    if not User.objects.filter(username="tester2"):
        User.objects.create_user(username="tester2", email=faker.email(), password="Test1234!")
    logging.info(
        f"{User.objects.count()} User(s) created!") if DEBUG else None

    # Generate profile images for test users
    try:
        from PIL import Image, ImageDraw, ImageFont
        profile_dir = os.path.join(settings.MEDIA_ROOT, 'profile_images')
        os.makedirs(profile_dir, exist_ok=True)

        profile_colors = [
            (233, 30, 99), (156, 39, 176), (63, 81, 181), (0, 150, 136),
            (255, 87, 34), (121, 85, 72), (96, 125, 139), (76, 175, 80),
            (255, 152, 0), (33, 150, 243),
        ]
        for i in range(1, 11):
            uname = f'adoor_{i}'
            u = User.objects.get(username=uname)
            if not u.profile_image:
                color = profile_colors[i - 1]
                size = 200
                img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([0, 0, size - 1, size - 1], fill=color)
                letter = f'A{i}'
                try:
                    font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 72)
                except Exception:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), letter, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text(((size - tw) / 2, (size - th) / 2 - 10), letter,
                          fill=(255, 255, 255), font=font)
                img_path = os.path.join(profile_dir, f'{uname}.png')
                img.save(img_path, 'PNG')
                u.profile_image = f'profile_images/{uname}.png'
                u.save()
        logging.info("Profile images created for test users!") if DEBUG else None
    except ImportError:
        logging.warning("Pillow not installed, skipping profile image generation") if DEBUG else None

    # Seed Superuser
    admin = User.objects.filter(is_superuser=True).first()
    user = User.objects.get(username="adoor_2")
    logging.info("Superuser created!") if DEBUG else None

    # Seed Article/AdminQuestion/CustomQuestionPost
    users = User.objects.all()
    for _ in range(n):
        user = random.choice(users)
        (Question.objects.create(
            author=admin, is_admin_question=True, content_en=faker.word(), content_ko=faker.word()))
    logging.info(f"{Question.objects.count()} Question(s) created!") \
        if DEBUG else None

    # Select Daily Questions
    select_daily_questions()

    # Seed Response (with public visibility for discover testing)
    questions = Question.objects.all()
    for _ in range(n):
        user = random.choice(users)
        question = random.choice(questions)
        response, created = Response.objects.get_or_create(author=user,
                                                  content=faker.text(max_nb_chars=50),
                                                  question=question,
                                                  visibility=['public'])
    logging.info(
        f"{Response.objects.count()} Response(s) created!") if DEBUG else None

    # Seed Check-in
    social_battery_options = [
        'completely_drained',
        'low',
        'needs_recharge',
        'moderately_social',
        'fully_charged',
        'super_social'
    ]

    with open('adoorback/test/spotify_ids.txt', 'r') as file:
        spotify_ids = [line.strip() for line in file]

    # Well-known popular Spotify track IDs (guaranteed to resolve via oEmbed)
    popular_track_ids = [
        '7qiZfU4dY1lWllzX7mPBI3',  # Shape of You - Ed Sheeran
        '4Dvkj6JhhA12EX05fT7y2e',  # As It Was - Harry Styles
        '4cOdK2wGLETKBW3PvgPWqT',  # Never Gonna Give You Up - Rick Astley
        '3n3Ppam7vgaVa1iaRUc9Lp',  # Mr. Brightside - The Killers
        '1BxfuPKGuaTgP7aM0Bbdwr',  # Bohemian Rhapsody - Queen
        '60nZcImufyMA1MKQY3dcCH',  # Happy - Pharrell Williams
        '7MXVkk9YMctZqd1Srtv4MB',  # Starboy - The Weeknd
        '0e7ipj03S05BNilyu5bRzt',  # Somebody That I Used to Know - Gotye
        '2Fxmhks0bxGSBdJ92vM42m',  # bad guy - Billie Eilish
        '6UelLqGlWMcVH1E5c4H7lY',  # Watermelon Sugar - Harry Styles
    ]

    emoji_list = ["🥳", "😳", "😤", "⚽️", "💥", "🍀", "🦁", "🕶️", "🧚🏻", "🐑"]
    for i in range(n):
        user = random.choice(users)
        social_battery = random.choice(social_battery_options)
        track_id = random.choice(spotify_ids)
        original_check_in = CheckIn.objects.filter(user=user, is_active=True)
        if original_check_in.exists():
            for check_in in original_check_in:
                check_in.is_active = False
                check_in.save()
        checkin, created = CheckIn.objects.get_or_create(user=user,
                                                social_battery=social_battery,
                                                mood=emoji_list[i%10],
                                                description=faker.text(max_nb_chars=20),
                                                track_id=track_id,
                                                is_active=True)
    logging.info(
        f"{CheckIn.objects.count()} Check-in(s) created!") if DEBUG else None

    # Ensure each non-friend user has an active check-in with a popular Spotify track
    # (so the discover music feed always has testable data)
    discover_music_users = [
        User.objects.get(username=f'adoor_{i}') for i in range(3, 11)
    ]
    for idx, dmu in enumerate(discover_music_users):
        active = CheckIn.objects.filter(user=dmu, is_active=True).first()
        if not active or not active.track_id:
            # Deactivate any existing active check-ins
            CheckIn.objects.filter(user=dmu, is_active=True).update(is_active=False)
            CheckIn.objects.create(
                user=dmu,
                social_battery=random.choice(social_battery_options),
                mood=emoji_list[idx % 10],
                description=faker.text(max_nb_chars=20),
                track_id=popular_track_ids[idx % len(popular_track_ids)],
                is_active=True,
            )
    logging.info("Ensured active check-ins with popular Spotify tracks for discover music!") if DEBUG else None

    # Seed Note (with public visibility for discover testing)
    for _ in range(n):
        user = random.choice(users)
        note, created = Note.objects.get_or_create(author=user,
                                          content=faker.text(max_nb_chars=50),
                                          visibility=['public'])
    logging.info(
        f"{Note.objects.count()} Note(s) created!") if DEBUG else None

    # Seed Friend Request
    user_1 = User.objects.get(username="adoor_1")
    user_2 = User.objects.get(username="adoor_2")
    user_3 = User.objects.get(username="adoor_3")
    user_4 = User.objects.get(username="adoor_4")
    user_5 = User.objects.get(username="adoor_5")
    user_6 = User.objects.get(username="adoor_6")
    user_7 = User.objects.get(username="adoor_7")
    user_8 = User.objects.get(username="adoor_8")
    user_9 = User.objects.get(username="adoor_9")
    user_10 = User.objects.get(username="adoor_10")

    # FriendRequest.objects.all().delete()
    FriendRequest.objects.get_or_create(requester=user_8, requestee=user_9)
    FriendRequest.objects.get_or_create(requester=user_8, requestee=user_10)

    # Seed Friendship
    ## Since bulk_create does not call Connection model's save() method,
    ## we explicitly assign user1 as the user with smaller id
    connections = []
    for user in [user_1, user_3, user_4, user_5, user_6]:
        user1 = min(user_2, user, key=lambda u: u.id)
        user2 = max(user_2, user, key=lambda u: u.id)
        # Check if connection already exists before adding it
        if not Connection.objects.filter(user1=user1, user2=user2).exists():
            connections.append(
                Connection(
                    user1=user1,
                    user2=user2,
                    user1_choice='friend',
                    user2_choice='friend'
                )
            )
    if connections:  # Only create connections if there are any new ones
        Connection.objects.bulk_create(connections)

    for u in [user_1, user_3, user_4, user_5, user_6]:
        # Check if chat room already exists with these two users
        existing_chat_room = ChatRoom.objects.filter(users=user_2).filter(users=u)
        if not existing_chat_room.exists():
            chat_room = ChatRoom()
            chat_room.save()
            chat_room.users.add(user_2, u)

    # ===== DISCOVER FEATURE: Interests & Personas =====
    # Ensure Interest/Persona objects exist in DB
    interest_names = ['Gaming', 'Coding', 'Photography', 'Hiking', 'Cooking',
                      'Drawing', 'Reading', 'Running', 'Movies', 'Anime']
    interests_map = {}
    for name in interest_names:
        obj, _ = Interest.objects.get_or_create(content=name)
        interests_map[name] = obj

    persona_names = ['Lurker', 'ContentCreator', 'NightOwl', 'EarlyBird',
                     'MusicSharer', 'OpenBook', 'ClosedBook', 'DailyScroller']
    personas_map = {}
    for name in persona_names:
        obj, _ = Persona.objects.get_or_create(content=name)
        personas_map[name] = obj

    # Assign interests and personas to users for discover testing
    # adoor_2 (test user): Gaming, Coding, Photography + Lurker, NightOwl
    user_2_interests = ['Gaming', 'Coding', 'Photography']
    user_2_personas = ['Lurker', 'NightOwl']
    for i_name in user_2_interests:
        interests_map[i_name].users.add(user_2)
    for p_name in user_2_personas:
        personas_map[p_name].users.add(user_2)

    # adoor_7 (not friend of 2, friend of 1 & 3 → mutual friends with 2):
    # Interests: Gaming, Photography (shares 2 with adoor_2) + NightOwl (shares 1 persona)
    for i_name in ['Gaming', 'Photography']:
        interests_map[i_name].users.add(user_7)
    for p_name in ['NightOwl', 'MusicSharer']:
        personas_map[p_name].users.add(user_7)

    # adoor_8 (not friend of 2, friend of 4 → mutual friend with 2):
    # Interests: Coding, Hiking (shares 1 with adoor_2) + EarlyBird
    for i_name in ['Coding', 'Hiking']:
        interests_map[i_name].users.add(user_8)
    for p_name in ['EarlyBird']:
        personas_map[p_name].users.add(user_8)

    # adoor_9 (not friend of 2, friend of 5 & 6 → mutual friends with 2):
    # Interests: Gaming, Cooking (shares 1 with adoor_2) + Lurker (shares 1 persona)
    for i_name in ['Gaming', 'Cooking']:
        interests_map[i_name].users.add(user_9)
    for p_name in ['Lurker', 'DailyScroller']:
        personas_map[p_name].users.add(user_9)

    # adoor_10 (no mutual friends with 2, but shared traits):
    # Interests: Coding, Photography, Gaming (shares 3 with adoor_2) + NightOwl, OpenBook
    for i_name in ['Coding', 'Photography', 'Gaming']:
        interests_map[i_name].users.add(user_10)
    for p_name in ['NightOwl', 'OpenBook']:
        personas_map[p_name].users.add(user_10)

    logging.info("Interests and Personas assigned to users for discover testing!") if DEBUG else None

    # ===== DISCOVER FEATURE: Additional friend networks for mutual friends =====
    # adoor_7 is friends with adoor_1 and adoor_3 (mutual friends with adoor_2)
    for friend_user in [user_1, user_3]:
        u1 = min(user_7, friend_user, key=lambda u: u.id)
        u2 = max(user_7, friend_user, key=lambda u: u.id)
        if not Connection.objects.filter(user1=u1, user2=u2).exists():
            Connection.objects.create(user1=u1, user2=u2,
                                      user1_choice='friend', user2_choice='friend')

    # adoor_8 is friends with adoor_4 (mutual friend with adoor_2)
    u1 = min(user_8, user_4, key=lambda u: u.id)
    u2 = max(user_8, user_4, key=lambda u: u.id)
    if not Connection.objects.filter(user1=u1, user2=u2).exists():
        Connection.objects.create(user1=u1, user2=u2,
                                  user1_choice='friend', user2_choice='friend')

    # adoor_9 is friends with adoor_5 and adoor_6 (mutual friends with adoor_2)
    for friend_user in [user_5, user_6]:
        u1 = min(user_9, friend_user, key=lambda u: u.id)
        u2 = max(user_9, friend_user, key=lambda u: u.id)
        if not Connection.objects.filter(user1=u1, user2=u2).exists():
            Connection.objects.create(user1=u1, user2=u2,
                                      user1_choice='friend', user2_choice='friend')

    logging.info("Additional friend networks created for discover testing!") if DEBUG else None

    # ===== DISCOVER FEATURE: Extra public posts from non-friend users =====
    discover_post_content = [
        "Just finished a marathon coding session! Who else is up late?",
        "Photography tip: Golden hour is the best time for portraits!",
        "Anyone else obsessed with this new game? Can't stop playing!",
        "Hiking through the mountains today, the view is incredible!",
        "Made the best pasta from scratch tonight, recipe in comments!",
        "Drawing challenge day 30 - finally completed it!",
        "Just finished reading an amazing sci-fi novel, any recommendations?",
        "Morning run done! 5K personal best today!",
        "Movie night recommendations? Looking for something thrilling",
        "Late night thoughts: Why does coding feel easier at 2am?",
        "Found the perfect coffee shop for studying",
        "Weekend vibes: music, art, and good company",
        "Anyone want to play Valorant later tonight?",
        "Started learning a new programming language today",
        "Sunset photos from today's hike are unreal",
    ]

    for user in [user_7, user_8, user_9, user_10]:
        question = random.choice(questions)
        for i in range(3):
            content = random.choice(discover_post_content)
            Response.objects.get_or_create(
                author=user,
                content=f"{content} - from {user.username} #{i+1}",
                question=question,
                visibility=['public']
            )
            Note.objects.get_or_create(
                author=user,
                content=f"{random.choice(discover_post_content)} - from {user.username} note #{i+1}",
                visibility=['public']
            )

    logging.info("Extra public posts created for discover testing!") if DEBUG else None

    # Test Notifications
    response = Response.objects.first()
    note = Note.objects.first()

    # Like.objects.all().delete()
    Like.objects.get_or_create(user=user_1, content_type=get_response_type(), object_id=response.id)
    Like.objects.get_or_create(user=user_3, content_type=get_response_type(), object_id=response.id)
    Like.objects.get_or_create(user=user_4, content_type=get_response_type(), object_id=response.id)
    Like.objects.get_or_create(user=user_5, content_type=get_response_type(), object_id=response.id)
    Like.objects.get_or_create(user=user_6, content_type=get_response_type(), object_id=response.id)
    Like.objects.get_or_create(user=user_7, content_type=get_response_type(), object_id=response.id)
    Like.objects.get_or_create(user=user_1, content_type=get_note_type(), object_id=note.id)
    Like.objects.get_or_create(user=user_3, content_type=get_note_type(), object_id=note.id)
    Like.objects.get_or_create(user=user_4, content_type=get_note_type(), object_id=note.id)
    Like.objects.get_or_create(user=user_5, content_type=get_note_type(), object_id=note.id)
    Like.objects.get_or_create(user=user_6, content_type=get_note_type(), object_id=note.id)
    Like.objects.get_or_create(user=user_7, content_type=get_note_type(), object_id=note.id)
    # Like.objects.all().delete()
    # Comment.objects.all().delete()
    Comment.objects.get_or_create(author=user_1, content_type=get_response_type(), object_id=response.id,
                                  content="test comment noti")
    Comment.objects.get_or_create(author=user_3, content_type=get_response_type(), object_id=response.id,
                                  content="test comment noti")
    Comment.objects.get_or_create(author=user_4, content_type=get_response_type(), object_id=response.id,
                                  content="test comment noti")
    Comment.objects.get_or_create(author=user_5, content_type=get_response_type(), object_id=response.id,
                                  content="test comment noti")
    Comment.objects.get_or_create(author=user_6, content_type=get_response_type(), object_id=response.id,
                                  content="test comment noti")
    Comment.objects.get_or_create(author=user_7, content_type=get_response_type(), object_id=response.id,
                                  content="test comment noti")
    Comment.objects.get_or_create(author=user_1, content_type=get_note_type(), object_id=note.id,
                                  content="test note noti")
    Comment.objects.get_or_create(author=user_3, content_type=get_note_type(), object_id=note.id,
                                  content="test note noti")
    Comment.objects.get_or_create(author=user_4, content_type=get_note_type(), object_id=note.id,
                                  content="test note noti")
    Comment.objects.get_or_create(author=user_5, content_type=get_note_type(), object_id=note.id,
                                  content="test note noti")
    Comment.objects.get_or_create(author=user_6, content_type=get_note_type(), object_id=note.id,
                                  content="test note noti")
    Comment.objects.get_or_create(author=user_7, content_type=get_note_type(), object_id=note.id,
                                  content="test note noti")
    # Comment.objects.all().delete()
    # ResponseRequest.objects.all().delete()
    ResponseRequest.objects.get_or_create(requester=user_1, requestee=user_3, question=response.question)
    ResponseRequest.objects.get_or_create(requester=user_4, requestee=user_3, question=response.question)
    ResponseRequest.objects.get_or_create(requester=user_5, requestee=user_3, question=response.question)
    ResponseRequest.objects.get_or_create(requester=user_6, requestee=user_3, question=response.question)
    ResponseRequest.objects.get_or_create(requester=user_7, requestee=user_3, question=response.question)
    ResponseRequest.objects.all().delete()

    # Seed Response Request
    for _ in range(n):
        question = random.choice(questions)
        requester = random.choice(users)
        requestee = random.choice(users.exclude(id=requester.id))
        ResponseRequest.objects.get_or_create(requester=requester, requestee=requestee, question=question)
    logging.info(
        f"{ResponseRequest.objects.count()} ResponseRequest(s) created!") if DEBUG else None

    # Seed Comment (target=Feed)
    responses = Response.objects.filter(author=user_2) if Response.objects.filter(author=user_2).exists() else Response.objects.all()
    for _ in range(n):
        user = random.choice(users)
        response = random.choice(responses)
        Comment.objects.get_or_create(author=user, content_type=get_response_type(), object_id=response.id,
                                      content=faker.catch_phrase(), is_private=_ % 2)
    logging.info(
        f"{Comment.objects.count()} Comment(s) created!") if DEBUG else None

    # Seed Reply Comment (content_type=get_comment_type(), object_id=comment.id)
    comment_model = get_comment_type()
    for _ in range(n):
        comment_user = random.choice(users)
        reply_user = random.choice(users)
        comment = Comment.objects.all()[_ % 10]
        reply, created = Comment.objects.get_or_create(author=reply_user, content_type=get_comment_type(), object_id=comment.id,
                                              content=faker.catch_phrase(), is_private=comment.is_private)
        if reply.target.is_private:
            reply.is_private = True
            reply.save()
    logging.info(f"{Comment.objects.filter(content_type=comment_model).count()} Repl(ies) created!") \
        if DEBUG else None

    # Test Notification
    comment = Comment.objects.filter(content_type=comment_model).last()
    reply = Comment.objects.filter(content_type=get_response_type()).last()
    # Like.objects.all().delete()
    Like.objects.get_or_create(user=user_1, content_type=get_comment_type(), object_id=comment.id)
    Like.objects.get_or_create(user=user_3, content_type=get_comment_type(), object_id=comment.id)
    Like.objects.get_or_create(user=user_4, content_type=get_comment_type(), object_id=comment.id)
    Like.objects.get_or_create(user=user_5, content_type=get_comment_type(), object_id=comment.id)
    Like.objects.get_or_create(user=user_6, content_type=get_comment_type(), object_id=comment.id)
    Like.objects.get_or_create(user=user_7, content_type=get_comment_type(), object_id=comment.id)
    Like.objects.get_or_create(user=user_1, content_type=get_comment_type(), object_id=reply.id)
    Like.objects.get_or_create(user=user_3, content_type=get_comment_type(), object_id=reply.id)
    Like.objects.get_or_create(user=user_4, content_type=get_comment_type(), object_id=reply.id)
    Like.objects.get_or_create(user=user_5, content_type=get_comment_type(), object_id=reply.id)
    Like.objects.get_or_create(user=user_6, content_type=get_comment_type(), object_id=reply.id)
    Like.objects.get_or_create(user=user_7, content_type=get_comment_type(), object_id=reply.id)
    # Like.objects.all().delete()

    # Seed Like
    for i in range(n):
        user = random.choice(users)
        question = Question.objects.all()[i:i + 1].first()
        response = Response.objects.all()[i:i + 1].first()
        comment = Comment.objects.comments_only()[i]
        reply = Comment.objects.replies_only()[i]
        Like.objects.get_or_create(user=user, content_type=get_question_type(), object_id=question.id)
        Like.objects.get_or_create(user=user, content_type=get_response_type(), object_id=response.id)
        Like.objects.get_or_create(user=user, content_type=get_comment_type(), object_id=comment.id)
        Like.objects.get_or_create(user=user, content_type=get_comment_type(), object_id=reply.id)
    logging.info(
        f"{Like.objects.count()} Like(s) created!") if DEBUG else None

    # Seed Chat Messages
    for chat_room in ChatRoom.objects.all():
        participants = chat_room.users.all()
        for p in participants:
            timestamp = timezone.now()
            for _ in range(random.randint(3, 5)):
                Message.objects.get_or_create(sender=p, content=faker.text(max_nb_chars=50), timestamp=timestamp,
                                              chat_room=chat_room)
    logging.info(
        f"{Message.objects.count()} Message(s) created!") if DEBUG else None