from django.shortcuts import render

from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from .models import Category, Subscription
from .serializers import CategorySerializer, CategoryDetailSerializer, SubscriptionSerializer
from note.models import Note
from qna.models import Response
from note.serializers import NoteSerializer
from qna.serializers import ResponseSerializer


#create API views for Category, Subscription, and CategoryContentView
class CategoryListCreateView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [IsAuthenticated()]


class CategoryDetailView(generics.RetrieveAPIView):
    queryset = Category.objects.all()
    serializer_class = CategoryDetailSerializer
    permission_classes = [IsAuthenticated]


class SubscriptionListCreateView(generics.ListCreateAPIView):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)


class SubscriptionDestroyView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)


class CategoryContentView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        category_id = self.kwargs.get('category_id')
        content_type = self.kwargs.get('content_type')
        
        if content_type == 'response':
            return Response.objects.filter(category_id=category_id)
        elif content_type == 'note':
            return Note.objects.filter(category_id=category_id)
        
    def get_serializer_class(self):
        content_type = self.kwargs.get('content_type')
        if content_type == 'response':
            return ResponseSerializer
        elif content_type == 'note':
            return NoteSerializer