from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from check_in.models import CheckIn


class CheckInBaseSerializer(serializers.ModelSerializer):
    current_user_read = serializers.SerializerMethodField(read_only=True)

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids
    
    class Meta:
        model = CheckIn
        fields = ['id', 'created_at', 'is_active', 'mood', 'track_id',
                  'availability', 'description', 'current_user_read']


class MyCheckInSerializer(CheckInBaseSerializer):
    class Meta:
        model = CheckIn
        fields = CheckInBaseSerializer.Meta.fields + ['share_everyone', 'share_groups', 'share_friends']


class CheckInDetailSerializer(MyCheckInSerializer):
    user = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='user', lookup_url_kwarg='username')
    user_detail = UserMinimalSerializer(source='user', read_only=True)

    class Meta:
        model = CheckIn
        fields = MyCheckInSerializer.Meta.fields + ['user', 'user_detail']


class TrackSerializer(serializers.Serializer):
    track_ids = serializers.ListField(child=serializers.CharField())
