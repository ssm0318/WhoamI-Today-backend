from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from check_in.models import CheckIn

User = get_user_model()

class CheckInLatestVisibilityAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('current-user-latest-check-in-visibility')

    def test_default_visibility_no_check_ins(self):
        """
        If the user has no check-ins, return the default ['public'].
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['visibility'], ['public'])

    def test_visibility_with_existing_check_in(self):
        """
        If the user has check-ins, return the visibility of the most recent one.
        """
        # Create an old check-in
        CheckIn.objects.create(user=self.user, visibility=['public'], description="Old check-in")
        
        # Create a newer check-in
        CheckIn.objects.create(user=self.user, visibility=['friends'], description="New check-in")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['visibility'], ['friends'])

    def test_visibility_updates_safely(self):
        """
        Ensure that deleting a check-in (soft delete) respects the remaining latest one (or default).
        """
        check_in = CheckIn.objects.create(user=self.user, visibility=['friends'], description="To be deleted")

        # Verify initial state
        response = self.client.get(self.url)
        self.assertEqual(response.data['visibility'], ['friends'])
        
        # Delete the check-in
        check_in.delete()
        
        response = self.client.get(self.url)
        self.assertEqual(response.data['visibility'], ['public'])
