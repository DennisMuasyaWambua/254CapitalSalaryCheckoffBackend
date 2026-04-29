"""
URL routing for authentication and profile endpoints.
"""

from django.urls import path
from . import views
from . import hr_views

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
    path('verify-login-otp/', views.VerifyLoginOTPView.as_view(), name='verify-login-otp'),
    path('admin/verify-2fa/', views.AdminVerify2FAView.as_view(), name='admin-verify-2fa'),  # Deprecated

    # Profile management
    path('profile/', views.ProfileView.as_view(), name='profile'),

    # Password reset (legacy email-based)
    path('password-reset/request/', views.RequestPasswordResetView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', views.ResetPasswordView.as_view(), name='password-reset-confirm'),

    # New password management endpoints
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('request-password-reset/', views.RequestPasswordResetOTPView.as_view(), name='request-password-reset-otp'),
    path('reset-password/', views.ResetPasswordWithOTPView.as_view(), name='reset-password-otp'),
    path('admin/reset-user-password/', views.AdminResetUserPasswordView.as_view(), name='admin-reset-user-password'),

    # HR User Management (Admin only)
    path('users/hr/', hr_views.ListHRUsersView.as_view(), name='list-hr-users'),
    path('users/hr/create/', hr_views.CreateHRUserView.as_view(), name='create-hr-user'),
    path('users/hr/<uuid:user_id>/', hr_views.HRUserDetailView.as_view(), name='hr-user-detail'),
    path('users/hr/<uuid:user_id>/update/', hr_views.UpdateHRUserView.as_view(), name='update-hr-user'),
    path('users/hr/<uuid:user_id>/toggle-active/', hr_views.ToggleHRUserActiveView.as_view(), name='toggle-hr-user-active'),
    path('users/hr/<uuid:user_id>/delete/', hr_views.DeleteHRUserView.as_view(), name='delete-hr-user'),
]
