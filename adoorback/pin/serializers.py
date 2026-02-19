from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from adoorback.utils.content_types import get_generic_relation_type
from pin.models import Pin
from rest_framework import serializers
from note.serializers import NoteSerializer
from qna.serializers import ResponseSerializer

User = get_user_model()

class PinSerializer(serializers.ModelSerializer):
    user = serializers.HyperlinkedRelatedField(
        view_name='user-detail', read_only=True, lookup_field='username', lookup_url_kwarg='username'
    )
    content_object = serializers.SerializerMethodField(read_only=True)
    
    def get_content_object(self, obj):
        context = self.context
        if obj.content_type.model == 'note':
            return NoteSerializer(obj.content_object, context=context).data
        elif obj.content_type.model == 'response':
            return ResponseSerializer(obj.content_object, context=context).data
        return None

    class Meta:
        model = Pin
        fields = ['id', 'user', 'content_object', 'created_at']
        read_only_fields = ['id', 'user', 'content_object', 'created_at']

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        target_type_str = self.context['request'].data.get('content_type')
        target_id = self.context['request'].data.get('object_id')
        
        content_type = get_generic_relation_type(target_type_str)
        if not content_type:
            raise serializers.ValidationError({"detail": _("유효하지 않은 content_type입니다."), "code": "invalid_content_type"})

        model_class = content_type.model_class()
        try:
            target_obj = model_class.objects.get(id=target_id)
        except model_class.DoesNotExist:
            raise serializers.ValidationError({"detail": _("고정하려는 게시물이 존재하지 않거나 삭제되었습니다."), "code": "object_not_found"})

        if hasattr(target_obj, 'deleted') and target_obj.deleted:
            raise serializers.ValidationError({"detail": _("삭제된 게시물은 고정할 수 없습니다."), "code": "cannot_pin_deleted"})

        validated_data['user'] = user
        validated_data['content_type'] = content_type
        validated_data['object_id'] = target_id
        
        return super().create(validated_data)
