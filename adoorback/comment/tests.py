from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.contrib.auth import get_user_model

from account.models import Connection
from comment.models import Comment
from note.models import Note
from notification.models import Notification

User = get_user_model()


def _make_comment(author, target, content='test comment', is_private=False):
    """Create a Comment via ORM (triggers the post_save signal)."""
    ct = ContentType.objects.get_for_model(target)
    return Comment.objects.create(
        author=author,
        content_type=ct,
        object_id=target.id,
        content=content,
        is_private=is_private,
    )


@patch('notification.models.notify_firebase')
class CommentNotificationAudienceTests(TestCase):
    """Verify that comment notifications respect post audience (is_audience)."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='author', email='author@test.com', password='pass')
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='pass')
        self.stranger = User.objects.create_user(
            username='stranger', email='stranger@test.com', password='pass')
        self.commenter = User.objects.create_user(
            username='commenter', email='commenter@test.com', password='pass')

        # author <-> friend are connected
        Connection.objects.create(user1=self.author, user2=self.friend)
        # author <-> commenter are connected
        Connection.objects.create(user1=self.author, user2=self.commenter)

    # ------------------------------------------------------------------
    # 댓글 → 참여자: audience인 경우 알림 O
    # ------------------------------------------------------------------
    def test_comment_participant_receives_noti_when_audience(self, mock_firebase):
        note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])

        # friend comments first → becomes participant
        _make_comment(self.friend, note, 'first comment')
        # commenter comments → friend (participant) should get noti
        Notification.objects.all().delete()
        _make_comment(self.commenter, note, 'second comment')

        self.assertTrue(
            Notification.objects.filter(
                user=self.friend,
                target_type=ContentType.objects.get_for_model(Comment),
            ).exists(),
            "Friend is audience and participant — should receive notification"
        )

    # ------------------------------------------------------------------
    # 댓글 → 참여자: audience가 아닌 경우 알림 X
    # ------------------------------------------------------------------
    def test_comment_participant_no_noti_when_not_audience(self, mock_firebase):
        note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])

        # friend comments → becomes participant
        _make_comment(self.friend, note, 'first comment')

        # author unfriends friend → friend is no longer audience
        Connection.objects.filter(user1=self.author, user2=self.friend).delete()

        Notification.objects.all().delete()
        # commenter comments → friend should NOT get noti (no longer audience)
        _make_comment(self.commenter, note, 'second comment')

        self.assertFalse(
            Notification.objects.filter(
                user=self.friend,
                target_type=ContentType.objects.get_for_model(Comment),
            ).exists(),
            "Friend is no longer audience — should NOT receive notification"
        )

    # ------------------------------------------------------------------
    # 댓글 → 글 작성자: 항상 알림 O (자기 글이니까)
    # ------------------------------------------------------------------
    def test_comment_author_always_gets_noti(self, mock_firebase):
        note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])

        Notification.objects.all().delete()
        _make_comment(self.friend, note, 'a comment')

        self.assertTrue(
            Notification.objects.filter(
                user=self.author,
                target_type=ContentType.objects.get_for_model(Comment),
            ).exists(),
            "Post author should always receive comment notification"
        )

    # ------------------------------------------------------------------
    # 대댓글 → 원댓글 작성자: audience인 경우 알림 O
    # ------------------------------------------------------------------
    def test_reply_origin_author_receives_noti_when_audience(self, mock_firebase):
        note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])
        comment = _make_comment(self.friend, note, 'top-level comment')

        Notification.objects.all().delete()
        _make_comment(self.commenter, comment, 'reply')

        self.assertTrue(
            Notification.objects.filter(
                user=self.friend,
                target_type=ContentType.objects.get_for_model(Comment),
                message_en__contains='replied to your comment',
            ).exists(),
            "Comment author is audience — should receive reply notification"
        )

    # ------------------------------------------------------------------
    # 대댓글 → 원댓글 작성자: audience가 아닌 경우 알림 X
    # ------------------------------------------------------------------
    def test_reply_origin_author_no_noti_when_not_audience(self, mock_firebase):
        note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])
        comment = _make_comment(self.friend, note, 'top-level comment')

        # unfriend → friend loses access to the note
        Connection.objects.filter(user1=self.author, user2=self.friend).delete()

        Notification.objects.all().delete()
        _make_comment(self.commenter, comment, 'reply')

        self.assertFalse(
            Notification.objects.filter(
                user=self.friend,
                target_type=ContentType.objects.get_for_model(Comment),
                message_en__contains='replied to your comment',
            ).exists(),
            "Comment author is no longer audience — should NOT receive reply notification"
        )

    # ------------------------------------------------------------------
    # 대댓글 → 참여자: audience가 아닌 경우 알림 X
    # ------------------------------------------------------------------
    def test_reply_participant_no_noti_when_not_audience(self, mock_firebase):
        note = Note.objects.create(
            author=self.author, content='hello', visibility=['friends'])
        comment = _make_comment(self.friend, note, 'top-level comment')
        # friend replies → becomes participant of the comment thread
        _make_comment(self.friend, comment, 'reply 1')

        # unfriend
        Connection.objects.filter(user1=self.author, user2=self.friend).delete()

        Notification.objects.all().delete()
        # commenter replies → friend (participant) should NOT get noti
        _make_comment(self.commenter, comment, 'reply 2')

        self.assertFalse(
            Notification.objects.filter(
                user=self.friend,
                target_type=ContentType.objects.get_for_model(Comment),
                message_en__contains='you responded to',
            ).exists(),
            "Participant no longer audience — should NOT receive reply notification"
        )

    # ------------------------------------------------------------------
    # public 글 → 누구든 알림 받아야 함
    # ------------------------------------------------------------------
    def test_public_note_participant_always_gets_noti(self, mock_firebase):
        note = Note.objects.create(
            author=self.author, content='hello', visibility=['public'])

        # stranger comments (public이니까 가능)
        _make_comment(self.stranger, note, 'first')

        Notification.objects.all().delete()
        _make_comment(self.commenter, note, 'second')

        self.assertTrue(
            Notification.objects.filter(
                user=self.stranger,
                target_type=ContentType.objects.get_for_model(Comment),
            ).exists(),
            "Public note — stranger participant should receive notification"
        )
