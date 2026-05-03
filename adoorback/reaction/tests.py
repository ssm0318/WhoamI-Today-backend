from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import Connection
from comment.models import Comment
from note.models import Note
from notification.models import Notification
from reaction.models import Reaction

User = get_user_model()


def _make_comment(author, target, content='test comment', is_private=False):
    ct = ContentType.objects.get_for_model(target)
    return Comment.objects.create(
        author=author,
        content_type=ct,
        object_id=target.id,
        content=content,
        is_private=is_private,
    )


def _make_reaction(user, target, emoji='🔥'):
    ct = ContentType.objects.get_for_model(target)
    return Reaction.objects.create(
        user=user,
        content_type=ct,
        object_id=target.id,
        emoji=emoji,
    )


# ======================================================================
# Signal / Notification tests
# ======================================================================
@patch('notification.models.notify_firebase')
class CommentReactionNotificationTests(TestCase):
    """댓글 이모지 리액션 알림 테스트."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@test.com', password='pass')
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='pass')
        self.stranger = User.objects.create_user(
            username='stranger', email='stranger@test.com', password='pass')
        Connection.objects.create(user1=self.author, user2=self.friend)
        Connection.objects.create(user1=self.author, user2=self.stranger)

        self.note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])
        self.comment = _make_comment(self.friend, self.note, 'nice post')

    def test_reaction_on_comment_creates_notification(self, mock_fb):
        """다른 사람의 댓글에 리액션 → 알림 생성."""
        Notification.objects.all().delete()
        _make_reaction(self.stranger, self.comment, '❤️')

        noti = Notification.objects.filter(user=self.friend)
        self.assertEqual(noti.count(), 1)
        self.assertIn('댓글', noti.first().message_ko)
        self.assertNotIn('❤️', noti.first().message_ko)

    def test_self_reaction_no_notification(self, mock_fb):
        """자기 댓글에 리액션 → 알림 없음."""
        Notification.objects.all().delete()
        _make_reaction(self.friend, self.comment, '👍')

        self.assertFalse(
            Notification.objects.filter(user=self.friend).exists(),
            "Self-reaction should NOT create notification"
        )

    def test_self_reaction_allowed_in_db(self, mock_fb):
        """자기 댓글에 리액션 → DB에는 저장됨."""
        reaction = _make_reaction(self.friend, self.comment, '👍')
        self.assertIsNotNone(reaction.id)

    def test_multiple_different_emojis_on_same_comment(self, mock_fb):
        """한 사람이 같은 댓글에 여러 이모지 리액션 가능."""
        r1 = _make_reaction(self.stranger, self.comment, '🔥')
        r2 = _make_reaction(self.stranger, self.comment, '❤️')
        r3 = _make_reaction(self.stranger, self.comment, '😂')
        self.assertEqual(
            Reaction.objects.filter(
                user=self.stranger,
                content_type=ContentType.objects.get_for_model(self.comment),
                object_id=self.comment.id,
            ).count(),
            3,
        )

    def test_duplicate_emoji_rejected(self, mock_fb):
        """같은 이모지 중복 리액션 → IntegrityError."""
        _make_reaction(self.stranger, self.comment, '🔥')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            _make_reaction(self.stranger, self.comment, '🔥')

    def test_reaction_on_reply_notification_redirect(self, mock_fb):
        """대댓글에 리액션 → redirect_url이 root post를 가리킴."""
        reply = _make_comment(self.stranger, self.comment, 'reply text')
        Notification.objects.all().delete()
        _make_reaction(self.author, reply, '👏')

        noti = Notification.objects.filter(user=self.stranger).first()
        self.assertIsNotNone(noti)
        self.assertIn(f'/notes/{self.note.id}', noti.redirect_url)

    def test_blocked_user_no_notification(self, mock_fb):
        """차단된 유저의 리액션 → 알림 없음."""
        from user_report.models import UserReport
        UserReport.objects.create(user=self.friend, reported_user=self.stranger)

        Notification.objects.all().delete()
        _make_reaction(self.stranger, self.comment, '🔥')

        self.assertFalse(
            Notification.objects.filter(user=self.friend).exists(),
            "Blocked user's reaction should NOT create notification"
        )

    def test_notification_message_format(self, mock_fb):
        """알림 메시지에 이모지 없이, 댓글 내용 미리보기 포함."""
        Notification.objects.all().delete()
        _make_reaction(self.stranger, self.comment, '🎉')

        noti = Notification.objects.filter(user=self.friend).first()
        self.assertNotIn('🎉', noti.message_ko)
        self.assertIn('반응을 남겼습니다', noti.message_ko)
        self.assertIn('reacted to', noti.message_en)

    def test_different_emojis_aggregated_into_one_notification(self, mock_fb):
        """다른 이모지 리액션도 하나의 알림으로 합쳐짐."""
        third_user = User.objects.create_user(
            username='third', email='third@test.com', password='pass')
        Connection.objects.create(user1=self.author, user2=third_user)

        Notification.objects.all().delete()
        _make_reaction(self.stranger, self.comment, '🔥')
        _make_reaction(third_user, self.comment, '❤️')

        notis = Notification.objects.filter(user=self.friend)
        self.assertEqual(notis.count(), 1, "Different emojis should be aggregated into one notification")
        self.assertIn('third', notis.first().message_ko)

    def test_same_user_multiple_emojis_counted_once(self, mock_fb):
        """같은 사람이 여러 이모지 리액션 → 알림에 한 번만 카운트."""
        Notification.objects.all().delete()
        _make_reaction(self.stranger, self.comment, '🔥')
        _make_reaction(self.stranger, self.comment, '❤️')
        _make_reaction(self.stranger, self.comment, '😂')

        notis = Notification.objects.filter(user=self.friend)
        self.assertEqual(notis.count(), 1)
        # actor가 1명이므로 "외 N명" 없이 단독 메시지
        noti = notis.first()
        self.assertEqual(noti.actors.count(), 1)
        self.assertNotIn('외', noti.message_ko)


# ======================================================================
# API endpoint tests
# ======================================================================
@patch('notification.models.notify_firebase')
class CommentReactionAPITests(APITestCase):
    """댓글 리액션 API 엔드포인트 테스트."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@test.com', password='pass')
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='pass')
        self.stranger = User.objects.create_user(
            username='stranger', email='stranger@test.com', password='pass')
        Connection.objects.create(user1=self.author, user2=self.friend)
        Connection.objects.create(user1=self.author, user2=self.stranger)

        self.note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])
        self.comment = _make_comment(self.friend, self.note, 'nice post')

    def _reaction_url(self, comment_id):
        return f'/api/reactions/Comment/{comment_id}/'

    # -- Create --
    def test_create_reaction_on_comment(self, mock_fb):
        """POST /api/reactions/Comment/<id>/ → 201."""
        self.client.force_authenticate(user=self.stranger)
        response = self.client.post(self._reaction_url(self.comment.id), {'emoji': '🔥'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['emoji'], '🔥')

    def test_create_self_reaction(self, mock_fb):
        """자기 댓글에 리액션 → 201 (허용)."""
        self.client.force_authenticate(user=self.friend)
        response = self.client.post(self._reaction_url(self.comment.id), {'emoji': '❤️'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_multiple_emojis(self, mock_fb):
        """같은 댓글에 여러 이모지 → 각각 201."""
        self.client.force_authenticate(user=self.stranger)
        r1 = self.client.post(self._reaction_url(self.comment.id), {'emoji': '🔥'})
        r2 = self.client.post(self._reaction_url(self.comment.id), {'emoji': '❤️'})
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)

    def test_duplicate_emoji_rejected(self, mock_fb):
        """같은 이모지 중복 → 406."""
        self.client.force_authenticate(user=self.stranger)
        self.client.post(self._reaction_url(self.comment.id), {'emoji': '🔥'})
        response = self.client.post(self._reaction_url(self.comment.id), {'emoji': '🔥'})
        self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    # -- List (visibility) --
    def test_list_reactions_visible_comment(self, mock_fb):
        """볼 수 있는 댓글의 리액션 전체 조회 가능."""
        _make_reaction(self.stranger, self.comment, '🔥')
        _make_reaction(self.author, self.comment, '❤️')

        # stranger가 조회 (댓글 author 아니지만 public comment이므로 전체 보임)
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self._reaction_url(self.comment.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_list_reactions_private_comment_author_sees_all(self, mock_fb):
        """private 댓글 작성자는 리액션 전체 조회 가능."""
        private_comment = _make_comment(
            self.friend, self.note, 'secret', is_private=True)
        _make_reaction(self.author, private_comment, '🔥')

        self.client.force_authenticate(user=self.friend)
        response = self.client.get(self._reaction_url(private_comment.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_list_reactions_private_comment_non_authorized_empty(self, mock_fb):
        """private 댓글을 볼 수 없는 유저 → 빈 리스트."""
        private_comment = _make_comment(
            self.friend, self.note, 'secret', is_private=True)
        _make_reaction(self.author, private_comment, '🔥')

        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self._reaction_url(private_comment.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_list_reactions_private_comment_post_author_sees_all(self, mock_fb):
        """private 댓글의 대상 글 작성자는 리액션 조회 가능."""
        private_comment = _make_comment(
            self.friend, self.note, 'secret', is_private=True)
        _make_reaction(self.friend, private_comment, '🔥')

        # author는 note의 작성자이므로 private comment 접근 가능
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self._reaction_url(private_comment.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    # -- Delete --
    def test_delete_own_reaction(self, mock_fb):
        """자신의 리액션 삭제 → 204."""
        reaction = _make_reaction(self.stranger, self.comment, '🔥')
        self.client.force_authenticate(user=self.stranger)
        response = self.client.delete(f'/api/reactions/{reaction.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_others_reaction_forbidden(self, mock_fb):
        """다른 사람의 리액션 삭제 → 403."""
        reaction = _make_reaction(self.stranger, self.comment, '🔥')
        self.client.force_authenticate(user=self.friend)
        response = self.client.delete(f'/api/reactions/{reaction.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -- Version isolation --
    def test_version_isolation(self, mock_fb):
        """다른 버전 유저의 댓글에 리액션 → 403."""
        ver_q_user = User.objects.create_user(
            username='quser', email='q@test.com', password='pass',
            current_ver='version_q')
        ver_w_user = User.objects.create_user(
            username='wuser', email='w@test.com', password='pass',
            current_ver='version_w')
        Connection.objects.create(user1=self.author, user2=ver_q_user)
        q_comment = _make_comment(ver_q_user, self.note, 'q comment')

        self.client.force_authenticate(user=ver_w_user)
        response = self.client.post(self._reaction_url(q_comment.id), {'emoji': '🔥'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ======================================================================
# Serializer tests
# ======================================================================
@patch('notification.models.notify_firebase')
class CommentReactionSerializerTests(APITestCase):
    """댓글 serializer에 리액션 필드가 포함되는지 테스트."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@test.com', password='pass')
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='pass')
        Connection.objects.create(user1=self.author, user2=self.friend)

        self.note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])
        self.comment = _make_comment(self.friend, self.note, 'nice post')

    def test_comment_has_reaction_fields(self, mock_fb):
        """댓글 API에 current_user_reaction_id_list, like_reaction_user_sample 포함."""
        self.client.force_authenticate(user=self.author)
        response = self.client.get(f'/api/notes/{self.note.id}/comments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        comment_data = response.data['results'][0]
        self.assertIn('current_user_reaction_id_list', comment_data)
        self.assertIn('like_reaction_user_sample', comment_data)

    def test_current_user_reaction_id_list_populated(self, mock_fb):
        """내가 리액션한 이모지가 current_user_reaction_id_list에 포함."""
        _make_reaction(self.author, self.comment, '🔥')
        _make_reaction(self.author, self.comment, '❤️')

        self.client.force_authenticate(user=self.author)
        response = self.client.get(f'/api/notes/{self.note.id}/comments/')
        comment_data = response.data['results'][0]

        reaction_list = comment_data['current_user_reaction_id_list']
        emojis = {r['emoji'] for r in reaction_list}
        self.assertEqual(emojis, {'🔥', '❤️'})

    def test_like_reaction_user_sample_includes_reactions(self, mock_fb):
        """like_reaction_user_sample에 리액션 유저 포함."""
        _make_reaction(self.author, self.comment, '🔥')

        self.client.force_authenticate(user=self.friend)
        response = self.client.get(f'/api/notes/{self.note.id}/comments/')
        comment_data = response.data['results'][0]

        sample = comment_data['like_reaction_user_sample']
        self.assertEqual(len(sample), 1)
        self.assertEqual(sample[0]['reaction'], '🔥')
        self.assertFalse(sample[0]['like'])
