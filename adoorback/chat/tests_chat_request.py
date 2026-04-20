from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Connection
from chat.models import ChatRequest, ChatRoom
from notification.models import Notification

User = get_user_model()


class ChatRequestCreateTests(TestCase):
    """Chat request 생성 및 자동 수락 테스트."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='jaewon', email='jaewon@test.com', password='pw',
        )
        self.user_b = User.objects.create_user(
            username='gina_park', email='gina@test.com', password='pw',
        )
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)
        self.url = reverse('chat-request-create')

    # --- 정상 생성 ---
    def test_create_chat_request(self):
        """비친구에게 챗 요청 생성 → 201."""
        resp = self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ChatRequest.objects.filter(requester=self.user_a, requestee=self.user_b).exists()
        )

    # --- 노티 생성 확인 ---
    def test_create_chat_request_sends_notification(self):
        """챗 요청 생성 시 requestee에게 노티가 생성된다."""
        self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.assertTrue(
            Notification.objects.filter(
                user=self.user_b,
                message_ko__contains='채팅 요청을 보냈습니다',
            ).exists()
        )

    # --- 핵심 버그 수정: 역방향 요청 → 자동 수락 ---
    def test_reverse_request_auto_accepts(self):
        """A→B pending 상태에서 B→A 요청 → 자동 수락 + 200."""
        # A가 B에게 요청
        self.client_a.post(self.url, {'requestee_id': self.user_b.id})

        # B가 A에게 요청 → 자동 수락
        resp = self.client_b.post(self.url, {'requestee_id': self.user_a.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data.get('auto_accepted'))

    def test_reverse_request_creates_chat_room(self):
        """자동 수락 시 챗방이 생성된다."""
        self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.client_b.post(self.url, {'requestee_id': self.user_a.id})

        u1, u2 = (self.user_a, self.user_b) if self.user_a.id < self.user_b.id else (self.user_b, self.user_a)
        self.assertTrue(ChatRoom.objects.filter(user1=u1, user2=u2).exists())

    def test_reverse_request_marks_accepted(self):
        """자동 수락 시 기존 요청의 accepted가 True로 변경된다."""
        self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.client_b.post(self.url, {'requestee_id': self.user_a.id})

        req = ChatRequest.objects.get(requester=self.user_a, requestee=self.user_b)
        self.assertTrue(req.accepted)

    def test_reverse_request_sends_accepted_notification(self):
        """자동 수락 시 원래 requester(A)에게 수락 노티가 간다."""
        self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.client_b.post(self.url, {'requestee_id': self.user_a.id})

        self.assertTrue(
            Notification.objects.filter(
                user=self.user_a,
                message_ko__contains='채팅 요청을 수락했습니다',
            ).exists()
        )

    # --- 중복 요청 에러 ---
    def test_duplicate_pending_request_error(self):
        """같은 방향 pending 중복 → 에러."""
        self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        resp = self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_accepted_request_error(self):
        """이미 수락된 요청 있으면 → 에러."""
        ChatRequest.objects.create(
            requester=self.user_a, requestee=self.user_b, accepted=True,
        )
        resp = self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # --- declined 후 재요청 ---
    def test_retry_after_declined(self):
        """이전 요청이 declined면 새 요청 가능."""
        ChatRequest.objects.create(
            requester=self.user_a, requestee=self.user_b, accepted=False,
        )
        resp = self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_reverse_retry_after_declined(self):
        """상대 요청이 declined면 역방향 새 요청 가능."""
        ChatRequest.objects.create(
            requester=self.user_a, requestee=self.user_b, accepted=False,
        )
        resp = self.client_b.post(self.url, {'requestee_id': self.user_a.id})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    # --- 친구에게 요청 불가 ---
    def test_request_to_friend_error(self):
        """이미 친구인 유저에게 챗 요청 → 에러."""
        Connection.objects.create(
            user1=self.user_a, user2=self.user_b,
            user1_choice='friend', user2_choice='friend',
        )
        resp = self.client_a.post(self.url, {'requestee_id': self.user_b.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ChatRequestUpdateTests(TestCase):
    """Chat request 수동 수락/거절 테스트."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='jaewon', email='jaewon@test.com', password='pw',
        )
        self.user_b = User.objects.create_user(
            username='gina_park', email='gina@test.com', password='pw',
        )
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        self.chat_request = ChatRequest.objects.create(
            requester=self.user_a, requestee=self.user_b,
        )
        self.url = reverse('chat-request-update', kwargs={'pk': self.chat_request.id})

    def test_accept_creates_chat_room(self):
        """수동 수락 시 챗방이 생성된다."""
        resp = self.client_b.patch(self.url, {'accepted': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        u1, u2 = (self.user_a, self.user_b) if self.user_a.id < self.user_b.id else (self.user_b, self.user_a)
        self.assertTrue(ChatRoom.objects.filter(user1=u1, user2=u2).exists())

    def test_accept_sends_notification(self):
        """수동 수락 시 requester에게 수락 노티가 간다."""
        self.client_b.patch(self.url, {'accepted': True})
        self.assertTrue(
            Notification.objects.filter(
                user=self.user_a,
                message_ko__contains='채팅 요청을 수락했습니다',
            ).exists()
        )

    def test_decline_does_not_create_chat_room(self):
        """거절 시 챗방이 생성되지 않는다."""
        self.client_b.patch(self.url, {'accepted': False})

        u1, u2 = (self.user_a, self.user_b) if self.user_a.id < self.user_b.id else (self.user_b, self.user_a)
        self.assertFalse(ChatRoom.objects.filter(user1=u1, user2=u2).exists())

    def test_only_requestee_can_respond(self):
        """requester는 자신의 요청에 응답할 수 없다."""
        client_a = APIClient()
        client_a.force_authenticate(user=self.user_a)
        resp = client_a.patch(self.url, {'accepted': True})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class ChatRequestListTests(TestCase):
    """Chat request 리스트 조회 테스트."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='jaewon', email='jaewon@test.com', password='pw',
        )
        self.user_b = User.objects.create_user(
            username='gina_park', email='gina@test.com', password='pw',
        )
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        # A→B pending 요청
        ChatRequest.objects.create(requester=self.user_a, requestee=self.user_b)

    def test_received_list(self):
        """requestee(B)는 받은 pending 요청 리스트를 볼 수 있다."""
        resp = self.client_b.get(reverse('chat-request-create'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 1)

    def test_sent_list(self):
        """requester(A)는 보낸 요청 리스트를 볼 수 있다."""
        resp = self.client_a.get(reverse('chat-request-sent-list'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 1)
