from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Connection
from qna.models import Question, Response

User = get_user_model()


class QuestionResponsesTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@example.com', password='password'
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='password'
        )
        self.public_author = User.objects.create_user(
            username='public_author', email='public@example.com', password='password'
        )
        self.friend_author = User.objects.create_user(
            username='friend_author', email='friend@example.com', password='password'
        )
        self.stranger_author = User.objects.create_user(
            username='stranger_author', email='stranger@example.com', password='password'
        )

        Connection.objects.create(
            user1=self.viewer,
            user2=self.friend_author,
            user1_choice='friend',
            user2_choice='friend',
        )

        self.question = Question.objects.create(
            author=self.admin,
            content='What detail from today do you want to remember?',
            selected_dates=[date(2026, 5, 2)],
        )
        self.other_question = Question.objects.create(
            author=self.admin,
            content='Another question?',
        )

        self.own_response = Response.objects.create(
            author=self.viewer,
            question=self.question,
            content='Own response',
            visibility=['close_friends'],
        )
        self.public_response = Response.objects.create(
            author=self.public_author,
            question=self.question,
            content='Public response',
            visibility=['public'],
        )
        self.friend_response = Response.objects.create(
            author=self.friend_author,
            question=self.question,
            content='Friend response',
            visibility=['friends'],
        )
        self.hidden_response = Response.objects.create(
            author=self.stranger_author,
            question=self.question,
            content='Hidden friends-only response',
            visibility=['friends'],
        )
        Response.objects.create(
            author=self.public_author,
            question=self.other_question,
            content='Other question response',
            visibility=['public'],
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def test_returns_visible_responses_for_question(self):
        response = self.client.get(f'/api/qna/questions/{self.question.id}/responses/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['id'], self.question.id)
        self.assertEqual(response.data['content'], self.question.content)
        self.assertEqual(response.data['count'], 3)
        response_ids = [item['id'] for item in response.data['results']]
        self.assertIn(self.own_response.id, response_ids)
        self.assertIn(self.public_response.id, response_ids)
        self.assertIn(self.friend_response.id, response_ids)
        self.assertNotIn(self.hidden_response.id, response_ids)

    def test_unknown_question_returns_404(self):
        response = self.client.get('/api/qna/questions/999999/responses/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_request_returns_401(self):
        anon = APIClient()

        response = anon.get(f'/api/qna/questions/{self.question.id}/responses/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
