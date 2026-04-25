from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

from account.models import Connection
from check_in.models import CheckIn
from note.models import Note
from qna.models import Question, Response

User = get_user_model()


class FriendsMarkAllCheckInsAsReadTests(APITestCase):
    URL = '/api/user/friends/mark-all-checkins-as-read/'

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='ci_viewer', email='ci_viewer@test.com', password='password',
        )
        self.friend = User.objects.create_user(
            username='ci_friend', email='ci_friend@test.com', password='password',
        )
        self.stranger = User.objects.create_user(
            username='ci_stranger', email='ci_stranger@test.com', password='password',
        )
        Connection.objects.create(
            user1=self.viewer, user2=self.friend,
            user1_choice='friend', user2_choice='friend',
        )
        self.client.force_authenticate(user=self.viewer)

    def test_marks_friend_check_in_as_read(self):
        ci = CheckIn.objects.create(user=self.friend, is_active=True, visibility=['friends'])
        self.assertNotIn(self.viewer, ci.readers.all())

        response = self.client.patch(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        ci.refresh_from_db()
        self.assertIn(self.viewer, ci.readers.all())

    def test_skips_stranger_check_in(self):
        ci = CheckIn.objects.create(user=self.stranger, is_active=True, visibility=['public'])

        response = self.client.patch(self.URL)

        self.assertEqual(response.data['count'], 0)
        ci.refresh_from_db()
        self.assertNotIn(self.viewer, ci.readers.all())

    def test_skips_close_friends_when_viewer_not_close_friend(self):
        ci = CheckIn.objects.create(
            user=self.friend, is_active=True, visibility=['close_friends'],
        )

        response = self.client.patch(self.URL)

        self.assertEqual(response.data['count'], 0)
        ci.refresh_from_db()
        self.assertNotIn(self.viewer, ci.readers.all())

    def test_skips_inactive_check_in(self):
        ci = CheckIn.objects.create(user=self.friend, is_active=False, visibility=['friends'])

        response = self.client.patch(self.URL)

        self.assertEqual(response.data['count'], 0)
        ci.refresh_from_db()
        self.assertNotIn(self.viewer, ci.readers.all())

    def test_idempotent_when_already_read(self):
        ci = CheckIn.objects.create(user=self.friend, is_active=True, visibility=['friends'])
        ci.readers.add(self.viewer)

        response = self.client.patch(self.URL)

        self.assertEqual(response.data['count'], 0)


class FriendsMarkAllPostsAsReadTests(APITestCase):
    URL = '/api/user/friends/mark-all-posts-as-read/'

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='posts_viewer', email='posts_viewer@test.com', password='password',
        )
        self.friend = User.objects.create_user(
            username='posts_friend', email='posts_friend@test.com', password='password',
        )
        self.stranger = User.objects.create_user(
            username='posts_stranger', email='posts_stranger@test.com', password='password',
        )
        Connection.objects.create(
            user1=self.viewer, user2=self.friend,
            user1_choice='friend', user2_choice='friend',
        )
        self.client.force_authenticate(user=self.viewer)
        self.question = Question.objects.create(
            author=self.friend, content='How are you?', is_admin_question=False,
        )

    def test_marks_friend_note_and_response_as_read(self):
        note = Note.objects.create(
            author=self.friend, content='hello', visibility=['friends'],
        )
        response_obj = Response.objects.create(
            author=self.friend, question=self.question, content='good',
            visibility=['friends'],
        )

        api_response = self.client.patch(self.URL)

        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['note_count'], 1)
        self.assertEqual(api_response.data['response_count'], 1)
        note.refresh_from_db()
        response_obj.refresh_from_db()
        self.assertIn(self.viewer, note.readers.all())
        self.assertIn(self.viewer, response_obj.readers.all())

    def test_skips_stranger_note(self):
        note = Note.objects.create(
            author=self.stranger, content='from stranger', visibility=['public'],
        )

        api_response = self.client.patch(self.URL)

        self.assertEqual(api_response.data['note_count'], 0)
        note.refresh_from_db()
        self.assertNotIn(self.viewer, note.readers.all())

    def test_skips_close_friends_note_when_viewer_not_close_friend(self):
        note = Note.objects.create(
            author=self.friend, content='secret', visibility=['close_friends'],
        )

        api_response = self.client.patch(self.URL)

        self.assertEqual(api_response.data['note_count'], 0)
        note.refresh_from_db()
        self.assertNotIn(self.viewer, note.readers.all())

    def test_no_friends_returns_zero(self):
        loner = User.objects.create_user(
            username='loner', email='loner@test.com', password='password',
        )
        self.client.force_authenticate(user=loner)

        api_response = self.client.patch(self.URL)

        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertEqual(api_response.data['note_count'], 0)
        self.assertEqual(api_response.data['response_count'], 0)
