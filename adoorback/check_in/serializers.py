from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from check_in.models import CheckIn, Song


class CheckInBaseSerializer(serializers.ModelSerializer):
    current_user_read = serializers.SerializerMethodField(read_only=True)

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    class Meta:
        model = CheckIn
        fields = ['id', 'created_at', 'is_active', 'mood',
                  'social_battery', 'description', 'current_user_read', 'visibility']


class MyCheckInSerializer(CheckInBaseSerializer):
    class Meta:
        model = CheckIn
        fields = CheckInBaseSerializer.Meta.fields
        extra_kwargs = {
            'visibility': {'required': False}
        }

    def validate_visibility(self, value):
        if len(value) == 0:
            return value
        if len(value) != 1:
            raise serializers.ValidationError("Please select exactly one visibility option.")
        return value


class SongBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Song
        fields = ['id', 'created_at', 'is_active', 'track_id']


class MySongSerializer(SongBaseSerializer):
    class Meta:
        model = Song
        fields = SongBaseSerializer.Meta.fields


class TrackSerializer(serializers.Serializer):
    track_ids = serializers.ListField(child=serializers.CharField())
