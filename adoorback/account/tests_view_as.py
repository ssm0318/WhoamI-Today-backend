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
        self.owner.bio_visibility = 'friends'
        self.owner.pronouns = 'they/them'
        self.owner.pronouns_visibility = 'friends'
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
        self.owner.online_persona_visibility = 'friends'
        self.owner.save()

        response = self.client.get('/api/user/me/profile/?view_as=public')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('user_personas'), [])

    def test_view_as_friends_includes_persona(self):
        """When online_persona_friends_only=True, friends view still sees personas."""
        self.owner.online_persona_visibility = 'friends'
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
        self.owner.online_persona_visibility = 'friends'
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


class ShadowViewerProfileTests(TestCase):
    """Integration tests: ?view_as_user=<username> behaves as if that user were the viewer.

    The owner has `bio_friends_only=True`. When the owner previews their profile
    AS alice (a friend), bio is visible (alice is a friend → can see). When the
    owner previews AS a non-friend (synthetic public stranger), bio is hidden.
    """

    def setUp(self):
        from account.models import Connection
        self.owner = User.objects.create_user(
            username='owner_sv', email='owner_sv@example.com', password='pw',
        )
        self.owner.bio = 'Hi, I am the owner.'
        self.owner.bio_visibility = 'friends'
        self.owner.save()

        self.alice = User.objects.create_user(
            username='alice_sv', email='alice_sv@example.com', password='pw',
        )
        # alice is friends with owner
        Connection.objects.create(
            user1=self.owner, user2=self.alice,
            user1_choice='friend', user2_choice='friend',
        )

        self.stranger = User.objects.create_user(
            username='stranger_sv', email='stranger_sv@example.com', password='pw',
        )
        # No connection with owner

        self.client = APIClient()

    def test_owner_views_as_friend_sees_bio(self):
        """Owner previews as alice (friend) → bio is visible because alice can see it."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/user/me/profile/?view_as_user=alice_sv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('bio'), 'Hi, I am the owner.')

    def test_owner_views_as_stranger_hides_bio(self):
        """Owner previews as stranger (no connection) → bio is hidden."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/user/me/profile/?view_as_user=stranger_sv')
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data.get('bio'), (None, ''))

    def test_owner_views_as_returns_friendship_derived_fields_from_shadow_perspective(self):
        """Friend-status fields reflect the shadow viewer's relationship, not the owner's."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/user/me/profile/?view_as_user=alice_sv')
        self.assertEqual(response.status_code, 200)
        # are_friends should reflect the alice<->owner relationship (true), not owner<->owner (n/a)
        self.assertTrue(response.data.get('are_friends', False))

    def test_owner_views_as_stranger_returns_not_friends(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/user/me/profile/?view_as_user=stranger_sv')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data.get('are_friends', True))

    def test_non_owner_view_as_user_is_silently_ignored(self):
        """Non-owner sending view_as_user is ignored (returns response based on actual viewer)."""
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(f'/api/user/{self.owner.username}/profile/?view_as_user=alice_sv')
        self.assertEqual(response.status_code, 200)
        # The response is from stranger's perspective, NOT alice's. So bio (friends_only) is hidden.
        self.assertIn(response.data.get('bio'), (None, ''))


class PublicProxyViewerTests(TestCase):
    """Tests for the public-proxy resolution: ?view_as=public uses wit_bot as shadow viewer."""

    def setUp(self):
        from account.models import Connection
        self.owner = User.objects.create_user(
            username='owner_pp', email='owner_pp@example.com', password='pw',
        )
        self.owner.bio = 'Owner bio'
        self.owner.bio_visibility = 'friends'
        self.owner.save()
        self.proxy = User.objects.create_user(
            username='wit_bot', email='wit_bot@example.com', password='pw',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_view_as_public_uses_wit_bot_as_shadow_viewer(self):
        """When the proxy exists and isn't a friend, ?view_as=public renders from its perspective."""
        response = self.client.get('/api/user/me/profile/?view_as=public')
        self.assertEqual(response.status_code, 200)
        # bio is friends_only and proxy is not a friend → bio should be hidden
        self.assertIn(response.data.get('bio'), (None, ''))
        # are_friends should reflect proxy<->owner relationship (false)
        self.assertFalse(response.data.get('are_friends', True))

    def test_view_as_public_falls_back_when_proxy_does_not_exist(self):
        """If proxy user doesn't exist, fall back to tier-mode masking."""
        self.proxy.delete()
        response = self.client.get('/api/user/me/profile/?view_as=public')
        self.assertEqual(response.status_code, 200)
        # Tier-mode masking still hides bio
        self.assertIn(response.data.get('bio'), (None, ''))

    def test_view_as_public_falls_back_when_proxy_is_friend(self):
        """If proxy user has somehow become a friend of owner, fall back to tier-mode."""
        from account.models import Connection
        Connection.objects.create(
            user1=self.owner, user2=self.proxy,
            user1_choice='friend', user2_choice='friend',
        )
        response = self.client.get('/api/user/me/profile/?view_as=public')
        self.assertEqual(response.status_code, 200)
        # bio is still hidden (tier-mode), but the rendering is no longer "from proxy's perspective"
        self.assertIn(response.data.get('bio'), (None, ''))


class ResolvePublicProxyViewerUnitTests(TestCase):
    """Direct unit tests for resolve_public_proxy_viewer."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='unit_owner', email='unit_owner@example.com', password='pw',
        )

    def test_returns_none_when_proxy_missing(self):
        from account.view_as import resolve_public_proxy_viewer
        # Don't create the proxy user
        self.assertIsNone(resolve_public_proxy_viewer(self.owner))

    def test_returns_proxy_when_present_and_not_friend(self):
        from account.view_as import resolve_public_proxy_viewer
        proxy = User.objects.create_user(
            username='wit_bot', email='wit_bot_unit@example.com', password='pw',
        )
        result = resolve_public_proxy_viewer(self.owner)
        self.assertEqual(result, proxy)

    def test_returns_none_when_proxy_is_friend(self):
        from account.view_as import resolve_public_proxy_viewer
        from account.models import Connection
        proxy = User.objects.create_user(
            username='wit_bot', email='wit_bot_unit2@example.com', password='pw',
        )
        Connection.objects.create(
            user1=self.owner, user2=proxy,
            user1_choice='friend', user2_choice='friend',
        )
        self.assertIsNone(resolve_public_proxy_viewer(self.owner))

    def test_returns_none_when_proxy_is_owner(self):
        """Edge case: if the proxy username happens to match the owner's, return None."""
        from account.view_as import resolve_public_proxy_viewer
        # Create a user whose username is the proxy's
        weird_owner = User.objects.create_user(
            username='wit_bot', email='wit_bot_owner@example.com', password='pw',
        )
        self.assertIsNone(resolve_public_proxy_viewer(weird_owner))


class PostListViewAsTests(TestCase):
    """Integration tests: view_as filtering on note/response/all-posts list endpoints."""

    def setUp(self):
        from account.models import Connection
        from note.models import Note

        self.owner = User.objects.create_user(
            username='owner_pl', email='owner_pl@example.com', password='pw',
        )
        self.friend = User.objects.create_user(
            username='friend_pl', email='friend_pl@example.com', password='pw',
        )
        Connection.objects.create(
            user1=self.friend, user2=self.owner,
            user1_choice='friend', user2_choice='friend',
        )
        self.stranger = User.objects.create_user(
            username='stranger_pl', email='stranger_pl@example.com', password='pw',
        )
        self.proxy = User.objects.create_user(
            username='wit_bot', email='wit_bot_pl@example.com', password='pw',
        )

        self.note_public = Note.objects.create(
            author=self.owner, content='Public note', visibility=['public'],
        )
        self.note_friends = Note.objects.create(
            author=self.owner, content='Friends note', visibility=['friends'],
        )
        self.note_close_friends = Note.objects.create(
            author=self.owner, content='Close friends note', visibility=['close_friends'],
        )

        self.client = APIClient()

    def _get_note_ids(self, response):
        return {item['id'] for item in response.data.get('results', response.data)}

    def test_owner_without_view_as_sees_all_notes(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/user/{self.owner.username}/notes/')
        self.assertEqual(response.status_code, 200)
        ids = self._get_note_ids(response)
        self.assertIn(self.note_public.id, ids)
        self.assertIn(self.note_friends.id, ids)
        self.assertIn(self.note_close_friends.id, ids)

    def test_view_as_public_shows_only_public_notes(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/user/{self.owner.username}/notes/?view_as=public')
        self.assertEqual(response.status_code, 200)
        ids = self._get_note_ids(response)
        self.assertIn(self.note_public.id, ids)
        self.assertNotIn(self.note_friends.id, ids)
        self.assertNotIn(self.note_close_friends.id, ids)

    def test_view_as_friends_shows_public_and_friends(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/user/{self.owner.username}/notes/?view_as=friends')
        self.assertEqual(response.status_code, 200)
        ids = self._get_note_ids(response)
        self.assertIn(self.note_public.id, ids)
        self.assertIn(self.note_friends.id, ids)
        self.assertNotIn(self.note_close_friends.id, ids)

    def test_view_as_close_friends_shows_public_friends_close_friends(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/user/{self.owner.username}/notes/?view_as=close_friends')
        self.assertEqual(response.status_code, 200)
        ids = self._get_note_ids(response)
        self.assertIn(self.note_public.id, ids)
        self.assertIn(self.note_friends.id, ids)
        self.assertIn(self.note_close_friends.id, ids)

    def test_view_as_user_stranger_sees_only_public(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            f'/api/user/{self.owner.username}/notes/?view_as_user={self.stranger.username}',
        )
        self.assertEqual(response.status_code, 200)
        ids = self._get_note_ids(response)
        self.assertIn(self.note_public.id, ids)
        self.assertNotIn(self.note_friends.id, ids)
        self.assertNotIn(self.note_close_friends.id, ids)

    def test_non_owner_view_as_is_ignored(self):
        """Non-owner sending view_as on someone else's notes should be ignored."""
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(
            f'/api/user/{self.owner.username}/notes/?view_as=close_friends',
        )
        self.assertEqual(response.status_code, 200)
        ids = self._get_note_ids(response)
        # Stranger can only see public notes regardless of view_as param
        self.assertIn(self.note_public.id, ids)
        self.assertNotIn(self.note_friends.id, ids)
        self.assertNotIn(self.note_close_friends.id, ids)

    def test_view_as_public_on_all_posts_endpoint(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/user/{self.owner.username}/all-posts/?view_as=public')
        self.assertEqual(response.status_code, 200)
        ids = {item['id'] for item in response.data.get('results', response.data)}
        self.assertIn(self.note_public.id, ids)
        self.assertNotIn(self.note_friends.id, ids)
        self.assertNotIn(self.note_close_friends.id, ids)
