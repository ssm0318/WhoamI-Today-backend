from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient
from rest_framework.utils import json
from test_plus.test import TestCase

from account.models import FriendRequest
from user_report.models import UserReport
from feed.models import Article, Question, Response, ResponseRequest
from comment.models import Comment
from like.models import Like
from notification.models import Notification
from adoorback.test.seed import set_seed

User = get_user_model()
N = 10


class UserReportTestCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_user_report(self):
        Article.objects.all().delete()
        Response.objects.all().delete()
        Question.objects.all().delete()
        
        user1 = self.make_user(username='user1')
        user2 = self.make_user(username='user2')
        user3 = self.make_user(username='user3')

        article1 = Article.objects.create(author_id=user1.id, content='test content1')
        article2 = Article.objects.create(author_id=user2.id, content='test content2')
        article3 = Article.objects.create(author_id=user3.id, content='test content3')

        comment1 = Comment.objects.create(target=article2, author_id=user1.id, content='test comment1', is_anonymous=True, is_private=False)
        comment2 = Comment.objects.create(target=article2, author_id=user2.id, content='test comment2', is_anonymous=True, is_private=False)
        comment3 = Comment.objects.create(target=article2, author_id=user3.id, content='test comment3', is_anonymous=True, is_private=False)

        user3.friends.add(user1)

        with self.login(username=user3.username, password='password'):
            response = self.get('current-user-friends')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 1)  # before blocking

        with self.login(username=user1.username, password='password'):
            response = self.get('current-user-friends')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 1)  # before blocking

        # user3 reports user1
        with self.login(username=user3.username, password='password'):
            user_report = UserReport.objects.create(user_id=user3.id, reported_user_id=user1.id)

        with self.login(username=user3.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 2) # article of user1 is blocked
            self.assertEqual(len(response.data['results'][1]['comments']), 2) # comment of user1 is blocked

        with self.login(username=user2.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 3)
            self.assertEqual(len(response.data['results'][1]['comments']), 3)

        with self.login(username=user1.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 2) # article of user3 does not show
            self.assertEqual(len(response.data['results'][0]['comments']), 2) # comment of user3 is blocked

        with self.login(username=user3.username, password='password'):
            response = self.get('current-user-friends')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)  # blocked user don't show up in friend list

    def test_user_report_noti(self):
        user1 = self.make_user(username='user1')
        user2 = self.make_user(username='user2')
        user3 = self.make_user(username='user3')

        # test notification
        question = Question.objects.create(author=user1, content='test question', is_admin_question=True)
        article = Article.objects.create(author=user3, content='test article')

        with self.login(username=user3.username, password='password'):
            UserReport.objects.create(user_id=user3.id, reported_user_id=user1.id)
            prev_noti_count = Notification.objects.count()
            ResponseRequest.objects.create(requester=user1, requestee=user3, question=question)
            ResponseRequest.objects.create(requester=user3, requestee=user1, question=question)
            Response.objects.create(question=question, author=user1)
            Comment.objects.create(target=article, author=user1)
            Like.objects.create(target=article, user=user1)
            curr_noti_count = Notification.objects.count()
            self.assertEqual(curr_noti_count, prev_noti_count)  # notis from/for blocked users should NOT be created

    def test_user_report_deletion_undeletion(self):
        user4 = self.make_user(username='user4')
        user5 = self.make_user(username='user5')
        user6 = self.make_user(username='user6')

        # initialization
        ResponseRequest.objects.all().delete()
        FriendRequest.objects.all().delete()
        UserReport.objects.all().delete()

        question = Question.objects.create(author_id=1, content='test question', is_admin_question=True)

        ResponseRequest.objects.create(requester=user4, requestee=user5, question=question)
        ResponseRequest.objects.create(requester=user5, requestee=user4, question=question)
        FriendRequest.objects.create(requester=user4, requestee=user5)

        self.assertEqual(ResponseRequest.objects.count(), 2)
        self.assertEqual(FriendRequest.objects.count(), 1)

        UserReport.objects.create(user_id=4, reported_user_id=5)

        self.assertEqual(ResponseRequest.objects.count(), 0)
        self.assertEqual(FriendRequest.objects.count(), 0)

        user = User.objects.get(id=user4.id)
        user.delete()

        self.assertEqual(UserReport.objects.count(), 0)

        # undelete
        user.undelete()
        self.assertEqual(UserReport.objects.count(), 1)


class APITestCase(TestCase):
    client_class = APIClient


class UserReportAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

    def test_user_report_list(self):
        user1 = self.make_user(username='user1')
        user2 = self.make_user(username='user2')

        with self.login(username=user1.username, password='password'):
            data = {"reported_user_id": user2.id}
            response = self.post('user-report-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

    def test_restrictions(self):
        user1 = self.make_user(username='user1')
        user2 = self.make_user(username='user2')
        user3 = self.make_user(username='user3')

        with self.login(username=user3.username, password='password'):
            data = {"reported_user_id": user1.id}
            response = self.post('user-report-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        with self.login(username=user1.username, password='password'):
            response = self.get('current-user-friends')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)  # blocked user don't show up in friend list

        with self.login(username=user3.username, password='password'):
            response = self.get(self.reverse('user-detail', username=user1.username))
            self.assertEqual(response.status_code, 403)  # can't access blocked user's page

        with self.login(username=user2.username, password='password'):
            response = self.get(self.reverse('user-detail', username=user1.username))
            self.assertEqual(response.status_code, 200)

        with self.login(username=user1.username, password='password'):
            response = self.get(self.reverse('user-detail', username=user3.username))
            self.assertEqual(response.status_code, 403)  # can't access blocked user's page
