from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient
from rest_framework.utils import json
from test_plus.test import TestCase

from account.models import FriendRequest
from content_report.models import ContentReport
from user_report.models import UserReport
from feed.models import Article, Question, Response, ResponseRequest, Post
from comment.models import Comment
from like.models import Like
from notification.models import Notification
from adoorback.test.seed import set_seed
from adoorback.utils.content_types import get_article_type, get_question_type, get_response_type

User = get_user_model()
N = 10


class ContentReportTestCase(TestCase):
    def setUp(self):
        set_seed(N)

    def test_content_report(self):
        Article.objects.all().delete()
        Response.objects.all().delete()
        Question.objects.all().delete()
        
        user1 = self.make_user(username='user1')
        user2 = self.make_user(username='user2')
        user3 = self.make_user(username='user3')

        article = Article.objects.create(author=user2, content='test article')
        question = Question.objects.create(author=user3, content='test question')
        response1 = Response.objects.create(author=user2, content='test response1', question=question)
        response2 = Response.objects.create(author=user3, content='test response2', question=question)
        
        with self.login(username=user1.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 4)

        with self.login(username=user1.username, password='password'):
            post1 = Post.objects.get(content_type=get_question_type(), object_id=question.id)
            ContentReport.objects.create(user=user1, post=post1)
            UserReport.objects.create(user=user1, reported_user=user2)

            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 1)
            self.assertEqual(response.data['results'][0]['content'], 'test response2')

            post2 = Post.objects.get(content_type=get_response_type(), object_id=response2.id)
            ContentReport.objects.create(user=user1, post=post2)
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 0)

        with self.login(username=user2.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 4)

    
class APITestCase(TestCase):
    client_class = APIClient


class ContentReportAPITestCase(APITestCase):
    def setUp(self):
        set_seed(N)

    def test_content_report_list(self):
        Article.objects.all().delete()
        Response.objects.all().delete()
        Question.objects.all().delete()
        
        user1 = self.make_user(username='user1')
        user2 = self.make_user(username='user2')
        user3 = self.make_user(username='user3')

        article = Article.objects.create(author=user2, content='test article')
        question = Question.objects.create(author=user3, content='test question')
        response1 = Response.objects.create(author=user2, content='test response1', question=question)
        response2 = Response.objects.create(author=user3, content='test response2', question=question)

        with self.login(username=user1.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 4)

        with self.login(username=user1.username, password='password'):
            data = {"target_type": "Question", "target_id": question.id}
            response = self.post('content-report-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        with self.login(username=user1.username, password='password'):
            data = {"target_type": "Response", "target_id": response2.id}
            response = self.post('content-report-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        with self.login(username=user1.username, password='password'):
            response = self.get('anonymous-feed-post-list')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 2)        
            self.assertEqual(response.data['results'][0]['content'], 'test response1')
            self.assertEqual(response.data['results'][1]['content'], 'test article')

    def test_restrictions(self):
        user1 = self.make_user(username='user1')
        user2 = self.make_user(username='user2')
        user3 = self.make_user(username='user3')

        UserReport.objects.all().delete()
        ContentReport.objects.all().delete()

        article = Article.objects.create(author=user2, content='test article')
        question = Question.objects.create(author=user3, content='test question')
        response1 = Response.objects.create(author=user2, content='test response1', question=question)
        response2 = Response.objects.create(author=user3, content='test response2', question=question)

        with self.login(username=user1.username, password='password'):
            data = {"target_type": "Response", "target_id": response2.id}
            response = self.post('content-report-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        with self.login(username=user1.username, password='password'):
            response = self.get(self.reverse('response-detail', pk=response2.id))
            self.assertEqual(response.status_code, 403) # user can't access the content they blocked

        with self.login(username=user3.username, password='password'):
            response = self.get(self.reverse('response-detail', pk=response2.id))
            self.assertEqual(response.status_code, 200)

        with self.login(username=user1.username, password='password'):
            data = {"target_type": "Question", "target_id": question.id}
            response = self.post('content-report-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        with self.login(username=user1.username, password='password'):
            response = self.get(self.reverse('question-detail', pk=question.id))
            self.assertEqual(response.status_code, 403)

        with self.login(username=user2.username, password='password'):
            response = self.get(self.reverse('question-detail', pk=question.id))
            self.assertEqual(response.status_code, 200)

        with self.login(username=user1.username, password='password'):
            data = {"target_type": "Article", "target_id": article.id}
            response = self.post('content-report-list', data=data, extra={'format': 'json'})
            self.assertEqual(response.status_code, 201)

        with self.login(username=user1.username, password='password'):
            response = self.get(self.reverse('article-detail', pk=article.id))
            self.assertEqual(response.status_code, 403)

        with self.login(username=user2.username, password='password'):
            response = self.get(self.reverse('article-detail', pk=article.id))
            self.assertEqual(response.status_code, 200)
