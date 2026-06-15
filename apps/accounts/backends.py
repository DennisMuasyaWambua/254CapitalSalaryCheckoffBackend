"""
Custom authentication backends for the 254 Capital system.
"""

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows users to authenticate
    using either their username or email address.

    This is particularly useful for HR managers and admins who use
    email/password login instead of phone/OTP.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate using username or email.

        Args:
            request: The HTTP request
            username: Can be either username or email
            password: User's password
            **kwargs: Additional keyword arguments

        Returns:
            User instance if authentication succeeds, None otherwise
        """
        if username is None or password is None:
            return None

        try:
            candidates = User.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            )

            # Prefer exact email match, then exact username match
            user = (
                candidates.filter(email__iexact=username).first()
                or candidates.filter(username__iexact=username).first()
            )

            if user is None:
                User().set_password(password)
                return None

            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        except Exception:
            User().set_password(password)

        return None
