"""
Company Management app configuration.
"""

from django.apps import AppConfig


class CompanyManagementConfig(AppConfig):
    """Configuration for the Company Management app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.company_management'
    verbose_name = 'Company Management'

    def ready(self):
        """
        Import signal handlers when the app is ready.
        """
        # Import signals here if needed in the future
        pass
