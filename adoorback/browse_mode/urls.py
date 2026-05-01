from django.urls import path

from browse_mode import views

urlpatterns = [
    path('presets/', views.BrowseModePresetList.as_view(), name='browse-mode-preset-list'),
    path(
        'presets/<int:pk>/',
        views.BrowseModePresetDetail.as_view(),
        name='browse-mode-preset-detail',
    ),
    path(
        'presets/<int:pk>/used/',
        views.BrowseModePresetMarkUsed.as_view(),
        name='browse-mode-preset-mark-used',
    ),
    path(
        'wishlist/',
        views.BrowseModeWishlistCreate.as_view(),
        name='browse-mode-wishlist-create',
    ),
]
