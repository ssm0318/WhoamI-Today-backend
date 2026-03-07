from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from note.models import Note
from account.models import Connection

User = get_user_model()

class NoteVisibilityTests(TestCase):
    def setUp(self):
        # Create users
        self.author = User.objects.create_user(username='author', email='author@example.com', password='password')
        self.friend = User.objects.create_user(username='friend', email='friend@example.com', password='password')
        self.stranger = User.objects.create_user(username='stranger', email='stranger@example.com', password='password')

        # Create relationships
        Connection.objects.create(user1=self.author, user2=self.friend) # Friends

        self.client = APIClient()

    def test_public_note_visibility(self):
        note = Note.objects.create(author=self.author, content='Public Note', visibility=['public'])
        
        # Stranger should see it
        self.assertTrue(note.is_audience(self.stranger))
        pass

    def test_verify_response_style_logic(self):
        # Public Note — everyone can see (public check happens first)
        note_public = Note.objects.create(author=self.author, content='Public Only', visibility=['public'])
        self.assertTrue(note_public.is_audience(self.friend))
        self.assertTrue(note_public.is_audience(self.stranger))

        # Friend Note — only connected users
        note_friend = Note.objects.create(author=self.author, content='Friend Only', visibility=['friends'])
        self.assertTrue(note_friend.is_audience(self.friend))
        self.assertFalse(note_friend.is_audience(self.stranger))

    def test_api_visibility(self):
        # Public Note
        Note.objects.create(author=self.author, content='Public Content', visibility=['public'])

        # Stranger requests
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(f'/api/user/{self.author.username}/notes/')
        self.assertEqual(len(response.data['results']), 1)

        # Friend also sees public note
        self.client.force_authenticate(user=self.friend)
        response = self.client.get(f'/api/user/{self.author.username}/notes/')
        self.assertEqual(len(response.data['results']), 1)
        
