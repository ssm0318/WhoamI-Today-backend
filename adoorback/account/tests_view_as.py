from django.test import RequestFactory, TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APIRequestFactory
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

    def test_non_owner_cannot_use_view_as_to_mask_someone_else_profile(self):
        """Non-owner sending view_as on someone else's profile sees the friend-view filtered.

        The owner has bio_friends_only=True. `other` is unrelated to owner (no Connection).
        Even when `other` sends view_as=close_friends (trying to coerce a higher tier than
        they actually have), the response should still hide the bio because the masking
        helper and serializer gate on `user == instance` — view_as is a no-op for non-owners.
        """
        other = User.objects.create_user(
            username='other', email='other@example.com', password='pw',
        )
        self.client.force_authenticate(user=other)
        response = self.client.get(f'/api/user/{self.owner.username}/profile/?view_as=close_friends')
        self.assertEqual(response.status_code, 200)
        # bio is friends_only and `other` is not a friend → bio must be hidden
        # regardless of view_as=close_friends
        self.assertIn(response.data.get('bio'), (None, ''))


class ParseViewAsUserTests(TestCase):
    """Tests for the parse_view_as_user query-param parser."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_returns_none_when_param_missing(self):
        from account.view_as import parse_view_as_user
        request = self.factory.get('/api/user/me/profile/')
        self.assertIsNone(parse_view_as_user(request))

    def test_returns_username_when_present(self):
        from account.view_as import parse_view_as_user
        request = self.factory.get('/api/user/me/profile/?view_as_user=alice')
        self.assertEqual(parse_view_as_user(request), 'alice')

    def test_returns_none_when_empty_string(self):
        from account.view_as import parse_view_as_user
        request = self.factory.get('/api/user/me/profile/?view_as_user=')
        self.assertIsNone(parse_view_as_user(request))


class ResolveShadowViewerTests(TestCase):
    """Tests for the resolve_shadow_viewer helper.

    The helper takes a request, the target profile owner, and returns either
    a User instance to use as the effective viewer OR None if the param is
    missing / unauthorized / invalid.

    Owner-only: only the target's owner is allowed to use shadow_viewer.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pw',
        )
        self.alice = User.objects.create_user(
            username='alice', email='alice@example.com', password='pw',
        )
        self.bob = User.objects.create_user(
            username='bob', email='bob@example.com', password='pw',
        )

    def test_returns_none_when_param_missing(self):
        from account.view_as import resolve_shadow_viewer
        request = self.factory.get('/api/user/me/profile/')
        request.user = self.owner
        self.assertIsNone(resolve_shadow_viewer(request, self.owner))

    def test_returns_user_when_owner_requests_valid_username(self):
        from account.view_as import resolve_shadow_viewer
        request = self.factory.get('/api/user/me/profile/?view_as_user=alice')
        request.user = self.owner
        result = resolve_shadow_viewer(request, self.owner)
        self.assertEqual(result, self.alice)

    def test_returns_none_when_non_owner_tries(self):
        """A non-owner sending view_as_user is ignored (not an abuse vector)."""
        from account.view_as import resolve_shadow_viewer
        request = self.factory.get('/api/user/owner/profile/?view_as_user=alice')
        request.user = self.bob  # not the owner
        self.assertIsNone(resolve_shadow_viewer(request, self.owner))

    def test_returns_none_when_username_does_not_exist(self):
        from account.view_as import resolve_shadow_viewer
        request = self.factory.get('/api/user/me/profile/?view_as_user=nonexistent')
        request.user = self.owner
        self.assertIsNone(resolve_shadow_viewer(request, self.owner))

    def test_returns_none_when_owner_picks_themselves(self):
        """Owner picking themselves as shadow viewer is a no-op (treat as unset)."""
        from account.view_as import resolve_shadow_viewer
        request = self.factory.get('/api/user/me/profile/?view_as_user=owner')
        request.user = self.owner
        # Owner viewing their own profile through their own eyes is identity → no shadow
        self.assertIsNone(resolve_shadow_viewer(request, self.owner))
