from django.urls import path
from qna import views

urlpatterns = [
    # Response related
    path('responses/', views.ResponseCreate.as_view(), name='response-list'),
    path('responses/<int:pk>/', views.ResponseDetail.as_view(), name='response-detail'),
    path('responses/<int:pk>/comments/', views.ResponseComments.as_view(), name='response-comments'),
    path('responses/<int:pk>/likes/', views.ResponseLikes.as_view(), name='response-like-user-list'),
    path('responses/read', views.ResponseRead.as_view(), name='response-read'),

    # Question related
    path('questions/daily/', views.DailyQuestionList.as_view(), name='daily-question-list'),
    path('questions/daily/<int:year>/<int:month>/<int:day>/', views.DateQuestionList.as_view(), name='date-question-list'),
    path('questions/daily/recommended/',
         views.RecommendedQuestionList.as_view(), name='recommended-question-list'),
    path('questions/', views.QuestionList.as_view(), name='question-list'),
    path('questions/<int:pk>/responses/', views.QuestionResponseList.as_view(), name='question-response-list'),

    # Question Detail Page related
    path('questions/<int:pk>/', views.QuestionDetail.as_view(), name='question-detail'),

    # Response Request related
    path('questions/response-request/', views.ResponseRequestCreate.as_view(),
         name='response-request-create'),
    path('questions/<int:qid>/response-request/', views.ResponseRequestList.as_view(),
         name='response-request-list'),
    path('questions/<int:qid>/response-request/<int:rid>/', views.ResponseRequestDestroy.as_view(),
         name='response-request-destroy'),
]
