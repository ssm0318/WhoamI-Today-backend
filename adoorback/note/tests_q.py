from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from account.models import Connection
from note.models import Note

User = get_user_model()


class QNoteEndpointTests(APITestCase):
    """Test Version Q note endpoints return correct format."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@test.com', password='password',
            current_ver='version_q', user_group='group_q_first'
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='password',
            current_ver='version_q', user_group='group_q_first'
        )
        Connection.objects.create(
            user1=self.user, user2=self.friend,
            user1_choice='friend', user2_choice='friend'
        )
        self.client.force_authenticate(user=self.user)

    def test_q_note_create_no_share_type(self):
        """Q note creation should work without share_type."""
        url = reverse('q-note-create')
        data = {'content': 'Hello from Q', 'visibility': '["friends"]'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('share_type', response.data)
        self.assertNotIn('current_user_reaction_id_list', response.data)

    def test_q_note_create_has_like_fields(self):
        """Q note should have like_count and like_user_sample instead of reactions."""
        url = reverse('q-note-create')
        data = {'content': 'Q note test', 'visibility': '["friends"]'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('like_count', response.data)
        self.assertIn('like_user_sample', response.data)

    def test_q_note_detail(self):
        """Q note detail should not include share_type or reactions."""
        note = Note.objects.create(
            author=self.friend, content='Friend note',
            visibility=['friends'], share_type='regular'
        )
        url = reverse('q-note-detail', kwargs={'pk': note.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('share_type', response.data)
        self.assertNotIn('current_user_reaction_id_list', response.data)
        self.assertIn('like_count', response.data)

    def test_w_note_create_has_share_type(self):
        """W note creation should include share_type and reactions."""
        url = reverse('note-list')  # W endpoint
        data = {'content': 'Hello from W', 'visibility': '["friends"]', 'share_type': 'tmi_of_the_day'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('share_type', response.data)
        self.assertIn('current_user_reaction_id_list', response.data)

    def test_q_note_detail_permission_denied_for_stranger(self):
        """Q note detail should deny access to non-audience users."""
        stranger = User.objects.create_user(
            username='stranger', email='stranger@test.com', password='password'
        )
        note = Note.objects.create(
            author=self.friend, content='Private note',
            visibility=['close_friends']
        )
        self.client.force_authenticate(user=stranger)
        url = reverse('q-note-detail', kwargs={'pk': note.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
