from rest_framework import serializers
from django.contrib.auth import get_user_model

from reaction.models import Reaction
from adoorback.serializers import AdoorBaseSerializer
from account.serializers import AuthorFriendSerializer

User = get_user_model()

class ReactionBaseSerializer(serializers.ModelSerializer):
    class Meta(AdoorBaseSerializer.Meta):
        model = Reaction
        fields = ['id', 'emoji']


class ReactionMineSerializer(ReactionBaseSerializer):
    is_mine = serializers.SerializerMethodField(read_only=True)

    def get_is_mine(self, obj):
        return obj.user == self.context.get('request', None).user

    class Meta(ReactionBaseSerializer.Meta):
        fields = ReactionBaseSerializer.Meta.fields + ['is_mine']


class ReactionSerializer(ReactionBaseSerializer):
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        user = obj.user
        return AuthorFriendSerializer(user).data


    class Meta(AdoorBaseSerializer.Meta):
        model = Reaction
        fields = ReactionBaseSerializer.Meta.fields + ['user']
