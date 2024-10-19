from django.urls import path
from qna import views

urlpatterns = [
    # Response related
    path('responses/', views.ResponseCreate.as_view(), name='response-list'),
    path('responses/<int:pk>/', views.ResponseDetail.as_view(), name='response-detail'),
    path('responses/<int:pk>/comments/', views.ResponseComments.as_view(), name='response-comments'),
    path('responses/<int:pk>/interactions/', views.ResponseInteractions.as_view(), name='response-interaction-user-list'),
    path('responses/read/', views.ResponseRead.as_view(), name='response-read'),

    # Question related
    path('questions/daily/', views.DailyQuestionList.as_view(), name='daily-question-list'),
    path('questions/', views.QuestionList.as_view(), name='question-list'),

    # Question Detail Page related
    path('questions/<int:pk>/', views.QuestionDetail.as_view(), name='question-detail'),

    # Response Request related
    path('questions/response-request/', views.ResponseRequestCreate.as_view(),
         name='response-request-create'),
]
