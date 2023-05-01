import random
import logging
import sys

from django.utils import timezone
from django.contrib.auth import get_user_model
from faker import Faker

from adoorback.utils.content_types import get_comment_type
from account.models import FriendRequest
from feed.models import Article, Response, Question, ResponseRequest
from comment.models import Comment
from like.models import Like

DEBUG = False


def set_seed(n):
    if DEBUG:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    User = get_user_model()
    faker = Faker()

    # Seed User
    for _ in range(2):
        User.objects.create_user(username="adoor_" + str(_+1),
                                 email=faker.email(),
                                 password="adoor2020:)")
    logging.info(
        f"{User.objects.count()} User(s) created!") if DEBUG else None

    # Seed Superuser
    if User.objects.count() == 2:
        User.objects.create_superuser(
            username='adoor', email='adoor.team@gmail.com', password='adoor2020:)',
            question_history=",".join(map(str, faker.random_elements(
                elements=range(1, 1501),
                length=random.randint(3, 10),
                unique=True))))
    admin = User.objects.get(username='adoor')
    logging.info("Superuser created!") if DEBUG else None

    # Seed Article/AdminQuestion/CustomQuestionPost
    users = User.objects.all()
    for _ in range(n):
        user = random.choice(users)
        article = Article.objects.create(author=user,
                                         content=faker.catch_phrase(),
                                         share_with_friends=random.choice(
                                             [True, False]),
                                         share_anonymously=random.choice([True, False]))
        if not article.share_anonymously and not article.share_with_friends:
            article.share_with_friends = True
            article.save()
        Question.objects.create(
            author=admin, is_admin_question=True, content=faker.word())
        Question.objects.create(
            author=user, is_admin_question=False, content=faker.word())
    logging.info(
        f"{Article.objects.count()} Article(s) created!") if DEBUG else None
    logging.info(f"{Question.objects.count()} Question(s) created!") \
        if DEBUG else None

    # Select Daily Questions
    daily_questions = Question.objects.filter(
        selected_date__isnull=True).order_by('?')[:30]
    for question in daily_questions:
        question.selected_date = timezone.now()
        question.save()

    # Seed Response
    questions = Question.objects.all()
    for _ in range(n):
        question = random.choice(questions)
        response = Response.objects.create(author=user,
                                           content=faker.text(max_nb_chars=50),
                                           question=question,
                                           share_with_friends=random.choice(
                                               [True, False]),
                                           share_anonymously=random.choice([True, False]))
        if not response.share_anonymously and not response.share_with_friends:
            response.share_with_friends = True
            response.save()
    logging.info(
        f"{Response.objects.count()} Response(s) created!") if DEBUG else None

    # Seed Response Request
    for _ in range(n):
        question = random.choice(questions)
        requester = random.choice(users)
        requestee = random.choice(users.exclude(id=requester.id))
        ResponseRequest.objects.get_or_create(requester=requester, requestee=requestee, question=question)
    logging.info(
        f"{ResponseRequest.objects.count()} ResponseRequest(s) created!") if DEBUG else None

    # Seed Comment (target=Feed)
    articles = Article.objects.all()
    responses = Response.objects.all()
    for _ in range(n):
        user = random.choice(users)
        article = random.choice(articles)
        response = random.choice(responses)
        Comment.objects.create(author=user, target=article,
                               content=faker.catch_phrase(), is_private=_ % 2)
        Comment.objects.create(author=user, target=response,
                               content=faker.catch_phrase(), is_private=_ % 2)
    logging.info(
        f"{Comment.objects.count()} Comment(s) created!") if DEBUG else None

    # Seed Reply Comment (target=Comment)
    comment_model = get_comment_type()
    comments = Comment.objects.all()
    for _ in range(n):
        user = random.choice(users)
        comment = random.choice(comments)
        reply = Comment.objects.create(author=user, target=comment,
                                       content=faker.catch_phrase(), is_private=comment.is_private)
        if reply.target.is_private:
            reply.is_private = True
            reply.save()
    logging.info(f"{Comment.objects.filter(content_type=comment_model).count()} Repl(ies) created!") \
        if DEBUG else None

    # Seed Like
    for i in range(n):
        user = random.choice(users)
        article = Article.objects.get(id=i + 1)
        question = Question.objects.get(id=i + 1)
        response = Response.objects.get(id=i + 1)
        comment = Comment.objects.comments_only()[i]
        reply = Comment.objects.replies_only()[i]
        Like.objects.create(user=user, target=article)
        Like.objects.create(user=user, target=question)
        Like.objects.create(user=user, target=response)
        Like.objects.create(user=user, target=comment)
        Like.objects.create(user=user, target=reply)
    logging.info(
        f"{Like.objects.count()} Like(s) created!") if DEBUG else None

    # Seed Friend Request
    user_1 = User.objects.get(id=1)
    user_2 = User.objects.get(id=2)
    user_3 = User.objects.get(id=3)

    FriendRequest.objects.create(requester=user_3, requestee=user_1)
    FriendRequest.objects.create(requester=user_3, requestee=user_2)

    # Seed Friendship
    user_1.friends.add(user_2)


def fill_data():
    User = get_user_model()
    faker = Faker()

    # Fill Empty Seed Data
    users = User.objects.all()
    questions = Question.objects.all()
    articles = Article.objects.all()
    comments = Comment.objects.all()
    responses = Response.objects.all()
    posts = random.choice([articles, questions, responses])
    for user in users:
        Article.objects.create(author=user, content=faker.catch_phrase()) \
            if user.article_set.count() == 0 else None
        Question.objects.create(author=user, content=faker.catch_phrase(), is_admin_question=False) \
            if user.question_set.count() == 0 else None
        Response.objects.create(author=user, content=faker.catch_phrase(), question=random.choice(questions)) \
            if user.response_set.count() == 0 else None
        ResponseRequest.objects.create(requester=random.choice(users.exclude(id=user.id)),
                                       requestee=user, question=random.choice(questions)) \
            if user.received_response_request_set.count() == 0 else None
        Comment.objects.create(author=user, content=faker.catch_phrase(), target=random.choice(articles)) \
            if Comment.objects.comments_only().filter(author=user).count() == 0 else None
        Comment.objects.create(author=user, content=faker.catch_phrase(), target=random.choice(comments)) \
            if Comment.objects.replies_only().filter(author=user).count() == 0 else None
        Like.objects.create(user=user, target=random.choice(posts)) \
            if Like.objects.feed_likes_only().filter(user=user).count() == 0 else None
        Like.objects.create(user=user, target=random.choice(comments)) \
            if Like.objects.comment_likes_only().filter(user=user).count() == 0 else None
