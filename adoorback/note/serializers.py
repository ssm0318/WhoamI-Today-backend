from itertools import chain
import json

from django.contrib.auth import get_user_model
from django.db.models import F, Value, CharField, BooleanField
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from adoorback.serializers import AdoorBaseSerializer
from adoorback.utils.content_types import get_generic_relation_type
from note.models import Note
from reaction.models import Reaction


User = get_user_model()


class BaseNoteSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedRelatedField(
        view_name='user-detail', read_only=True, lookup_field='username', lookup_url_kwarg='username'
    )
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    images = serializers.SerializerMethodField()
    current_user_read = serializers.SerializerMethodField(read_only=True)

    def get_current_user_read(self, obj):
        return self.context['request'].user.id in obj.reader_ids

    def get_images(self, obj):
        return [image.image.url for image in obj.images.all().order_by('created_at')]

    class Meta(AdoorBaseSerializer.Meta):
        model = Note
        fields = AdoorBaseSerializer.Meta.fields + ['author', 'author_detail', 'images', 'current_user_read', 'is_edited']


class VisibilityField(serializers.MultipleChoiceField):
    def to_internal_value(self, data):
        # Case: single item list from form-data (e.g., ['["friends"]'])
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], str):
            if data[0].strip().startswith('['):
                data = data[0]

        if isinstance(data, str):
            data = data.strip()
            if data.startswith('[') and data.endswith(']'):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    content = data[1:-1].strip()
                    if not content:
                        data = []
                    else:
                        data = [v.strip().strip('"').strip("'") for v in content.split(',') if v.strip()]
            elif ',' in data:
                data = [v.strip() for v in data.split(',') if v.strip()]
            
            if isinstance(data, str):
                data = [data]

        # MultipleChoiceField returns a set, but we need a list for ArrayField
        return list(super().to_internal_value(data))


class NoteSerializer(BaseNoteSerializer):
    current_user_reaction_id_list = serializers.SerializerMethodField(read_only=True)
    like_reaction_user_sample = serializers.SerializerMethodField(read_only=True)
    visibility = VisibilityField(choices=['only_me', 'close_friends', 'friends', 'public'], required=True)
    share_type = serializers.CharField(required=False, default='regular')

    def validate_visibility(self, value):
        if len(value) != 1:
            raise serializers.ValidationError("Please select exactly one visibility option.")
        return list(value)

    def get_current_user_reaction_id_list(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        reactions = Reaction.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return [{"id": reaction.id, "emoji": reaction.emoji} for reaction in reactions]

    def get_like_reaction_user_sample(self, obj):
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
        
        return [
            {**UserMinimalSerializer(User.objects.get(id=item['user']), context=self.context).data, 
             'like': item['like'], 'reaction': item['reaction']} 
            for item in combined
        ]

    class Meta(BaseNoteSerializer.Meta):
        fields = BaseNoteSerializer.Meta.fields + ['current_user_reaction_id_list', 'like_reaction_user_sample', 'visibility', 'share_type']


class DefaultFriendNoteSerializer(BaseNoteSerializer):
    '''
    Friend Note Serializer for default ver.
    1) includes like count even when viewing others' notes
    2) excludes reactions
    '''
    like_count = serializers.SerializerMethodField(read_only=True)
    like_user_sample = serializers.SerializerMethodField(read_only=True)
    visibility = VisibilityField(choices=['only_me', 'close_friends', 'friends', 'public'], required=True)

    def validate_visibility(self, value):
        if len(value) != 1:
            raise serializers.ValidationError("Please select exactly one visibility option.")
        return list(value)

    def get_like_count(self, obj):
        return obj.liked_user_ids.count()

    def get_like_user_sample(self, obj):
        recent_likes = obj.note_likes.order_by('-created_at')[:3]
        recent_users = [like.user for like in recent_likes]
        return UserMinimalSerializer(recent_users, many=True, context=self.context).data

    class Meta(BaseNoteSerializer.Meta):
        fields = BaseNoteSerializer.Meta.fields + ['like_count', 'like_user_sample', 'visibility', 'share_type']
