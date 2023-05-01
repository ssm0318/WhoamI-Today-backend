import csv

from django.utils import timezone
from django.contrib.auth import get_user_model

from feed.models import Question
from notification.models import Notification
from adoorback.utils.content_types import get_response_request_type


def select_daily_questions():
    questions = Question.objects.filter(
        selected_date__isnull=True).order_by('?')[:30]
    # if we run out of questions to select from
    if questions.count() < 30:
        Question.objects.update(selected_date=None)
    questions |= Question.objects.filter(
        selected_date__isnull=True).order_by('?')[:(30 - questions.count())]
    for question in questions:
        question.selected_date = timezone.now()
        question.save()


def create_question_csv():
    csvfile = open('./feed/algorithms/question_contents.csv', 'w')
    writer = csv.writer(csvfile)
    fields = ['id', 'author_id', 'content']

    for question_obj in Question.objects.all():
        row = "QUESTION,"
        for field in fields:
            row += str(getattr(question_obj, field)) + ","
        writer.writerow([c.strip() for c in row.strip(',').split(',')])

    for question in Question.objects.prefetch_related('response_set'):
        for response_obj in question.response_set.all():
            row = "RESPONSE," + str(question.id) + "," + \
                  str(question.author.id) + "," + response_obj.content
            writer.writerow([c.strip() for c in row.strip(',').split(',')])


def create_user_csv():
    User = get_user_model()

    csvfile = open('./feed/algorithms/user_contents.csv', 'w')
    writer = csv.writer(csvfile)

    for question in Question.objects.prefetch_related('response_set'):
        for response_obj in question.response_set.all():
            row = "ANSWERED," + str(question.id) + "," + str(response_obj.author.id)
            writer.writerow([c.strip() for c in row.strip(',').split(',')])

    for user in User.objects.all():
        if user.question_history is not None:
            for selected_id in user.question_history.split(','):
                row = "SELECTED," + selected_id + "," + str(user.id)
                writer.writerow([c.strip() for c in row.strip(',').split(',')])

    for question in Question.objects.all():
        row = "CREATED," + str(question.id) + "," + str(question.author.id)
        writer.writerow([c.strip() for c in row.strip(',').split(',')])

    for question in Question.objects.prefetch_related('question_likes'):
        for like_obj in question.question_likes.all():
            row = "LIKED," + str(question.id) + "," + str(like_obj.user.id)
            writer.writerow([c.strip() for c in row.strip(',').split(',')])

    for notification in Notification.objects.prefetch_related('origin').filter(
            target_type=get_response_request_type()):
        row = "REQUESTED," + str(notification.origin_id) + "," + str(notification.actor_id)
        writer.writerow([c.strip() for c in row.strip(',').split(',')])
