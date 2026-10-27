from django.db import migrations

SYSTEM_FILTERS = [
    ("Anime", "Aplats de couleurs et contours encrés façon dessin animé.", {"base": "anime"}),
    ("Peinture à l'huile", "Touches de pinceau épaisses et couleurs riches.", {"base": "peinture", "saturation": 1.15}),
    ("Cyberpunk", "Néons magenta et cyan, ambiance futuriste.", {"base": "cyberpunk"}),
    ("Aquarelle", "Lavis doux et texture papier.", {"base": "aquarelle"}),
    ("Croquis", "Dessin au crayon graphite.", {"base": "croquis"}),
    ("Vintage", "Pellicule sépia des années 70 avec vignettage.", {"base": "vintage"}),
]


def create_filters(apps, schema_editor):
    ImageFilter = apps.get_model("aistudio", "ImageFilter")
    for nom, description, params in SYSTEM_FILTERS:
        ImageFilter.objects.get_or_create(nom=nom, user=None, defaults={"description": description, "parametres": params})


def remove_filters(apps, schema_editor):
    ImageFilter = apps.get_model("aistudio", "ImageFilter")
    ImageFilter.objects.filter(user=None, nom__in=[f[0] for f in SYSTEM_FILTERS]).delete()


class Migration(migrations.Migration):
    dependencies = [("aistudio", "0001_initial")]
    operations = [migrations.RunPython(create_filters, remove_filters)]
