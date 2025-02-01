from itertools import chain

from django.contrib.auth import get_user_model
from django.db.models import F, Value, CharField, BooleanField
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from adoorback.serializers import AdoorBaseSerializer
from adoorback.utils.content_types import get_generic_relation_type
from note.models import Note
from reaction.models import Reaction


User = get_user_model()


class NoteSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    images = serializers.SerializerMethodField()
    current_user_read = serializers.SerializerMethodField(read_only=True)
    current_user_reaction_id_list = serializers.SerializerMethodField(read_only=True)
    like_reaction_user_sample = serializers.SerializerMethodField(read_only=True)
    visibility = serializers.ChoiceField(
        choices=['friends', 'close_friends'],
        required=True
    )

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    def get_images(self, obj):
        images = obj.images.all().order_by('created_at')
        return [image.image.url for image in images]
    
    def get_current_user_reaction_id_list(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        reactions = Reaction.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return [{"id": reaction.id, "emoji": reaction.emoji} for reaction in reactions]

    def get_like_reaction_user_sample(self, obj):
        from account.serializers import UserMinimalSerializer

        likes = obj.note_likes.annotate(
            created=F('created_at'),
            like=Value(True, output_field=BooleanField()),
            reaction=Value(None, output_field=CharField())
        ).values('user', 'created', 'like', 'reaction')

        reactions = obj.reactions.annotate(
            created=F('created_at'),
            like=Value(False, output_field=BooleanField()),
            reaction=F('emoji')
        ).values('user', 'created', 'like', 'reaction')

        combined = sorted(
            chain(likes, reactions),
            key=lambda x: x['created'],
            reverse=True
        )[:3]

        serialized_data = []
        for reaction in combined:
            user = User.objects.get(id=reaction['user'])
            user_data = UserMinimalSerializer(user, context=self.context).data
            user_data['like'] = reaction['like']
            user_data['reaction'] = reaction['reaction']
            serialized_data.append(user_data)

        return serialized_data

    class Meta(AdoorBaseSerializer.Meta):
        model = Note
        fields = AdoorBaseSerializer.Meta.fields + ['author', 'author_detail', 'images', 'current_user_like_id', 
                                                    'current_user_read', 'like_reaction_user_sample', 'current_user_reaction_id_list', 'is_edited', 'visibility']


class DefaultFriendNoteSerializer(AdoorBaseSerializer):
    '''
    Friend Note Serializer for default ver.
    1) includes like count even when viewing others' notes
    2) excludes reactions
    '''
    like_count = serializers.SerializerMethodField(read_only=True)
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    images = serializers.SerializerMethodField()
    current_user_read = serializers.SerializerMethodField(read_only=True)
    like_user_sample = serializers.SerializerMethodField(read_only=True)

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    def get_images(self, obj):
        images = obj.images.all().order_by('created_at')
        return [image.image.url for image in images]
    
    def get_like_user_sample(self, obj):
        from account.serializers import UserMinimalSerializer
        recent_likes = obj.note_likes.order_by('-created_at')[:3]
        recent_users = [like.user for like in recent_likes]
        return UserMinimalSerializer(recent_users, many=True, context=self.context).data
    
    def get_like_count(self, obj):
        return obj.liked_user_ids.count()

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)

    class Meta(AdoorBaseSerializer.Meta):
        model = Note
        fields = AdoorBaseSerializer.Meta.fields + ['author', 'author_detail', 'images', 'current_user_like_id', 
                                                    'current_user_read', 'like_user_sample', 'is_edited']
