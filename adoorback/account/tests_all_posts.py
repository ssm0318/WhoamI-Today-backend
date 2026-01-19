from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient
from rest_framework import status
from note.models import Note
from qna.models import Question, Response
from pin.models import Pin

User = get_user_model()

class CurrentUserAllPostListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_user', email='test@example.com', password='password')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create Content
        self.note = Note.objects.create(author=self.user, content='Test Note', visibility=['public'])
        self.question = Question.objects.create(content='Test Question', author=self.user, selected_date='2024-01-01')
        self.response = Response.objects.create(author=self.user, question=self.question, content='Test Response', visibility=['public'])

    def test_pin_id_in_all_posts(self):
        # 1. Verify pin_id is None initially
        url = '/api/user/me/all-posts/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        
        for item in results:
            self.assertFalse(item['pinned'])
            self.assertIsNone(item['pin_id'])

        # 2. Pin the items
        note_content_type = ContentType.objects.get_for_model(Note)
        response_content_type = ContentType.objects.get_for_model(Response)

        pin_note = Pin.objects.create(user=self.user, content_type=note_content_type, object_id=self.note.id)
        pin_response = Pin.objects.create(user=self.user, content_type=response_content_type, object_id=self.response.id)

        # 3. Verify pin_id is present and correct
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']

        note_result = next(item for item in results if item['type'] == 'Note')
        response_result = next(item for item in results if item['type'] == 'Response')

        self.assertTrue(note_result['pinned'])
        self.assertEqual(note_result['pin_id'], pin_note.id)

        self.assertTrue(response_result['pinned'])
        self.assertEqual(response_result['pin_id'], pin_response.id)

        # 4. Unpin (delete Pin objects)
        pin_note.delete()
        pin_response.delete()

        # 5. Verify pin_id is None again
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']

        for item in results:
            self.assertFalse(item['pinned'])
            self.assertIsNone(item['pin_id'])
