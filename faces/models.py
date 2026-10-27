from django.conf import settings
from django.db import models


class FaceEncoding(models.Model):
    """Empreinte faciale de référence d'un utilisateur (calculée depuis sa photo de profil)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="face_encoding")
    vecteur_encoding = models.JSONField(default=list)
    photo_reference = models.ImageField(upload_to="visages/references/%Y/%m/")
    date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "encodage facial"
        verbose_name_plural = "encodages faciaux"

    def __str__(self):
        return f"Encodage de {self.user}"


class DetectedFace(models.Model):
    """Visage détecté sur une publication."""

    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="detected_faces")
    image_source = models.ImageField("visage recadré", upload_to="visages/detectes/%Y/%m/", blank=True)
    bounding_box = models.JSONField(default=dict, help_text="x, y, w, h en pourcentage de l'image")
    encoding_detecte = models.JSONField(default=list, blank=True)
    user_identifie = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    confiance = models.FloatField(default=0.0)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "visage détecté"
        verbose_name_plural = "visages détectés"
        ordering = ["post", "pk"]

    def __str__(self):
        return f"Visage #{self.pk} sur post {self.post_id}"

    @property
    def confiance_pct(self):
        return round(self.confiance * 100)

    @property
    def accepted_tag(self):
        return self.tag_suggestions.filter(statut=TagSuggestion.Statut.ACCEPTE).select_related("user_suggere").first()


class TagSuggestion(models.Model):
    """Identification (suggérée par l'IA ou manuelle) d'un ami sur un visage."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        ACCEPTE = "accepte", "Accepté"
        REFUSE = "refuse", "Refusé"

    detected_face = models.ForeignKey(DetectedFace, on_delete=models.CASCADE, related_name="tag_suggestions")
    user_suggere = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tag_suggestions")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    auto = models.BooleanField("suggéré par l'IA", default=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "suggestion de tag"
        verbose_name_plural = "suggestions de tag"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user_suggere} sur visage #{self.detected_face_id} ({self.get_statut_display()})"
