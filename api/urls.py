# api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EmailAccountViewSet,
    EmailViewSet,
    ReservationViewSet,
    SyncLogViewSet,
    GoogleOAuthInitView,
    GoogleOAuthCallbackView,
)

router = DefaultRouter()
router.register(r'email-accounts', EmailAccountViewSet, basename='emailaccount')
router.register(r'emails', EmailViewSet, basename='email')
router.register(r'reservations', ReservationViewSet, basename='reservation')
router.register(r'sync-logs', SyncLogViewSet, basename='synclog')

urlpatterns = [
    path('', include(router.urls)),
    
    # Google OAuth
    path('auth/google/', GoogleOAuthInitView.as_view(), name='google-oauth-init'),
    path('auth/google/callback/', GoogleOAuthCallbackView.as_view(), name='google-oauth-callback'),
]