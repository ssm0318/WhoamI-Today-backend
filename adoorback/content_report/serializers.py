from rest_framework import serializers

from content_report.models import ContentReport


class ContentReportSerializer(serializers.ModelSerializer):
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    def get_target_type(self, obj):
        return obj.target.type

    def get_target_id(self, obj):
        return obj.object_id

    class Meta:
        model = ContentReport
        fields = ['target_type', 'target_id']
