from rest_framework import serializers

from account.serializers import CurrentUserSerializer, UserProfileSerializer


class QCurrentUserSerializer(CurrentUserSerializer):
    """
    CurrentUser serializer for Version Q.
    - No chips_by_category, no custom_chips (Q uses flat interest/persona lists)
    """
    class Meta(CurrentUserSerializer.Meta):
        fields = [f for f in CurrentUserSerializer.Meta.fields
                  if f not in ('chips_by_category', 'custom_chips')]


class QUserProfileSerializer(UserProfileSerializer):
    """
    UserProfile serializer for Version Q.
    - No chip-related fields
    - All other fields (privacy, friendship, check-in) remain the same
    """
    class Meta(UserProfileSerializer.Meta):
        fields = [f for f in UserProfileSerializer.Meta.fields
                  if f not in ('mutual_interests', 'mutual_personas', 'friendship_level')]
