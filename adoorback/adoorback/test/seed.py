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
from chat.models import ChatRoom, Message, get_or_create_chat_room
from check_in.models import CheckIn, Poke, Song
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

    # Select Daily Questions for the past 10 days (including today)
    import datetime
    today = datetime.date.today()
    for day_offset in range(10):
        select_daily_questions(set_date=today - datetime.timedelta(days=day_offset))

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

    emoji_pool = ["🥳", "😳", "😤", "⚽️", "💥", "🍀", "🦁", "🕶️", "🧚🏻", "🐑",
                   "😎", "🔥", "🎉", "💀", "😂", "🤔", "😴", "🙃", "✨", "🌈"]
    for i in range(n):
        user = random.choice(users)
        social_battery = random.choice(social_battery_options)
        track_id = random.choice(spotify_ids)
        original_check_in = CheckIn.objects.filter(user=user, is_active=True)
        if original_check_in.exists():
            for check_in in original_check_in:
                check_in.is_active = False
                check_in.save()
        # Generate 1-5 random mood emojis per user
        num_emojis = random.randint(1, 5)
        mood_emojis = random.sample(emoji_pool, num_emojis)
        checkin, created = CheckIn.objects.get_or_create(user=user,
                                                social_battery=social_battery,
                                                mood=mood_emojis,
                                                thought=faker.text(max_nb_chars=20),
                                                is_active=True)
        # Create Song separately
        Song.objects.filter(user=user, is_active=True).update(is_active=False)
        Song.objects.create(user=user, track_id=track_id, is_active=True)
    logging.info(
        f"{CheckIn.objects.count()} Check-in(s) created!") if DEBUG else None
    logging.info(
        f"{Song.objects.count()} Song(s) created!") if DEBUG else None

    # Ensure each non-friend user has an active song with a popular Spotify track
    # (so the discover music feed always has testable data)
    discover_music_users = [
        User.objects.get(username=f'adoor_{i}') for i in range(3, 11)
    ]
    for idx, dmu in enumerate(discover_music_users):
        active_song = Song.objects.filter(user=dmu, is_active=True).first()
        if not active_song:
            Song.objects.filter(user=dmu, is_active=True).update(is_active=False)
            Song.objects.create(
                user=dmu,
                track_id=popular_track_ids[idx % len(popular_track_ids)],
                is_active=True,
            )
    logging.info("Ensured active songs with popular Spotify tracks for discover music!") if DEBUG else None

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
        get_or_create_chat_room(user_2, u)

    # Add more friends for adoor_1 (for testing new posts, poke, etc.)
    for friend_user in [user_3, user_4, user_5, user_6]:
        u1_sorted = min(user_1, friend_user, key=lambda u: u.id)
        u2_sorted = max(user_1, friend_user, key=lambda u: u.id)
        if not Connection.objects.filter(user1=u1_sorted, user2=u2_sorted).exists():
            Connection.objects.create(
                user1=u1_sorted, user2=u2_sorted,
                user1_choice='friend', user2_choice='friend'
            )
    logging.info("Extra friends added for adoor_1!") if DEBUG else None

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
        users = [chat_room.user1, chat_room.user2]
        for sender in users:
            receiver = chat_room.user2 if sender == chat_room.user1 else chat_room.user1
            for _ in range(random.randint(3, 5)):
                Message.objects.create(
                    sender=sender, receiver=receiver,
                    content=faker.text(max_nb_chars=50),
                    chat_room=chat_room
                )
    logging.info(
        f"{Message.objects.count()} Message(s) created!") if DEBUG else None

    # ===== NEW POST TESTING =====
    # Create recent unread posts from adoor_1's friends so the "New post" badge shows
    new_post_authors = [user_2, user_3, user_7]
    new_post_content = [
        "Just discovered an amazing coffee shop nearby!",
        "Anyone want to go hiking this weekend?",
        "New song on repeat - can't stop listening",
        "Finally finished that book I've been reading",
        "Late night thoughts: what if we could fly?",
    ]
    for author in new_post_authors:
        note = Note.objects.create(
            author=author,
            content=random.choice(new_post_content),
            visibility=['friends'],
        )
        # Do NOT add adoor_1 to readers — this makes it "unread" / "new"
        note.readers.add(author)
        logging.info(f"New unread post created by {author.username}") if DEBUG else None

    # Also create a TMI post and a Photo post for testing share types
    Note.objects.create(
        author=user_2,
        content="Hot take: pineapple on pizza is actually good",
        visibility=['friends'],
        share_type='tmi_of_the_day',
    )
    Note.objects.create(
        author=user_3,
        content="Sunset from my window today",
        visibility=['friends'],
        share_type='photo_of_the_day',
    )
    # Make adoor_3 have NO active check-in (for poke testing)
    # Deactivate all check-ins and songs for adoor_3
    CheckIn.objects.filter(user=user_3, is_active=True).update(is_active=False)
    Song.objects.filter(user=user_3, is_active=True).update(is_active=False)
    logging.info("adoor_3 check-in cleared for poke testing!") if DEBUG else None

    logging.info("New post test data created!") if DEBUG else None

    # ===== CHIP CATEGORY TESTING =====
    # Assign chips with proper categories for the 7-category system
    from account.models import CHIP_CATEGORY_CHOICES
    category_chips = {
        'music_entertainment': ['Hip-Hop', 'K-Pop', 'Anime', 'Lo-Fi', 'Podcasts'],
        'hobbies_activities': ['Gaming', 'Basketball', 'Photography', 'Cooking', 'Hiking', 'Coding'],
        'on_my_mind': ['Psychology', 'Mental Health', 'AI & Tech', 'Finance'],
        'as_a_friend': ['Good Listener', 'Night Owl', 'Overthinker', 'Hype Person'],
        'online_persona': ['Lurker', 'Meme Collector', 'Late Replier', 'Content Creator'],
        'favorite_platform': ['Instagram', 'YouTube', 'Discord', 'TikTok'],
        'least_favorite_platform': ['X / Twitter', 'Threads'],
    }
    for cat_key, chip_labels in category_chips.items():
        for label in chip_labels:
            interest, _ = Interest.objects.get_or_create(content=label)
            interest.category = cat_key
            interest.save()

    # Assign chips to users with category awareness
    user_chip_assignments = {
        user_1: {'music_entertainment': ['Hip-Hop', 'Anime'], 'hobbies_activities': ['Gaming', 'Coding'], 'online_persona': ['Lurker']},
        user_2: {'music_entertainment': ['K-Pop', 'Lo-Fi'], 'hobbies_activities': ['Photography', 'Hiking'], 'as_a_friend': ['Good Listener']},
        user_3: {'hobbies_activities': ['Basketball', 'Cooking'], 'on_my_mind': ['Psychology'], 'favorite_platform': ['YouTube']},
        user_5: {'music_entertainment': ['Podcasts'], 'on_my_mind': ['AI & Tech', 'Finance'], 'online_persona': ['Content Creator']},
        user_7: {'hobbies_activities': ['Gaming', 'Photography'], 'as_a_friend': ['Night Owl', 'Hype Person'], 'favorite_platform': ['Discord']},
    }
    for user, categories in user_chip_assignments.items():
        for cat_key, labels in categories.items():
            for label in labels:
                interest = Interest.objects.get(content=label)
                user.user_interests.add(interest)
    logging.info("Chip category test data created!") if DEBUG else None

    # ===== COMPREHENSIVE EDGE CASE TESTING =====

    # 1. User with partial check-in (only song, no status/battery)
    CheckIn.objects.filter(user=user_4, is_active=True).update(
        social_battery=None, mood=[], thought=None
    )
    logging.info("adoor_4: partial check-in (song only)") if DEBUG else None

    # 2. User with same platform as both Favorite and Least Favorite
    fav_ig = Interest.objects.get_or_create(content='Instagram')[0]
    fav_ig.category = 'favorite_platform'
    fav_ig.save()
    least_ig = Interest.objects.get_or_create(content='Instagram (least)')[0]
    least_ig.category = 'least_favorite_platform'
    least_ig.save()
    user_6.user_interests.add(fav_ig, least_ig)
    logging.info("adoor_6: same platform favorite + least favorite") if DEBUG else None

    # 3. Two users sharing same custom chip text (case-insensitive match)
    from account.models import CustomChip
    CustomChip.objects.get_or_create(user=user_1, text='late night coder', category='hobbies_activities')
    CustomChip.objects.get_or_create(user=user_5, text='Late Night Coder', category='hobbies_activities')
    logging.info("Custom chip mutual match: adoor_1 + adoor_5") if DEBUG else None

    # 4. User with max 5 custom chips in one category
    for i in range(5):
        CustomChip.objects.get_or_create(
            user=user_2,
            text=f'custom hobby {i+1}',
            category='hobbies_activities'
        )
    logging.info("adoor_2: max 5 custom chips in hobbies") if DEBUG else None

    # 5. User with friends-only visibility flags set
    user_6.bio_friends_only = True
    user_6.interests_friends_only = True
    user_6.pronouns_friends_only = True
    user_6.save()
    logging.info("adoor_6: friends-only visibility on bio/interests/pronouns") if DEBUG else None

    # 6. Ensure 2nd and 3rd degree connections exist for degree badge testing
    # adoor_8 is NOT friends with adoor_1 but IS friends with adoor_2 (mutual friend)
    # This makes adoor_8 a 2nd degree connection to adoor_1
    u8 = User.objects.get(username='adoor_8')
    u1_sorted = min(user_2, u8, key=lambda u: u.id)
    u2_sorted = max(user_2, u8, key=lambda u: u.id)
    if not Connection.objects.filter(user1=u1_sorted, user2=u2_sorted).exists():
        Connection.objects.create(user1=u1_sorted, user2=u2_sorted, user1_choice='friend', user2_choice='friend')
    logging.info("adoor_8: 2nd degree connection to adoor_1 via adoor_2") if DEBUG else None

    # adoor_10 is 3rd+ degree (no mutual friends with adoor_1)
    logging.info("adoor_10: 3rd+ degree connection to adoor_1") if DEBUG else None

    # 7. Users with bio, pronouns, profile data for visibility testing
    user_6.bio = "Secret bio only for friends"
    user_6.pronouns = "they/them"
    user_6.save()
    logging.info("adoor_6: has bio + pronouns for visibility testing") if DEBUG else None

    # ===== CHECK-IN REACTIONS & NUDGE TEST DATA =====
    from reaction.models import Reaction
    from django.contrib.contenttypes.models import ContentType

    checkin_ct = ContentType.objects.get_for_model(CheckIn)

    # adoor_1 reacts to adoor_2's check-in (🔥 and 👍)
    ci_2 = CheckIn.objects.filter(user=user_2, is_active=True).first()
    if ci_2:
        Reaction.objects.get_or_create(user=user_1, emoji='🔥', content_type=checkin_ct, object_id=ci_2.id)
        Reaction.objects.get_or_create(user=user_1, emoji='👍', content_type=checkin_ct, object_id=ci_2.id)
        logging.info("adoor_1 reacted 🔥 and 👍 to adoor_2's check-in") if DEBUG else None

    # adoor_2 reacts to adoor_5's check-in (❤️)
    ci_5 = CheckIn.objects.filter(user=user_5, is_active=True).first()
    if ci_5:
        Reaction.objects.get_or_create(user=user_2, emoji='❤️', content_type=checkin_ct, object_id=ci_5.id)
        logging.info("adoor_2 reacted ❤️ to adoor_5's check-in") if DEBUG else None

    # adoor_5 reacts to adoor_1's check-in (🤗 and 🚀)
    ci_1 = CheckIn.objects.filter(user=user_1, is_active=True).first()
    if ci_1:
        Reaction.objects.get_or_create(user=user_5, emoji='🤗', content_type=checkin_ct, object_id=ci_1.id)
        Reaction.objects.get_or_create(user=user_5, emoji='🚀', content_type=checkin_ct, object_id=ci_1.id)
        logging.info("adoor_5 reacted 🤗 and 🚀 to adoor_1's check-in") if DEBUG else None

    # Nudges: adoor_1 nudges adoor_3 for all 4 components (adoor_3 has empty check-in)
    for comp in ['battery', 'mood', 'thought', 'song']:
        Poke.objects.get_or_create(sender=user_1, receiver=user_3, component_type=comp)
    logging.info("adoor_1 nudged adoor_3 for all 4 components") if DEBUG else None

    # Nudges: adoor_2 nudges adoor_4 for mood and song only
    Poke.objects.get_or_create(sender=user_2, receiver=user_4, component_type='mood')
    Poke.objects.get_or_create(sender=user_2, receiver=user_4, component_type='song')
    logging.info("adoor_2 nudged adoor_4 for mood and song") if DEBUG else None

    # Nudges: adoor_5 nudges adoor_1 for thought (so adoor_1 sees a received nudge)
    Poke.objects.get_or_create(sender=user_5, receiver=user_1, component_type='thought')
    logging.info("adoor_5 nudged adoor_1 for thought") if DEBUG else None

    logging.info("Check-in reactions & nudge test data created!") if DEBUG else None

    # ===== CHECK-IN VISIBILITY TEST DATA =====
    from datetime import timedelta

    # adoor_5: mood set to "only_me" (should be hidden from friends)
    ci_5 = CheckIn.objects.filter(user=user_5, is_active=True).first()
    if ci_5:
        ci_5.mood_visibility = 'only_me'
        ci_5.thought_visibility = 'close_friends'
        ci_5.save()
        logging.info("adoor_5: mood=only_me, thought=close_friends") if DEBUG else None

    # adoor_6: battery set to "public", thought to "only_me"
    ci_6 = CheckIn.objects.filter(user=user_6, is_active=True).first()
    if ci_6:
        ci_6.battery_visibility = 'public'
        ci_6.thought_visibility = 'only_me'
        ci_6.save()
        logging.info("adoor_6: battery=public, thought=only_me") if DEBUG else None

    # adoor_7: simulate auto-archive by setting battery_updated_at to 13 hours ago
    ci_7 = CheckIn.objects.filter(user=user_7, is_active=True).first()
    if ci_7:
        ci_7.battery_updated_at = timezone.now() - timedelta(hours=13)
        ci_7.mood_updated_at = timezone.now() - timedelta(hours=13)
        # Use update to bypass save() which would reset timestamps
        CheckIn.objects.filter(pk=ci_7.pk).update(
            battery_updated_at=timezone.now() - timedelta(hours=13),
            mood_updated_at=timezone.now() - timedelta(hours=13),
        )
        logging.info("adoor_7: battery and mood auto-archived (13h old)") if DEBUG else None

    # adoor_8: all components set to "public"
    ci_8 = CheckIn.objects.filter(user=u8, is_active=True).first()
    if ci_8:
        ci_8.battery_visibility = 'public'
        ci_8.mood_visibility = 'public'
        ci_8.thought_visibility = 'public'
        ci_8.song_visibility = 'public'
        ci_8.save()
        logging.info("adoor_8: all components public") if DEBUG else None

    logging.info("Check-in visibility test data created!") if DEBUG else None

    logging.info("=== Comprehensive seed data complete! ===") if DEBUG else None