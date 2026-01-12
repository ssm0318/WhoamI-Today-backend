from rest_framework import serializers
from django.contrib.auth import get_user_model

from adoorback.utils.content_types import get_generic_relation_type
from pin.models import Pin
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

    def create(self, validated_data):
        user = self.context['request'].user
        target_type = self.context['request'].data.get('content_type')
        target_id = self.context['request'].data.get('object_id')
        
        content_type = get_generic_relation_type(target_type)
        validated_data['user'] = user
        validated_data['content_type'] = content_type
        validated_data['object_id'] = target_id
        
        return super().create(validated_data)
