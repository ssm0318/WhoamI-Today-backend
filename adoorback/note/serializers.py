from itertools import chain
import json

from django.contrib.auth import get_user_model
from django.db.models import F, Value, CharField, BooleanField
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from adoorback.models import Mission
from adoorback.serializers import AdoorBaseSerializer
from adoorback.utils.content_types import get_generic_relation_type
from note.models import Note, ShareType
from reaction.models import Reaction


User = get_user_model()


MAX_MISSION_ATTEMPTS_PER_DAY = 5


class BaseNoteSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedRelatedField(
        view_name='user-detail', read_only=True, lookup_field='username', lookup_url_kwarg='username'
    )
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    images = serializers.SerializerMethodField()
    video = serializers.SerializerMethodField()
    current_user_read = serializers.SerializerMethodField(read_only=True)

    def get_current_user_read(self, obj):
        return self.context['request'].user.id in obj.reader_ids

    def get_images(self, obj):
        return [image.image.url for image in obj.images.all().order_by('created_at')]

    def get_video(self, obj):
        try:
            note_video = obj.videos.first()
        except Exception:
            return None
        if note_video:
            try:
                video_url = note_video.video.url if note_video.video else None
            except Exception:
                video_url = None
            try:
                thumbnail_url = note_video.thumbnail.url if note_video.thumbnail else None
            except Exception:
                thumbnail_url = None
            if video_url:
                return {
                    'url': video_url,
                    'thumbnail_url': thumbnail_url,
                    'duration_seconds': note_video.duration_seconds,
                }
        return None

    class Meta(AdoorBaseSerializer.Meta):
        model = Note
        fields = AdoorBaseSerializer.Meta.fields + ['author', 'author_detail', 'images', 'video', 'current_user_read', 'is_edited']


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
    content = serializers.CharField(required=False, allow_blank=True, default='')
    mission_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    mission_prompt = serializers.CharField(read_only=True)
    mission_attempt_number = serializers.IntegerField(read_only=True)

    def validate_visibility(self, value):
        if len(value) != 1:
            raise serializers.ValidationError("Please select exactly one visibility option.")
        return list(value)

    def validate(self, attrs):
        if self.instance is not None:
            return attrs

        share_type = attrs.get('share_type') or ShareType.REGULAR
        content = (attrs.get('content') or '').strip()
        request = self.context.get('request')
        has_images = bool(request.FILES.getlist('images')) if request else False
        has_video = bool(request.FILES.get('video')) if request else False

        if share_type == ShareType.PHOTO_OF_THE_DAY:
            if not has_images:
                raise serializers.ValidationError({'images': 'Photo of the Day는 이미지가 필요합니다.'})
        elif share_type == ShareType.MISSION:
            mission_id = attrs.get('mission_id')
            if not mission_id:
                raise serializers.ValidationError({'mission_id': 'Mission posts require a mission_id.'})
            try:
                Mission.objects.get(id=mission_id)
            except Mission.DoesNotExist:
                raise serializers.ValidationError({'mission_id': 'Mission not found.'})
            if request and request.user.is_authenticated:
                from adoorback.views import count_mission_attempts_today
                if count_mission_attempts_today(request.user) >= MAX_MISSION_ATTEMPTS_PER_DAY:
                    raise serializers.ValidationError(
                        {'detail': 'No mission attempts remaining today.'}
                    )
            if not content and not has_images and not has_video:
                raise serializers.ValidationError('텍스트, 이미지, 또는 동영상 중 하나 이상을 포함해야 합니다.')
        else:
            if not content and not has_images and not has_video:
                raise serializers.ValidationError('텍스트, 이미지, 또는 동영상 중 하나 이상을 포함해야 합니다.')

        return attrs

    def create(self, validated_data):
        mission_id = validated_data.pop('mission_id', None)
        if validated_data.get('share_type') == ShareType.MISSION and mission_id is not None:
            mission = Mission.objects.get(id=mission_id)
            validated_data['mission_prompt'] = mission.prompt
            request = self.context.get('request')
            existing = 0
            if request and request.user.is_authenticated:
                from adoorback.views import count_mission_attempts_today
                existing = count_mission_attempts_today(request.user)
            validated_data['mission_attempt_number'] = existing + 1
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Mission fields and share_type are immutable — strip any incoming attempts
        # to change them. Edits only mutate content/images/visibility.
        validated_data.pop('share_type', None)
        validated_data.pop('mission_id', None)
        validated_data.pop('mission_prompt', None)
        validated_data.pop('mission_attempt_number', None)
        return super().update(instance, validated_data)

    def get_current_user_reaction_id_list(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        reactions = Reaction.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return [{"id": reaction.id, "emoji": reaction.emoji} for reaction in reactions]

    def get_like_reaction_user_sample(self, obj):
        blocked_ids = self.context['request'].user.user_report_blocked_ids
        likes = obj.note_likes.exclude(user_id__in=blocked_ids).annotate(
            created=F('created_at'),
            like=Value(True, output_field=BooleanField()),
            reaction=Value(None, output_field=CharField())
        ).values('user', 'created', 'like', 'reaction')

        reactions = obj.reactions.exclude(user_id__in=blocked_ids).annotate(
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
        fields = BaseNoteSerializer.Meta.fields + [
            'current_user_reaction_id_list',
            'like_reaction_user_sample',
            'visibility',
            'share_type',
            'mission_id',
            'mission_prompt',
            'mission_attempt_number',
        ]


