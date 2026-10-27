from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User


class EmailOrUsernameBackend(ModelBackend):
    """Permet de se connecter avec son e-mail ou son nom d'utilisateur."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
        if user is None:
            User().set_password(password)  # temps constant contre l'énumération de comptes
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
