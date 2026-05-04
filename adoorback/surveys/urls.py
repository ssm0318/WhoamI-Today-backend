from django.urls import path

from surveys.views import (
    MyResponseView, PastSurveysView, SurveyDetailView, SurveyIndexView,
    SurveyOfTheDayView, SurveyResponseSubmitView, SurveyResultsView,
)

urlpatterns = [
    path('today/', SurveyOfTheDayView.as_view(), name='survey-today'),
    path('index/', SurveyIndexView.as_view(), name='survey-index'),
    path('past/', PastSurveysView.as_view(), name='survey-past'),
    path('<slug:slug>/', SurveyDetailView.as_view(), name='survey-detail'),
    path('<slug:slug>/responses/', SurveyResponseSubmitView.as_view(), name='survey-submit'),
    path('<slug:slug>/my_response/', MyResponseView.as_view(), name='survey-my-response'),
    path('<slug:slug>/results/', SurveyResultsView.as_view(), name='survey-results'),
]
