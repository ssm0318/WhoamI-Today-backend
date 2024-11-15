from translate.models import TranslateResponse
from rest_framework import serializers

class TranslateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranslateResponse
        fields = '__all__'  
