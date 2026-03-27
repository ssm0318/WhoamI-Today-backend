from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from adoorback.utils.validators import adoor_exception_handler

from check_in.models import CheckIn, Song
import check_in.serializers as cs

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
        
        # TODO: Refactor this temporary logic later (default visibility)
        if not serializer.validated_data.get('visibility'):
            last_check_in = CheckIn.objects.filter(user=current_user).order_by('-created_at').first()
            if last_check_in:
                serializer.validated_data['visibility'] = last_check_in.visibility
            else:
                serializer.validated_data['visibility'] = ['public']

        serializer.save(user=current_user, is_active=True)

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


class CurrentUserLatestCheckInVisibility(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        user = request.user
        latest_check_in = CheckIn.objects.filter(user=user).order_by('-created_at').first()

        if latest_check_in:
            return Response({'visibility': latest_check_in.visibility}, status=status.HTTP_200_OK)
        else:
            return Response({'visibility': ['public']}, status=status.HTTP_200_OK)


class LatestCheckIn(generics.RetrieveAPIView):
    """
    Get the most recent check-in of request user (regardless of is_active).
    Used to pre-fill the create check-in form.
    """
    serializer_class = cs.MyCheckInSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        latest = CheckIn.objects.filter(user=request.user).order_by('-created_at').first()
        if latest:
            serializer = self.get_serializer(latest)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response({}, status=status.HTTP_200_OK)


class CurrentSong(generics.ListCreateAPIView):
    """
    Get current active song of request user or create a new song.
    """
    serializer_class = cs.MySongSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        current_user = self.request.user

        serializer.save(user=current_user, is_active=True)

        # deactivate previous song
        previous_song = Song.objects.filter(user=current_user, is_active=True) \
                                    .exclude(id=serializer.instance.id).first()
        if previous_song:
            previous_song.is_active = False
            previous_song.save()

        return Response(serializer.data)

    def get_queryset(self):
        current_user = self.request.user
        return Song.objects.filter(user=current_user, is_active=True)


class SongDetail(generics.RetrieveUpdateAPIView):
    """
    Get a specific song, or deactivate a song.
    """
    queryset = Song.objects.all()
    serializer_class = cs.MySongSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            song = Song.objects.get(id=self.kwargs.get('pk'))
        except Song.DoesNotExist:
            raise exceptions.NotFound("Song not found.")
        if not song.is_active:
            raise exceptions.PermissionDenied("This song has been edited or deleted.")
        if self.request.user != song.user:
            raise exceptions.PermissionDenied("Only the author can access song details.")
        return song

    def patch(self, request, *args, **kwargs):
        '''
        Used when user deletes a song, which makes the is_active field of song False.
        '''
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)
