from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from adoorback.utils.permissions import IsNotBlocked
from adoorback.utils.validators import adoor_exception_handler

from check_in.models import CheckIn
import check_in.serializers as cs
from qna.models import FriendGroup

User = get_user_model()


class CurrentCheckIn(generics.ListCreateAPIView):
    """
    Get current active check-in of request user or create a new check-in.
    """
    serializer_class = cs.MyCheckInSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        current_user = self.request.user
        share_group_ids = self.request.data.get('share_groups', [])
        share_groups = [get_object_or_404(FriendGroup, id=id_) for id_ in share_group_ids]
        share_friend_ids = self.request.data.get('share_friends', [])
        share_friends = [get_object_or_404(User, id=id_) for id_ in share_friend_ids]
        share_everyone = self.request.data.get('share_everyone', False)
        serializer.save(user=current_user, is_active=True,
                        share_friends=share_friends, share_groups=share_groups, 
                        share_everyone=share_everyone)

        # deactivate previous check-in
        previous_check_in = CheckIn.objects.filter(user=current_user, is_active=True) \
                                           .exclude(id=serializer.instance.id).first()
        if previous_check_in:
            previous_check_in.is_active = False
            previous_check_in.save()
        
        return Response(serializer.data)

    def get_queryset(self):
        current_user = self.request.user
        return CheckIn.objects.filter(user=current_user, is_active=True)


class CheckInDetail(generics.RetrieveUpdateAPIView):
    """
    Get a specific check-in, or update a check-in.
    """
    queryset = CheckIn.objects.all()
    serializer_class = cs.MyCheckInSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler
    
    def get_object(self):
        try:
            check_in = CheckIn.objects.get(id=self.kwargs.get('pk'))
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")
        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in has been edited or deleted.")
        if self.request.user != check_in.user:
            raise exceptions.PermissionDenied("Only the author can access check-in details.")
        return check_in

    def patch(self, request, *args, **kwargs):
        '''
        Used when user deletes a check-in, which makes the is_active field of check-in False.
        '''
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CheckInRead(generics.UpdateAPIView):
    queryset = CheckIn.objects.all()
    serializer_class = cs.CheckInBaseSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            check_in = CheckIn.objects.get(id=self.kwargs.get('pk'))
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")
        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in has been edited or deleted.")
        return check_in
    
    def patch(self, request, *args, **kwargs):
        '''
        Used when user views a friend's check-in.
        '''
        current_user = self.request.user
        instance = self.get_object()
        instance.readers.add(current_user)
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TrackRecentSearches(generics.ListAPIView):
    """
    Get recent 15 searched tracks.
    """
    serializer_class = cs.TrackSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler
    
    def get(self, request, *args, **kwargs):
        current_user = self.request.user
        recent_check_ins = CheckIn.objects.filter(user=current_user).order_by('-created_at')
        recent_track_ids = []
        for check_in in recent_check_ins:
            if len(recent_track_ids) >= 15:
                break
            if check_in.track_id and check_in.track_id not in recent_track_ids:
                recent_track_ids.append(check_in.track_id)
        serializer = self.get_serializer({'track_ids': recent_track_ids})
        return Response(serializer.data)
