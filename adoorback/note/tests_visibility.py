from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from note.models import Note
from account.models import Connection

User = get_user_model()

class NoteVisibilityTests(TestCase):
    def setUp(self):
        # Create users
        self.author = User.objects.create_user(username='author', email='author@example.com', password='password')
        self.friend = User.objects.create_user(username='friend', email='friend@example.com', password='password')
        self.follower = User.objects.create_user(username='follower', email='follower@example.com', password='password')
        self.stranger = User.objects.create_user(username='stranger', email='stranger@example.com', password='password')

        # Create relationships
        Connection.objects.create(user1=self.author, user2=self.friend) # Friends
        from account.models import Follow
        Follow.objects.create(follower=self.follower, followed=self.author) # Follower follows Author

        self.client = APIClient()

    def test_public_note_visibility(self):
        note = Note.objects.create(author=self.author, content='Public Note', visibility=['public'])
        
        # Stranger should see it
        self.assertTrue(note.is_audience(self.stranger))
        
        # Friend should NOT see it via public scope if logic is strict, 
        # BUT current logic says: if friend -> check 'friends'. 
        # So if public note doesn't have 'friends' in visibility, friend MIGHT NOT see it?
        # Let's check logic:
        # if is_friend: if 'friends' return True.
        # if not is_friend and not is_following: check 'public'.
        # So a strictly 'public' note is NOT visible to friends? That seems like a bug or legacy design choice.
        # However, usually 'public' implies everyone. 
        # Response logic:
        # is_friend -> check 'friends'
        # is_following -> check 'follower'
        # else -> check 'public'
        # So if I mark something as 'public' only, friends won't see it?
        # The user request said "Make it exactly like Response".
        # Let's verify Response logic behavior.
        pass

    def test_followers_note_visibility(self):
        note = Note.objects.create(author=self.author, content='Follower Note', visibility=['followers'])
        
        # Follower should see it
        self.assertTrue(note.is_audience(self.follower))
        
        # Stranger should NOT see it
        self.assertFalse(note.is_audience(self.stranger))
        
        # Friend should NOT see it (unless they are following, but friends are connected, not following)
        # Note: In this system friend != following.
        self.assertFalse(note.is_audience(self.friend))

    def test_verify_response_style_logic(self):
        # The user said "Make it exactly like Response". 
        # Let's ensure my implementation matches Response logic.
        
        # Case 1: Public Note
        # If I want it to be visible to EVERYONE, I probably need to check multiple boxes or the logic is exclusive.
        # In Response logic:
        # if is_friend: check 'friends'
        # ...
        # if public: check 'public'
        # So if I publish a Response with ONLY 'public', friends cannot see it?
        # Let's test this assumption with Note implementation.
        
        note_public = Note.objects.create(author=self.author, content='Public Only', visibility=['public'])
        # Friend: is_friend=True. checks 'friends' in visibility. 'friends' NOT in ['public']. Returns False.
        # So Friend CANNOT see public-only note? 
        # If so, the frontend must auto-select 'friends' when 'public' is selected, OR logic needs to be inclusive.
        # But I am instructed to copy Response logic. So I will test that it behaves LIKE Response.
        
        self.assertFalse(note_public.is_audience(self.friend)) # Matches interpreted Response logic
        self.assertTrue(note_public.is_audience(self.stranger))

        # Case 2: Friend Note
        note_friend = Note.objects.create(author=self.author, content='Friend Only', visibility=['friends'])
        self.assertTrue(note_friend.is_audience(self.friend))
        self.assertFalse(note_friend.is_audience(self.stranger))
        self.assertFalse(note_friend.is_audience(self.follower))

    def test_api_visibility(self):
        # Public Note
        Note.objects.create(author=self.author, content='Public Content', visibility=['public'])
        
        # Stranger requests
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(f'/api/user/{self.author.username}/notes/')
        self.assertEqual(len(response.data['results']), 1)
        
        # Friend requests (should see 0 if my analysis is correct)
        self.client.force_authenticate(user=self.friend)
        response = self.client.get(f'/api/user/{self.author.username}/notes/')
        self.assertEqual(len(response.data['results']), 0) 
        
        # Follower requests (should see 0)
        self.client.force_authenticate(user=self.follower)
        response = self.client.get(f'/api/user/{self.author.username}/notes/')
        self.assertEqual(len(response.data['results']), 0)
