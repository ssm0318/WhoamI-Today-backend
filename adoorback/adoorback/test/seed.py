import logging
import random
import sys
import csv

from django.utils import timezone
from django.contrib.auth import get_user_model
from faker import Faker

from account.models import FriendRequest, Connection
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

    if not User.objects.filter(username='adoor').exists():
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

    # Seed Response
    questions = Question.objects.all()
    for _ in range(n):
        user = random.choice(users)
        question = random.choice(questions)
        response, created = Response.objects.get_or_create(author=user,
                                                  content=faker.text(max_nb_chars=50),
                                                  question=question)
    logging.info(
        f"{Response.objects.count()} Response(s) created!") if DEBUG else None

    # Seed Check-in
    social_battery_options = [
        'completely_drained',
        'low',
        'needs_recharge',
        'moderate',
        'fully_charged',
        'super_social'
    ]

    with open('adoorback/test/spotify_ids.txt', 'r') as file:
        spotify_ids = [line.strip() for line in file]

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

    # Seed Note
    for _ in range(n):
        user = random.choice(users)
        note, created = Note.objects.get_or_create(author=user,
                                          content=faker.text(max_nb_chars=50))
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