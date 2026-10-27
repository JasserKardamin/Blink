from django.core.management.base import BaseCommand, CommandError

from faces.engine import MODELS, ensure_models, model_path


class Command(BaseCommand):
    help = "Télécharge les modèles ONNX de reconnaissance faciale (YuNet + SFace)."

    def handle(self, *args, **options):
        if not ensure_models():
            raise CommandError("Téléchargement impossible. Vérifie la connexion ou place les fichiers manuellement.")
        for key in MODELS:
            path = model_path(key)[0]
            self.stdout.write(self.style.SUCCESS(f"✓ {path.name} ({path.stat().st_size // 1024} Ko)"))
