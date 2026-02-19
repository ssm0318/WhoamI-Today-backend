from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from pin.models import Pin
from note.models import Note
from qna.models import Question, Response

User = get_user_model()

class PinSoftDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.question = Question.objects.create(author=self.user, content='test question')
        
    def test_pin_deleted_when_note_deleted(self):
        # Create note
        note = Note.objects.create(author=self.user, content='test note')
        
        # Create pin
        pin = Pin.objects.create(user=self.user, content_object=note)
        
        # Verify pin exists
        self.assertEqual(Pin.objects.count(), 1)
        
        # Soft delete note
        note.delete()
        
        # Verify note is soft-deleted (if Note uses safedelete)
        self.assertTrue(note.deleted)
        
        # Verify pin is soft-deleted
        self.assertEqual(Pin.objects.count(), 0)
        self.assertEqual(Pin.all_objects.count(), 1) # Including soft-deleted
        self.assertTrue(Pin.all_objects.get(id=pin.id).deleted)

    def test_pin_deleted_when_response_deleted(self):
        # Create response
        response = Response.objects.create(author=self.user, question=self.question, content='test response')
        
        # Create pin
        pin = Pin.objects.create(user=self.user, content_object=response)
        
        # Verify pin exists
        self.assertEqual(Pin.objects.count(), 1)
        
        # Soft delete response
        response.delete()
        
        # Verify response is soft-deleted
        self.assertTrue(response.deleted)
        
        # Verify pin is soft-deleted
        self.assertEqual(Pin.objects.count(), 0)
        self.assertEqual(Pin.all_objects.count(), 1) # Including soft-deleted
        self.assertTrue(Pin.all_objects.get(id=pin.id).deleted)

    def test_pin_not_deleted_when_unrelated_object_deleted(self):
        # Create note and pin
        note = Note.objects.create(author=self.user, content='pinned note')
        pin = Pin.objects.create(user=self.user, content_object=note)
        
        # Create another note and delete it
        unrelated_note = Note.objects.create(author=self.user, content='unrelated note')
        unrelated_note.delete()
        
        # Verify pin still exists
        self.assertEqual(Pin.objects.count(), 1)
        self.assertFalse(Pin.objects.get(id=pin.id).deleted)

    def test_repin_after_unpin(self):
        # Create note
        note = Note.objects.create(author=self.user, content='test note')
        
        # Pin it
        Pin.objects.create(user=self.user, content_object=note)
        self.assertEqual(Pin.objects.count(), 1)
        
        # Unpin (soft-delete)
        Pin.objects.get(user=self.user, content_type=ContentType.objects.get_for_model(Note), object_id=note.id).delete()
        self.assertEqual(Pin.objects.count(), 0)
        self.assertEqual(Pin.all_objects.count(), 1)
        
        # Pin again (re-pin)
        # This should NOT raise IntegrityError now
        Pin.objects.create(user=self.user, content_object=note)
        self.assertEqual(Pin.objects.count(), 1)
        self.assertEqual(Pin.all_objects.count(), 2)

    def test_cannot_pin_deleted_note(self):
        from rest_framework.test import APIClient
        from django.urls import reverse
        
        client = APIClient()
        client.force_authenticate(user=self.user)
        
        note = Note.objects.create(author=self.user, content='deleted note')
        note.delete()
        
        url = reverse('pin-create')
        data = {
            'content_type': 'Note',
            'object_id': note.id
        }
        response = client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('삭제되었습니다', str(response.data))

    def test_cannot_pin_deleted_response(self):
        from rest_framework.test import APIClient
        from django.urls import reverse
        
        client = APIClient()
        client.force_authenticate(user=self.user)
        
        res = Response.objects.create(author=self.user, question=self.question, content='deleted response')
        res.delete()
        
        url = reverse('pin-create')
        data = {
            'content_type': 'Response',
            'object_id': res.id
        }
        response = client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('삭제되었습니다', str(response.data))
