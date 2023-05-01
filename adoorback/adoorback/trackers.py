from django.contrib.auth import get_user_model

from trackstats.models import Domain, Metric, Period
from trackstats.trackers import CountObjectsByDateTracker, CountObjectsByDateAndObjectTracker

from account.models import FriendRequest
from feed.models import Article, Response, Question, ResponseRequest
from comment.models import Comment
from like.models import Like
from notification.models import Notification

User = get_user_model()


Domain.objects.POSTS = Domain.objects.register(
    ref='posts',
    name='Posts')
Domain.objects.USERS = Domain.objects.register(
    ref='users',
    name='Users')
Domain.objects.REACTIONS = Domain.objects.register(
    ref='reactions',
    name='Reactions')
Domain.objects.NOTIFICATIONS = Domain.objects.register(
    ref='notifications',
    name='Notifications')
Domain.objects.INTERACTIONS = Domain.objects.register(
    ref='interactions',
    name='Interactions')

Metric.objects.ARTICLES_COUNT = Metric.objects.register(
    domain=Domain.objects.POSTS,
    ref='article_count',
    name='Number of articles created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.ARTICLES_COUNT,
    date_field='created_at').track(Article.objects.all())
Metric.objects.ARTICLES_BY_USER_COUNT = Metric.objects.register(
    domain=Domain.objects.POSTS,
    ref='article_count_by_user',
    name='Number of articles created by user')
CountObjectsByDateAndObjectTracker(
    period=Period.DAY,
    metric=Metric.objects.ARTICLES_BY_USER_COUNT,
    object_model=User,
    object_field='author',
    date_field='created_at').track(Article.objects.all())

Metric.objects.QUESTIONS_COUNT = Metric.objects.register(
    domain=Domain.objects.POSTS,
    ref='question_count',
    name='Number of questions created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.QUESTIONS_COUNT,
    date_field='created_at').track(Question.objects.all())
Metric.objects.QUESTIONS_BY_USER_COUNT = Metric.objects.register(
    domain=Domain.objects.POSTS,
    ref='question_count_by_user',
    name='Number of questions created by user')
CountObjectsByDateAndObjectTracker(
    period=Period.DAY,
    metric=Metric.objects.QUESTIONS_BY_USER_COUNT,
    object_model=User,
    object_field='author',
    date_field='created_at').track(Question.objects.all())

Metric.objects.RESPONSES_COUNT = Metric.objects.register(
    domain=Domain.objects.POSTS,
    ref='response_count',
    name='Number of responses created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.RESPONSES_COUNT,
    date_field='created_at').track(Response.objects.all())
Metric.objects.RESPONSES_BY_USER_COUNT = Metric.objects.register(
    domain=Domain.objects.POSTS,
    ref='response_count_by_user',
    name='Number of responses created by user')
CountObjectsByDateAndObjectTracker(
    period=Period.DAY,
    metric=Metric.objects.RESPONSES_BY_USER_COUNT,
    object_model=User,
    object_field='author',
    date_field='created_at').track(Response.objects.all())

Metric.objects.USERS_COUNT = Metric.objects.register(
    domain=Domain.objects.USERS,
    ref='user_count',
    name='Number of users signed up')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.USERS_COUNT,
    date_field='created_at').track(User.objects.all())


Metric.objects.COMMENTS_COUNT = Metric.objects.register(
    domain=Domain.objects.REACTIONS,
    ref='comment_count',
    name='Number of comments created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.COMMENTS_COUNT,
    date_field='created_at').track(Comment.objects.all())
Metric.objects.COMMENTS_BY_USER_COUNT = Metric.objects.register(
    domain=Domain.objects.POSTS,
    ref='comment_count_by_user',
    name='Number of comments created by user')
CountObjectsByDateAndObjectTracker(
    period=Period.DAY,
    metric=Metric.objects.COMMENTS_BY_USER_COUNT,
    object_model=User,
    object_field='author',
    date_field='created_at').track(Comment.objects.all())

Metric.objects.LIKES_COUNT = Metric.objects.register(
    domain=Domain.objects.REACTIONS,
    ref='like_count',
    name='Number of likes created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.LIKES_COUNT,
    date_field='created_at').track(Like.objects.all())

Metric.objects.NOTIFICATIONS_COUNT = Metric.objects.register(
    domain=Domain.objects.NOTIFICATIONS,
    ref='notification_count',
    name='Number of notifications created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.NOTIFICATIONS_COUNT,
    date_field='created_at').track(Notification.objects.all())

Metric.objects.FRIEND_REQUESTS_COUNT = Metric.objects.register(
    domain=Domain.objects.INTERACTIONS,
    ref='friend_request_count',
    name='Number of friend requests created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.FRIEND_REQUESTS_COUNT,
    date_field='created_at').track(FriendRequest.objects.all())

Metric.objects.RESPONSE_REQUESTS_COUNT = Metric.objects.register(
    domain=Domain.objects.INTERACTIONS,
    ref='response_requests_count',
    name='Number of response requests created')
CountObjectsByDateTracker(
    period=Period.DAY,
    metric=Metric.objects.RESPONSE_REQUESTS_COUNT,
    date_field='created_at').track(ResponseRequest.objects.all())
