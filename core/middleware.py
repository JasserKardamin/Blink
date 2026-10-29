from django.conf import settings
from django.shortcuts import render

# Préfixes dont les 404 ne doivent pas être remplacées par la page HTML (JSON, fichiers).
RAW_404_PREFIXES = ("/api/", "/static/", "/media/")


class FriendlyNotFoundMiddleware:
    """Affiche la page 404 de Blink même en mode DEBUG.

    En DEBUG, Django remplace templates/404.html par sa page technique jaune ;
    on garde ainsi une page « introuvable » unique, en développement comme en production.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            settings.DEBUG
            and response.status_code == 404
            and not request.path.startswith(RAW_404_PREFIXES)
        ):
            return render(request, "404.html", status=404)
        return response
