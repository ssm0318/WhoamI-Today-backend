from rest_framework import serializers

from moment.models import Moment
from account.serializers import AuthorFriendSerializer
from comment.serializers import CommentFriendSerializer, CommentResponsiveSerializer, CommentAnonymousSerializer


class MyMomentSerializer(serializers.ModelSerializer):
    like_count = serializers.SerializerMethodField(read_only=True)
    current_user_liked = serializers.SerializerMethodField(read_only=True)

    def get_like_count(self, obj):
        current_user = self.context['request'].user
        if obj.author != current_user:
            return None
        return obj.liked_user_ids.count()

    def get_current_user_liked(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.liked_user_ids
    
    class Meta:
        model = Moment
        fields = ['id', 'type', 'like_count', 'current_user_liked', 'created_at', 
                  'date', 'mood', 'photo', 'description']

