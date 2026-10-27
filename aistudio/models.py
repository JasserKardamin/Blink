from django.conf import settings
from django.db import models
from django.urls import reverse

from core.validators import validate_image_size


class Style(models.TextChoices):
    ANIME = "anime", "Anime"
    PEINTURE = "peinture", "Peinture à l'huile"
    CYBERPUNK = "cyberpunk", "Cyberpunk"
    AQUARELLE = "aquarelle", "Aquarelle"
    CROQUIS = "croquis", "Croquis"
    VINTAGE = "vintage", "Vintage"


class ImageFilter(models.Model):
    """Filtre artistique réutilisable (filtres système si user est vide)."""

    nom = models.CharField(max_length=60)
    description = models.TextField(blank=True, max_length=500)
    parametres = models.JSONField(
        default=dict, blank=True,
        help_text='Ex. {"base": "anime", "intensite": 1.0, "saturation": 1.2, "contraste": 1.0}',
    )
    preview = models.ImageField(upload_to="filtres/", blank=True, validators=[validate_image_size])
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="image_filters"
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "filtre d'image"
        verbose_name_plural = "filtres d'image"
        ordering = ["user_id", "nom"]

    def __str__(self):
        return self.nom

    @property
    def base_style(self):
        base = (self.parametres or {}).get("base", Style.ANIME)
        return base if base in Style.values else Style.ANIME

    @property
    def is_system(self):
        return self.user_id is None


class AIPromptTemplate(models.Model):
    """Modèle de prompt personnel réutilisable."""

    class Type(models.TextChoices):
        DESCRIPTION = "description", "Description (légende)"
        IMAGE = "image", "Génération d'image"
        FILTRE = "filtre", "Filtre"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="prompt_templates")
    nom = models.CharField(max_length=80)
    template_prompt = models.TextField(
        max_length=1000,
        help_text="Variables disponibles : {description}, {style}, {caption}.",
    )
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.IMAGE)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "modèle de prompt"
        verbose_name_plural = "modèles de prompt"
        ordering = ["-date"]

    def __str__(self):
        return self.nom

    def render(self, **values):
        class SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        return self.template_prompt.format_map(SafeDict(**values))


class GeneratedImage(models.Model):
    """Image produite par l'IA (filtre, image dérivée ou avatar)."""

    class Type(models.TextChoices):
        FILTRE = "filtre", "Filtre IA"
        DERIVEE = "derivee", "Image artistique dérivée"
        AVATAR = "avatar", "Avatar"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En cours"
        TERMINE = "termine", "Terminée"
        ERREUR = "erreur", "Erreur"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="generated_images")
    post = models.ForeignKey(
        "posts.Post", on_delete=models.CASCADE, null=True, blank=True, related_name="generated_images"
    )
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.FILTRE)
    filtre = models.ForeignKey(ImageFilter, on_delete=models.SET_NULL, null=True, blank=True)
    template = models.ForeignKey(AIPromptTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    image_originale = models.ImageField(upload_to="ia/originales/%Y/%m/")
    image_generee = models.ImageField(upload_to="ia/generees/%Y/%m/", blank=True)
    prompt = models.TextField(blank=True)
    style = models.CharField(max_length=20, choices=Style.choices, default=Style.ANIME)
    modele = models.CharField("modèle", max_length=120, blank=True)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    erreur = models.CharField(max_length=255, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "image générée"
        verbose_name_plural = "images générées"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_type_display()} {self.get_style_display()} #{self.pk}"

    def get_absolute_url(self):
        return reverse("aistudio:detail", kwargs={"pk": self.pk})
