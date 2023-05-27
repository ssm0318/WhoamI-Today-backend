from django.urls import path
from moment import views

urlpatterns = [
    path('today/', views.MomentToday.as_view(), name='moment-today'),
    path('monthly/<int:year>/<int:month>/', views.MomentMonthly.as_view(), name='moment-monthly'),
    path('<int:pk>/<str:field>', views.MomentDelete.as_view(), name='moment-delete')
]
