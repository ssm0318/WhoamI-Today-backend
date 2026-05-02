from rest_framework import serializers

from mission.models import Mission


class MissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mission
        fields = ['id', 'slug', 'prompt_en', 'prompt_ko', 'type']
