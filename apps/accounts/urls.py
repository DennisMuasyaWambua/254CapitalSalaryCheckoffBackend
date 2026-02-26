"""
URL routing for authentication and profile endpoints.
"""

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # OTP authentication
    path('otp/send/', views.SendOTPView.as_view(), name='otp-send'),
    path('otp/verify/', views.VerifyOTPView.as_view(), name='otp-verify'),

    # Registration
    path('register/', views.RegisterEmployeeView.as_view(), name='register'),

    # JWT token management
    path('token/refresh/', views.TokenRefreshView.as_view(), name='token-refresh'),

    # HR and Admin login
    path('hr/login/', views.HRLoginView.as_view(), name='hr-login'),
    path('admin/login/', views.AdminLoginView.as_view(), name='admin-login'),
    path('admin/verify-2fa/', views.AdminVerify2FAView.as_view(), name='admin-verify-2fa'),

    # Profile management
    path('profile/', views.ProfileView.as_view(), name='profile'),
]
