
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Subquery, Max, Count, Q, F
from rest_framework import generics, exceptions
from rest_framework.permissions import IsAuthenticated

from adoorback.utils.validators import adoor_exception_handler
from .models import Ping, PingRoom, PingRequest, get_or_create_ping_room, get_ping_room
from .serializers import PingSerializer, PingRoomSerializer, PingRequestSerializer, PingRequestUpdateSerializer

User = get_user_model()


class PingRoomList(generics.ListAPIView):
    serializer_class = PingRoomSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        
        # Subquery to get the latest ping for each room
        latest_ping_subquery = Ping.objects.filter(
            ping_room=OuterRef('pk')
        ).order_by('-created_at')

        return PingRoom.objects.filter(
            Q(user1=user) | Q(user2=user)
        ).annotate(
            last_ping_time=Subquery(latest_ping_subquery.values('created_at')[:1]),
            last_ping_content=Subquery(latest_ping_subquery.values('content')[:1]),
            last_ping_emoji=Subquery(latest_ping_subquery.values('emoji')[:1]),
            unread_cnt=Count(
                'pings',
                filter=Q(pings__receiver=user, pings__is_read=False)
            )
        ).filter(
            last_ping_time__isnull=False  # Only show rooms with messages
        ).order_by('-last_ping_time')



class PingList(generics.ListCreateAPIView):
    serializer_class = PingSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        ping_room = get_ping_room(connected_user, user)
        if not ping_room:
            self.oldest_unread_page = 1
            return []

        pings = list(ping_room.pings.all())  # to freeze the unread status

        oldest_unread = ping_room.pings.filter(receiver=user, is_read=False).order_by('id').first()

        if oldest_unread:
            oldest_position = Ping.objects.filter(ping_room=ping_room, id__gte=oldest_unread.id).count()
            pagination_size = getattr(settings, 'REST_FRAMEWORK', {}).get('PAGE_SIZE', 10)
            page_number = (oldest_position - 1) // pagination_size + 1
        else:
            page_number = 1
        self.oldest_unread_page = page_number

        return pings
    
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")
        response.data['username'] = connected_user.username

        response.data['oldest_unread_page'] = self.oldest_unread_page

        paginated_queryset = self.paginator.paginate_queryset(self.get_queryset(), request)
        if paginated_queryset:
            ping_ids = [ping.id for ping in paginated_queryset]
            Ping.objects.filter(id__in=ping_ids, receiver=request.user, is_read=False).update(is_read=True)

        return response

    def perform_create(self, serializer):
        user = self.request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        # Check if users can message each other
        if not user.is_connected(connected_user):
            # Non-friends need an accepted PingRequest
            ping_req = PingRequest.objects.filter(
                Q(requester=user, requestee=connected_user) |
                Q(requester=connected_user, requestee=user)
            ).first()

            if ping_req is None:
                # Auto-create a pending request with the first message
                PingRequest.objects.create(requester=user, requestee=connected_user)
            elif ping_req.accepted is False:
                raise exceptions.PermissionDenied("This chat request was declined.")
            elif ping_req.accepted is None and ping_req.requester != user:
                raise exceptions.PermissionDenied(
                    "You have a pending chat request from this user. Accept it first."
                )
            # If accepted=True or requester is sending additional messages while pending, allow

        ping_room = get_or_create_ping_room(user, connected_user)
        serializer.save(sender=user, receiver=connected_user, ping_room=ping_room)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        user = request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
            ping_room = get_or_create_ping_room(user, connected_user)

            unread_count = ping_room.pings.filter(receiver=user, is_read=False).count()
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        response.data['unread_count'] = unread_count
        return response


class PingRequestCreate(generics.ListCreateAPIView):
    """List received ping requests / Create a new ping request."""
    serializer_class = PingRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return PingRequest.objects.filter(
            requestee=self.request.user, accepted__isnull=True
        )

    def perform_create(self, serializer):
        user = self.request.user
        requestee_id = serializer.validated_data['requestee_id']
        requestee = User.objects.get(id=requestee_id)

        if user.is_connected(requestee):
            raise exceptions.ValidationError("You are already friends. No request needed.")

        existing = PingRequest.objects.filter(
            Q(requester=user, requestee=requestee) |
            Q(requester=requestee, requestee=user)
        ).first()
        if existing:
            raise exceptions.ValidationError("A ping request already exists between these users.")

        serializer.save(requester=user, requestee=requestee)


class PingRequestSentList(generics.ListAPIView):
    """List sent ping requests."""
    serializer_class = PingRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return PingRequest.objects.filter(requester=self.request.user)


class PingRequestUpdate(generics.UpdateAPIView):
    """Accept or decline a ping request."""
    serializer_class = PingRequestUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            return PingRequest.objects.get(
                id=self.kwargs.get('pk'),
                requestee=self.request.user
            )
        except PingRequest.DoesNotExist:
            raise exceptions.NotFound("Ping request not found.")
