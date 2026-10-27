from django.core.management.base import BaseCommand

from accounts.models import User
from faces.services import encode_user


class Command(BaseCommand):
    help = "Calcule l'empreinte faciale de tous les utilisateurs ayant une photo de profil."

    def handle(self, *args, **options):
        done = 0
        for user in User.objects.exclude(photo_profil=""):
            if encode_user(user):
                done += 1
                self.stdout.write(f"✓ {user}")
            else:
                self.stdout.write(self.style.WARNING(f"– {user} : aucun visage détecté"))
        self.stdout.write(self.style.SUCCESS(f"{done} empreinte(s) calculée(s)."))
