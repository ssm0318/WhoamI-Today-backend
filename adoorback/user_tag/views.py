from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.db.models import Case, Value, When, IntegerField

from account.serializers import UserFriendshipStatusSerializer

from adoorback.utils.validators import adoor_exception_handler

User = get_user_model()


class UserTagSearch(generics.ListAPIView):
    """
    List friends to tag
    """
    serializer_class = UserFriendshipStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        username = self.request.GET.get('query')
        user = self.request.user
        qs = User.objects.none()
        if username:
            qs_ids = list(user.friends.filter(
                username__startswith=username).order_by('username')[:10].values_list('id', flat=True))
            if len(qs_ids) < 10:
                contain_ids = list(user.friends.filter(
                        username__icontains=username).order_by('username').values_list('id', flat=True))
                for id_ in contain_ids:
                    if id_ not in qs_ids:
                        qs_ids.append(id_)
            # merge querysets while preserving order
            cases = [When(id=x, then=Value(i)) for i,x in enumerate(qs_ids)]
            case = Case(*cases, output_field=IntegerField())
            qs = User.objects.filter(id__in=qs_ids).annotate(my_order=case).order_by('my_order')

        return qs
