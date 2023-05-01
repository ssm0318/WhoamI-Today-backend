import random
import logging
import sys

import pandas as pd
from django.contrib.auth import get_user_model
from faker import Faker

from adoorback.utils.content_types import get_question_type
from feed.models import Question, ResponseRequest, Response
from like.models import Like

DEBUG = True


def set_question_seed():
    df = pd.read_csv('adoorback/assets/questions.csv')

    User = get_user_model()
    admin = User.objects.get(username='adoor')

    for i in df.index:
        content = df.at[i, 'content']
        Question.objects.create(author=admin, is_admin_question=True, content=content)


def set_mock_seed():
    if DEBUG:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    User = get_user_model()
    faker = Faker(locale='ko_KR')

    # Seed Superuser
    if User.objects.count() == 0:
        User.objects.create_superuser(
            username='adoor', email='adoor.team@gmail.com', password='adoor2020:)',
            question_history=",".join(map(str, faker.random_elements(
                elements=range(1, 1000),
                length=random.randint(3, 10),
                unique=True))))
        logging.info("Superuser created!") if DEBUG else None

        # Seed User
        for i in range(1000):
            User.objects.create_user(username=str(i) + faker.user_name(),
                                     email=str(i) + faker.email(),
                                     password=faker.password(),
                                     question_history=",".join(map(str,
                                                                   faker.random_elements(
                                                                       elements=range(1, 1000),
                                                                       length=random.randint(3, 10),
                                                                       unique=True))))
        logging.info(
            f"{User.objects.count()} Users created!") if DEBUG else None

    users = User.objects.all()

    set_question_seed()
    logging.info(
        f"{Question.objects.count()} Questions created!") if DEBUG else None

    # Seed Friendship
    for user in users:
        user.friends.add(*faker.random_elements(elements=range(1, 100), length=random.randint(0, 50), unique=True))
    logging.info("Friendship Relations created!") if DEBUG else None

    # Seed Response Request
    questions = Question.objects.all()
    for i in range(2000):
        question = random.choice(questions)
        requester = random.choice(users)
        requestee = random.choice(users.exclude(id=requester.id))
        ResponseRequest.objects.get_or_create(requester=requester, requestee=requestee, question=question)
    logging.info(
        f"{ResponseRequest.objects.count()} ResponseRequests created!") if DEBUG else None

    # Seed Response
    for _ in range(3000):
        user = random.choice(users)
        question = random.choice(questions)
        response = Response.objects.create(author=user,
                                           content=faker.catch_phrase(),
                                           question=question,
                                           share_with_friends=True,
                                           share_anonymously=False)
    logging.info(
        f"{Response.objects.count()} Responses created!") if DEBUG else None

    # Seed Feed Like
    for i in range(5000):
        user = random.choice(users)
        question = Question.objects.get(id=i % 1000 + 1)
        Like.objects.get_or_create(user=user, content_type=get_question_type(), object_id=question.id)
    logging.info(f"{Like.objects.count()} Likes created!") if DEBUG else None
