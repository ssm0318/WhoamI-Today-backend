from rest_framework import serializers

from account.serializers import CurrentUserSerializer, UserProfileSerializer


class QCurrentUserSerializer(CurrentUserSerializer):
    """
    CurrentUser serializer for Version Q.
    - No chips_by_category, no custom_chips (Q uses flat interest/persona lists)
    - No per-item *_visibility flags (Q uses account-level is_public)
    """
    class Meta(CurrentUserSerializer.Meta):
        fields = [f for f in CurrentUserSerializer.Meta.fields
                  if f not in ('chips_by_category', 'custom_chips')
                  and not f.endswith('_visibility')]


class QUserProfileSerializer(UserProfileSerializer):
    """
    UserProfile serializer for Version Q.
    - No chip-related fields
    - Uses account-level is_public instead of per-item *_visibility
    """
    class Meta(UserProfileSerializer.Meta):
        fields = [f for f in UserProfileSerializer.Meta.fields
                  if f not in ('mutual_interests', 'mutual_personas', 'friendship_level')]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        user = self._get_viewer()
        view_as = self.context.get('view_as')

        can_see_private = False
        if user is not None:
            request = self.context.get('request')
            actual_requester = request.user if request else None
            if (view_as is not None and actual_requester == instance
                    and self.context.get('shadow_viewer') is None):
                can_see_private = view_as in ('friends', 'close_friends')
            elif user == instance or user.is_connected(instance):
                can_see_private = True

        if not can_see_private:
            # Q ignores per-field visibility — undo any masking the W parent applied.
            ret['name'] = instance.name
            if instance.is_public:
                ret['pronouns'] = instance.pronouns
                ret['bio'] = instance.bio
                ret['user_interests'] = [str(i) for i in instance.user_interests.all()]
                ret['user_personas'] = [str(p) for p in instance.user_personas.all()]
            else:
                ret['pronouns'] = None
                ret['bio'] = None
                ret['user_interests'] = []
                ret['user_personas'] = []

        return ret
