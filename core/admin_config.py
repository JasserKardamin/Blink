from django.contrib.admin.apps import AdminConfig


class BlinkAdminConfig(AdminConfig):
    """Remplace le site d'administration par défaut par le dashboard Blink."""

    default_site = "core.admin_site.BlinkAdminSite"
