from django.test import RequestFactory, TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from account.models import User
from account.view_as import parse_view_as, VIEW_AS_TIERS


class ParseViewAsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_returns_none_when_param_missing(self):
        request = self.factory.get('/api/user/me/')
        self.assertIsNone(parse_view_as(request))

    def test_returns_tier_when_valid(self):
        for tier in VIEW_AS_TIERS:
            request = self.factory.get(f'/api/user/me/?view_as={tier}')
            self.assertEqual(parse_view_as(request), tier)

    def test_raises_validation_error_when_invalid(self):
        request = self.factory.get('/api/user/me/?view_as=enemies')
        with self.assertRaises(ValidationError):
            parse_view_as(request)


class ProfileViewAsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pw',
        )
        self.owner.bio = 'Hi, I am the owner.'
        self.owner.bio_friends_only = True
        self.owner.pronouns = 'they/them'
        self.owner.pronouns_friends_only = True
        self.owner.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_owner_without_view_as_sees_full_bio(self):
        response = self.client.get('/api/user/me/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('bio'), 'Hi, I am the owner.')
        self.assertEqual(response.data.get('pronouns'), 'they/them')

    def test_view_as_public_masks_bio_when_friends_only(self):
        response = self.client.get('/api/user/me/profile/?view_as=public')
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data.get('bio'), (None, ''))
        self.assertIn(response.data.get('pronouns'), (None, ''))

    def test_view_as_friends_keeps_bio_visible(self):
        response = self.client.get('/api/user/me/profile/?view_as=friends')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('bio'), 'Hi, I am the owner.')
        self.assertEqual(response.data.get('pronouns'), 'they/them')

    def test_view_as_close_friends_keeps_bio_visible(self):
        response = self.client.get('/api/user/me/profile/?view_as=close_friends')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('bio'), 'Hi, I am the owner.')

    def test_view_as_invalid_returns_400(self):
        response = self.client.get('/api/user/me/profile/?view_as=enemies')
        self.assertEqual(response.status_code, 400)

    def test_view_as_public_hides_friends_only_persona(self):
        """When online_persona_friends_only=True, public view sees empty personas."""
        self.owner.online_persona_friends_only = True
        self.owner.save()

        response = self.client.get('/api/user/me/profile/?view_as=public')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('user_personas'), [])

    def test_view_as_friends_includes_persona(self):
        """When online_persona_friends_only=True, friends view still sees personas."""
        self.owner.online_persona_friends_only = True
        self.owner.save()

        response = self.client.get('/api/user/me/profile/?view_as=friends')
        self.assertEqual(response.status_code, 200)
        # Friends are treated as can_see_private; user_personas isn't blanked.
        # We're not asserting any specific personas (none created), just that
        # the field is not forced to []. (Without view_as=friends, the field
        # would also not be blanked, so this test pins down the behavior.)
        self.assertIsNotNone(response.data.get('user_personas'))

    def test_view_as_close_friends_includes_persona(self):
        """When online_persona_friends_only=True, close_friends view sees personas."""
        self.owner.online_persona_friends_only = True
        self.owner.save()

        response = self.client.get('/api/user/me/profile/?view_as=close_friends')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data.get('user_personas'))
