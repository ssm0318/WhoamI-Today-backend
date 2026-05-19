"""Tests for CheckInPost 24h expiry + pin (highlight) feature.

Covers the visibility matrix introduced when:
  - posts auto-hide from friends after CHECK_IN_POST_EXPIRY_HOURS (24h),
  - the author can pin a post so it stays visible past expiry,
  - pinned posts use an independent `pin_visibility` (friends|close_friends)
    set/changed by the author after pinning.

The author's own posts remain visible to themselves regardless of age
(self archive). Friends are blocked from creating new likes/comments on
expired non-pinned posts because `is_audience()` returns False.

We bypass `auto_now_add=True` on `created_at` by using
`CheckInPost.objects.filter(...).update(created_at=...)` after creation.
"""
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from account.models import Connection
from check_in.models import CHECK_IN_POST_EXPIRY_HOURS, CheckInPost

User = get_user_model()


# 1x1 transparent PNG — valid image, ~70 bytes
PNG_1X1 = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xcf'
    b'\xc0\xc0\xc0\x00\x00\x00\x05\x00\x01\xa5\xf6E\xed\x00\x00\x00\x00'
    b'IEND\xaeB`\x82'
)


def make_image(name='t.png'):
    return SimpleUploadedFile(name, PNG_1X1, content_type='image/png')


def connect(author, viewer, author_choice='friend', viewer_choice='friend'):
    """Make `author` and `viewer` friends. `author_choice` is what `author` set
    for `viewer` — set to 'close_friend' to have author classify viewer as close.
    """
    Connection.objects.create(
        user1=author, user2=viewer,
        user1_choice=author_choice, user2_choice=viewer_choice,
    )


def age_post(post, hours):
    """Bypass auto_now_add to set created_at into the past."""
    new_ts = timezone.now() - timedelta(hours=hours)
    CheckInPost.objects.filter(pk=post.pk).update(created_at=new_ts)
    post.refresh_from_db()
    return post


class CheckInPostExpiryTests(TestCase):
    """Scenarios 1–5, 16 — 24h auto-hide from friends, author always sees."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@t.com', password='pw',
            current_ver='version_q',
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@t.com', password='pw',
            current_ver='version_q',
        )
        connect(self.author, self.friend)
        self.client = APIClient()

    def _create_post(self, visibility='friends'):
        return CheckInPost.objects.create(
            author=self.author, image=make_image(),
            caption='hi', visibility=visibility,
        )

    def test_fresh_post_visible_in_friend_feed(self):
        """Scenario 1: <24h post is visible in the friend's feed."""
        post = self._create_post()
        age_post(post, hours=23)

        self.client.force_authenticate(user=self.friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 1)
        self.assertEqual(resp.data['results'][0]['id'], post.id)

    def test_expired_unpinned_hidden_from_friend(self):
        """Scenario 2: >24h post (no pin) disappears from friend's feed."""
        post = self._create_post()
        age_post(post, hours=25)

        self.client.force_authenticate(user=self.friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['results'], [])

    def test_expired_unpinned_still_visible_to_author(self):
        """Scenario 3: author always sees own expired posts (self archive)."""
        post = self._create_post()
        age_post(post, hours=25)

        self.client.force_authenticate(user=self.author)
        resp = self.client.get(
            reverse('check-in-posts-by-user', kwargs={'pk': self.author.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data) if isinstance(resp.data, dict) else resp.data
        ids = [r['id'] for r in results]
        self.assertIn(post.id, ids)

    def test_expired_unpinned_detail_404_for_friend(self):
        """Scenario 4: friend can't open expired post via direct URL."""
        post = self._create_post()
        age_post(post, hours=25)

        self.client.force_authenticate(user=self.friend)
        resp = self.client.get(
            reverse('check-in-post-detail', kwargs={'pk': post.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_expired_unpinned_detail_200_for_author(self):
        """Scenario 5: author can still open expired own post via detail URL."""
        post = self._create_post()
        age_post(post, hours=25)

        self.client.force_authenticate(user=self.author)
        resp = self.client.get(
            reverse('check-in-post-detail', kwargs={'pk': post.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_expired_post_blocks_friend_is_audience(self):
        """Scenario 16: is_audience() returns False so likes/comments endpoints
        sharing this check are also blocked."""
        post = self._create_post()
        age_post(post, hours=25)
        self.assertFalse(post.is_audience(self.friend))
        self.assertTrue(post.is_audience(self.author))


class CheckInPostStoriesVisibilityTests(TestCase):
    """Daily Snapshot rails are split by surface:
    friends/close-friends snapshots stay on Friends, public snapshots go to Discover.
    """

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@t.com', password='pw',
            current_ver='version_q',
        )
        self.friend_author = User.objects.create_user(
            username='friend_author', email='friend_author@t.com', password='pw',
            current_ver='version_q',
        )
        self.close_author = User.objects.create_user(
            username='close_author', email='close_author@t.com', password='pw',
            current_ver='version_q',
        )
        self.public_author = User.objects.create_user(
            username='public_author', email='public_author@t.com', password='pw',
            current_ver='version_q',
        )
        connect(self.friend_author, self.viewer, author_choice='friend')
        connect(self.close_author, self.viewer, author_choice='close_friend')
        connect(self.public_author, self.viewer, author_choice='friend')
        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def _create_post(self, author, visibility, caption):
        return CheckInPost.objects.create(
            author=author,
            image=make_image(f'{caption}.png'),
            caption=caption,
            visibility=visibility,
        )

    def test_friends_story_rail_excludes_public_snapshots(self):
        friend_post = self._create_post(self.friend_author, 'friends', 'friends only')
        close_post = self._create_post(self.close_author, 'close_friends', 'close friends only')
        public_post = self._create_post(self.public_author, 'public', 'public snapshot')

        resp = self.client.get(reverse('check-in-post-stories'))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row['id'] for row in resp.data['results']]
        self.assertIn(friend_post.id, ids)
        self.assertIn(close_post.id, ids)
        self.assertNotIn(public_post.id, ids)

    def test_public_story_rail_returns_only_public_snapshots(self):
        friend_post = self._create_post(self.friend_author, 'friends', 'friends only')
        close_post = self._create_post(self.close_author, 'close_friends', 'close friends only')
        public_post = self._create_post(self.public_author, 'public', 'public snapshot')

        resp = self.client.get(reverse('check-in-post-stories'), {'visibility': 'public'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row['id'] for row in resp.data['results']]
        self.assertEqual(ids, [public_post.id])
        self.assertNotIn(friend_post.id, ids)
        self.assertNotIn(close_post.id, ids)


class CheckInPostPinToggleTests(TestCase):
    """Scenarios 6–10 — PATCH /pin/ and /pin_visibility/ behavior."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@t.com', password='pw',
            current_ver='version_q',
        )
        self.other = User.objects.create_user(
            username='other', email='other@t.com', password='pw',
            current_ver='version_q',
        )
        self.client = APIClient()

    def _create_post(self, visibility='friends'):
        return CheckInPost.objects.create(
            author=self.author, image=make_image(),
            caption='hi', visibility=visibility,
        )

    def test_pin_toggle_on_copies_visibility(self):
        """6: PATCH /pin/ on unpinned → is_pinned=True, pin_visibility=visibility."""
        post = self._create_post(visibility='close_friends')
        self.client.force_authenticate(user=self.author)
        resp = self.client.patch(reverse('check-in-post-pin', kwargs={'pk': post.id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertTrue(post.is_pinned)
        self.assertEqual(post.pin_visibility, 'close_friends')

    def test_pin_toggle_off_clears_pin_visibility(self):
        """7: PATCH /pin/ on pinned → is_pinned=False, pin_visibility=None."""
        post = self._create_post()
        post.is_pinned = True
        post.pin_visibility = 'friends'
        post.save()

        self.client.force_authenticate(user=self.author)
        resp = self.client.patch(reverse('check-in-post-pin', kwargs={'pk': post.id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertFalse(post.is_pinned)
        self.assertIsNone(post.pin_visibility)

    def test_pin_others_post_returns_404(self):
        """8: PATCH /pin/ on someone else's post → 404 (no existence leak)."""
        post = self._create_post()
        self.client.force_authenticate(user=self.other)
        resp = self.client.patch(reverse('check-in-post-pin', kwargs={'pk': post.id}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_pin_visibility_on_unpinned_returns_400(self):
        """9: PATCH /pin_visibility/ on unpinned post → 400."""
        post = self._create_post()
        self.client.force_authenticate(user=self.author)
        resp = self.client.patch(
            reverse('check-in-post-pin-visibility', kwargs={'pk': post.id}),
            data={'pin_visibility': 'close_friends'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pin_visibility_changes_on_pinned(self):
        """10: PATCH /pin_visibility/ {'close_friends'} on pinned → 200, value updated."""
        post = self._create_post(visibility='friends')
        self.client.force_authenticate(user=self.author)
        # Pin first to seed pin_visibility=friends
        self.client.patch(reverse('check-in-post-pin', kwargs={'pk': post.id}))
        # Then narrow to close_friends
        resp = self.client.patch(
            reverse('check-in-post-pin-visibility', kwargs={'pk': post.id}),
            data={'pin_visibility': 'close_friends'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertEqual(post.pin_visibility, 'close_friends')

    def test_pin_visibility_invalid_value_returns_400(self):
        """`only_me` and `public` are not valid for CheckInPost (2-value enum)."""
        post = self._create_post()
        self.client.force_authenticate(user=self.author)
        self.client.patch(reverse('check-in-post-pin', kwargs={'pk': post.id}))
        resp = self.client.patch(
            reverse('check-in-post-pin-visibility', kwargs={'pk': post.id}),
            data={'pin_visibility': 'only_me'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class CheckInPostExpiryPinInteractionTests(TestCase):
    """Scenarios 11–15 — pin keeps post visible past expiry, governed by
    pin_visibility (independent of original visibility)."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@t.com', password='pw',
            current_ver='version_q',
        )
        self.regular_friend = User.objects.create_user(
            username='regular', email='r@t.com', password='pw',
            current_ver='version_q',
        )
        self.close_friend = User.objects.create_user(
            username='close', email='c@t.com', password='pw',
            current_ver='version_q',
        )
        # author classified `regular_friend` as plain friend
        connect(self.author, self.regular_friend, author_choice='friend')
        # author classified `close_friend` as close_friend
        connect(self.author, self.close_friend, author_choice='close_friend')
        self.client = APIClient()

    def _create_pinned(self, visibility='friends', pin_visibility='friends', age_hours=25):
        post = CheckInPost.objects.create(
            author=self.author, image=make_image(),
            caption='hi', visibility=visibility,
            is_pinned=True, pin_visibility=pin_visibility,
        )
        return age_post(post, hours=age_hours)

    def test_expired_pinned_friends_visible_to_friend(self):
        """11: 24h+, pinned, pin_visibility=friends → visible in friend feed."""
        post = self._create_pinned(pin_visibility='friends')
        self.client.force_authenticate(user=self.regular_friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(post.id, ids)

    def test_expired_pinned_close_friends_visible_to_close_friend(self):
        """12: 24h+, pinned, pin_visibility=close_friends, viewer=close → visible."""
        post = self._create_pinned(pin_visibility='close_friends')
        self.client.force_authenticate(user=self.close_friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(post.id, ids)

    def test_expired_pinned_close_friends_hidden_from_regular_friend(self):
        """13: 24h+, pinned, pin_visibility=close_friends, viewer=regular friend
        → hidden, even when original visibility was 'friends'.
        pin_visibility takes precedence over the original visibility for expired posts."""
        post = self._create_pinned(visibility='friends', pin_visibility='close_friends')
        self.client.force_authenticate(user=self.regular_friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        ids = [r['id'] for r in resp.data['results']]
        self.assertNotIn(post.id, ids)

    def test_unpinning_expired_post_hides_immediately(self):
        """14: toggling pin OFF on expired post → instantly disappears from friend feed."""
        post = self._create_pinned(pin_visibility='friends')
        # baseline: visible
        self.client.force_authenticate(user=self.regular_friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        self.assertIn(post.id, [r['id'] for r in resp.data['results']])
        # author unpins
        self.client.force_authenticate(user=self.author)
        self.client.patch(reverse('check-in-post-pin', kwargs={'pk': post.id}))
        # friend feed: gone
        self.client.force_authenticate(user=self.regular_friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        self.assertNotIn(post.id, [r['id'] for r in resp.data['results']])

    def test_crossing_expiry_threshold_hides_unpinned(self):
        """15: a fresh post visible at t<24h disappears for friends once aged past 24h."""
        post = CheckInPost.objects.create(
            author=self.author, image=make_image(),
            caption='hi', visibility='friends',
        )
        # fresh: visible
        self.client.force_authenticate(user=self.regular_friend)
        resp = self.client.get(reverse('check-in-post-feed'))
        self.assertIn(post.id, [r['id'] for r in resp.data['results']])
        # age past expiry: hidden
        age_post(post, hours=CHECK_IN_POST_EXPIRY_HOURS + 1)
        resp = self.client.get(reverse('check-in-post-feed'))
        self.assertNotIn(post.id, [r['id'] for r in resp.data['results']])

    def test_pinned_close_friends_visible_to_author_themselves(self):
        """Author always sees own pinned posts regardless of pin_visibility."""
        post = self._create_pinned(pin_visibility='close_friends')
        self.assertTrue(post.is_audience(self.author))

    def test_serializer_exposes_pin_fields(self):
        """is_pinned / pin_visibility are present on read responses."""
        post = self._create_pinned(pin_visibility='friends', age_hours=1)
        self.client.force_authenticate(user=self.regular_friend)
        resp = self.client.get(
            reverse('check-in-post-detail', kwargs={'pk': post.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('is_pinned', resp.data)
        self.assertIn('pin_visibility', resp.data)
        self.assertTrue(resp.data['is_pinned'])
        self.assertEqual(resp.data['pin_visibility'], 'friends')
