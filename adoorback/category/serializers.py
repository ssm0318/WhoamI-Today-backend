from rest_framework import serializers
from .models import Category, Subscription

class CategorySerializer(serializers.ModelSerializer):
    added_users_count = serializers.SerializerMethodField()
    
    def get_added_users_count(self, obj):
        return obj.added_users.count()

    class Meta:
        model = Category
        fields = ['id', 'name', 'sharing_scope', 'added_users_count']


class CategoryDetailSerializer(CategorySerializer):
    responses_count = serializers.SerializerMethodField()
    notes_count = serializers.SerializerMethodField()
    
    def get_responses_count(self, obj):
        return obj.responses.count()
    
    def get_notes_count(self, obj):
        return obj.notes.count()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ['added_users', 'responses_count', 'notes_count']


class SubscriptionSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Subscription
        fields = ['id', 'category', 'category_id', 'sharing_scope']

    def validate(self, attrs):
        user = self.context['request'].user
        category_id = attrs.get('category_id')
        
        if Subscription.objects.filter(
            user=user,
            category_id=category_id,
            deleted__isnull=True
        ).exists():
            raise serializers.ValidationError("You are already subscribed to this category")
            
        return attrs

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)