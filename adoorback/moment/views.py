from datetime import date

from django.shortcuts import render

from django.db import transaction
from django.db.models import Q

from rest_framework import generics, exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from adoorback.utils.validators import adoor_exception_handler

import moment.serializers as ms
from moment.models import Moment

class MomentToday(generics.ListCreateAPIView, generics.UpdateAPIView):
    """
    List today's moment of request user, create a new moment for today, or update today's moment.
    """
    serializer_class = ms.MyMomentSerializer
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler
    
    def get_queryset(self):
        current_user = self.request.user
        current_date = date.today().strftime('%Y-%m-%d')
        queryset = Moment.objects.filter(Q(author=current_user) & Q(date=current_date)).order_by('-id')
        return queryset
    
    def create(self, request, *args, **kwargs):
        existing_moments = self.get_queryset()
        if existing_moments.exists():
            return Response("A moment for today already exists.", status=status.HTTP_400_BAD_REQUEST)
        
        if not 'mood' in request.data and not 'description' in request.data and not 'photo' in request.data:
            return Response("No fields provided for create.", status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user, date=date.today().strftime('%Y-%m-%d'))
    
    def get_object(self):
        return self.get_queryset().first()
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        if not instance:
           return Response("There's no moment for today to update.", status=status.HTTP_400_BAD_REQUEST) 
        
        if instance.mood and 'mood' in request.data:
            return Response("Cannot update mood - already exists.", status=status.HTTP_400_BAD_REQUEST)
        
        if instance.description and 'description' in request.data:
            return Response("Cannot update description - already exists.", status=status.HTTP_400_BAD_REQUEST)
        
        if instance.photo and 'photo' in request.data:
            return Response("Cannot update photo - already exists.", status=status.HTTP_400_BAD_REQUEST)
            
        if not 'mood' in request.data and not 'description' in request.data and not 'photo' in request.data:
            return Response("No fields provided for update.", status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

class MomentMonthly(generics.ListAPIView):
    serializer_class = ms.MyMomentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        current_user = self.request.user
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        formatted_date = f"{year}-{month:02d}"
        print(formatted_date)
        
        queryset = Moment.objects.filter(Q(author=current_user) & Q(date__startswith=formatted_date)).order_by('date')
        return queryset
