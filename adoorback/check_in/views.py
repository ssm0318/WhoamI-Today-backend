from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from adoorback.utils.validators import adoor_exception_handler

from check_in.models import CheckIn, Song, Poke
from reaction.models import Reaction
from reaction.serializers import ReactionSerializer
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

        # Check if there's an active check-in
        existing_checkin = CheckIn.objects.filter(
            user=current_user,
            is_active=True
        ).first()

        if existing_checkin:
            # Update existing check-in
            for field, value in serializer.validated_data.items():
                setattr(existing_checkin, field, value)
            existing_checkin.save()
            serializer.instance = existing_checkin
        else:
            # Create new check-in
            serializer.save(user=current_user, is_active=True)

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

        # Mirror the song change to the active check-in's song_updated_at so the
        # auto-archive logic (>12h) doesn't hide the just-saved song. Use update()
        # to bypass CheckIn.save()'s per-field timestamp logic.
        CheckIn.objects.filter(user=current_user, is_active=True) \
                       .update(song_updated_at=timezone.now())

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

        # Mirror the song removal to the active check-in's song_updated_at so the
        # auto-archive logic stays consistent with the song state.
        CheckIn.objects.filter(user=request.user, is_active=True) \
                       .update(song_updated_at=timezone.now())

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PokeCreate(generics.CreateAPIView):
    """
    Create a poke (ping) to ask a friend to share a component.
    POST body: { receiver_id, component_type }
    """
    serializer_class = cs.PokeSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        sender = self.request.user
        receiver_id = serializer.validated_data.pop('receiver_id')
        receiver = get_object_or_404(User, id=receiver_id)

        if sender == receiver:
            raise exceptions.ValidationError("You cannot poke yourself.")

        # Check daily poke limit
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = Poke.objects.filter(sender=sender, created_at__gte=today_start).count()
        if sent_today >= Poke.DAILY_POKE_LIMIT:
            raise exceptions.Throttled(detail="Daily poke limit reached.")

        # Check duplicate: same sender->receiver->component_type today
        component_type = serializer.validated_data.get('component_type')
        already_poked = Poke.objects.filter(
            sender=sender,
            receiver=receiver,
            component_type=component_type,
            created_at__gte=today_start,
        ).exists()
        if already_poked:
            raise exceptions.ValidationError("You already poked this component today.")

        serializer.save(sender=sender, receiver=receiver)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PokeSent(generics.ListAPIView):
    """
    Get pokes sent by the current user to a specific receiver today.
    GET /poke/sent/?receiver_id=X
    """
    serializer_class = cs.PokeSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        sender = self.request.user
        receiver_id = self.request.query_params.get('receiver_id')
        if not receiver_id:
            raise exceptions.ValidationError("receiver_id query parameter is required.")
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return Poke.objects.filter(
            sender=sender,
            receiver_id=receiver_id,
            created_at__gte=today_start,
        )


class PokeDelete(generics.DestroyAPIView):
    """
    Delete (un-poke) a specific poke. Only the sender can delete their own poke.
    DELETE /poke/<id>/
    """
    serializer_class = cs.PokeSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            poke = Poke.objects.get(id=self.kwargs.get('pk'))
        except Poke.DoesNotExist:
            raise exceptions.NotFound("Poke not found.")
        if self.request.user != poke.sender:
            raise exceptions.PermissionDenied("Only the sender can delete a poke.")
        return poke


class CheckInReact(APIView):
    """
    POST /api/check_in/<id>/react/
    Toggle a reaction on a check-in.
    Body: { "emoji": "..." }
    If the same user+emoji+checkin combo exists, delete it (toggle off).
    Otherwise create it.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def post(self, request, pk):
        try:
            check_in = CheckIn.objects.get(id=pk)
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")

        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in is no longer active.")

        emoji = request.data.get('emoji')
        if not emoji:
            raise exceptions.ValidationError("emoji is required.")

        content_type = ContentType.objects.get_for_model(CheckIn)

        existing = Reaction.objects.filter(
            user=request.user,
            emoji=emoji,
            content_type=content_type,
            object_id=pk,
        ).first()

        if existing:
            # Delete associated notifications before removing the reaction
            reaction_ct = ContentType.objects.get_for_model(type(existing))
            from notification.models import Notification
            Notification.objects.filter(
                target_type=reaction_ct,
                target_id=existing.id,
            ).delete()
            existing.delete()
            return Response({'toggled': 'off'}, status=status.HTTP_200_OK)
        else:
            reaction = Reaction.objects.create(
                user=request.user,
                emoji=emoji,
                content_type=content_type,
                object_id=pk,
            )
            serializer = ReactionSerializer(reaction, context={'request': request})
            return Response({**serializer.data, 'toggled': 'on'}, status=status.HTTP_201_CREATED)


class CheckInReactions(generics.ListAPIView):
    """
    GET /api/check_in/<id>/reactions/
    List all reactions on a check-in.
    """
    serializer_class = ReactionSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        pk = self.kwargs.get('pk')
        try:
            check_in = CheckIn.objects.get(id=pk)
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")

        content_type = ContentType.objects.get_for_model(CheckIn)
        return Reaction.objects.filter(
            content_type=content_type,
            object_id=pk,
        ).order_by('-created_at')
