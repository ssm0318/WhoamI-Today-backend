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
                  'social_battery', 'description', 'current_user_read']


class MyCheckInSerializer(CheckInBaseSerializer):
    class Meta:
        model = CheckIn
        fields = CheckInBaseSerializer.Meta.fields


class TrackSerializer(serializers.Serializer):
    track_ids = serializers.ListField(child=serializers.CharField())
