from django.urls import path
from moment import views

urlpatterns = [
    path('daily/<int:year>/<int:month>/<int:day>/', views.MomentToday.as_view(), name='moment-daily'),
    path('weekly/<int:year>/<int:month>/<int:day>/', views.MomentWeekly.as_view(), name='moment-weekly'),
    path('monthly/<int:year>/<int:month>/', views.MomentMonthly.as_view(), name='moment-monthly'),
    path('<int:pk>/<str:field>/', views.MomentDelete.as_view(), name='moment-delete'),
    path('comments/<int:pk>/', views.MomentComments.as_view(), name='moment-comments')
]
