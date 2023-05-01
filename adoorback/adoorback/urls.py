"""adoorback URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.conf.urls import url
from django.views.static import serve
from django.conf.urls.i18n import i18n_patterns
from fcm_django.api.rest_framework import FCMDeviceAuthorizedViewSet


urlpatterns = i18n_patterns(
    path('api/content_reports/', include('content_report.urls')),
    path('api/user_reports/', include('user_report.urls')),
    path('api/user_tags/', include('user_tag.urls')),
    path('api/likes/', include('like.urls')),
    path('api/comments/', include('comment.urls')),
    path('api/notifications/', include('notification.urls')),
    path('api/feed/', include('feed.urls')),
    path('api/user/', include('account.urls')),
    path('api/admin/', include('admin_honeypot.urls', namespace='admin_honeypot')),
    path('api/secret/', admin.site.urls),
    path('api/user/', include('rest_framework.urls', namespace='rest_framework')),
    path('api/devices/', FCMDeviceAuthorizedViewSet.as_view({'post': 'create'}), name='create_fcm_device'),
    path('api/tracking/', include('tracking.urls')),
    prefix_default_language=False
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        url(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        url(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    ]
