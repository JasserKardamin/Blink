from django.conf import settings
from django.db import models
from django.urls import reverse

from core.validators import validate_audio_file


class Transcription(models.Model):
    """Texte transcrit par l'IA à partir d'un audio (accessibilité)."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        TERMINE = "termine", "Terminée"
        ERREUR = "erreur", "Erreur"

    audio_post = models.OneToOneField(
        "AudioPost", on_delete=models.CASCADE, null=True, blank=True, related_name="transcription"
    )
    texte = models.TextField(blank=True)
    langue = models.CharField(max_length=10, blank=True)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    moteur = models.CharField(max_length=40, blank=True)
    erreur = models.CharField(max_length=255, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"Transcription #{self.pk} ({self.get_statut_display()})"

    @property
    def owner(self):
        if self.audio_post_id:
            return self.audio_post.user
        comment = getattr(self, "audio_comment", None)
        return comment.user if comment else None

    @property
    def audio_file(self):
        if self.audio_post_id:
            return self.audio_post.fichier_audio
        comment = getattr(self, "audio_comment", None)
        return comment.fichier_audio if comment else None

    @property
    def is_completed(self):
        """Vérifie si la transcription est terminée avec succès."""
        return self.statut == self.Statut.TERMINE

    @property
    def is_pending(self):
        """Vérifie si la transcription est en cours d'analyse."""
        return self.statut == self.Statut.EN_ATTENTE

    @property
    def is_error(self):
        """Vérifie si une erreur est survenue lors de la transcription."""
        return self.statut == self.Statut.ERREUR


class AudioPost(models.Model):
    """Message vocal publié seul ou attaché à une publication photo."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="audio_posts")
    post = models.ForeignKey(
        "posts.Post", on_delete=models.CASCADE, null=True, blank=True, related_name="audio_posts"
    )
    fichier_audio = models.FileField(upload_to="audio/posts/%Y/%m/", validators=[validate_audio_file])
    description = models.TextField(null=True, blank=True, max_length=500)
    duree = models.PositiveIntegerField("durée (s)", default=0)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "post audio"
        verbose_name_plural = "posts audio"
        ordering = ["-date"]

    def __str__(self):
        return f"Audio de {self.user} ({self.duree}s)"

    def get_absolute_url(self):
        return reverse("audio:detail", kwargs={"pk": self.pk})

    @property
    def formatted_duration(self):
        """Retourne la durée formatée en MM:SS."""
        minutes = self.duree // 60
        seconds = self.duree % 60
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def has_transcription(self):
        """Indique si une transcription textuelle est disponible."""
        return hasattr(self, "transcription") and bool(self.transcription.texte)

    def transcribe(self):
        from .services import transcribe_object

        return transcribe_object(self)


class AudioComment(models.Model):
    """Commentaire vocal sur une publication, transcrit pour l'accessibilité."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="audio_comments")
    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="audio_comments")
    fichier_audio = models.FileField(upload_to="audio/commentaires/%Y/%m/", validators=[validate_audio_file])
    transcription = models.OneToOneField(
        Transcription, on_delete=models.SET_NULL, null=True, blank=True, related_name="audio_comment"
    )
    duree = models.PositiveIntegerField("durée (s)", default=0)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "commentaire vocal"
        verbose_name_plural = "commentaires vocaux"
        ordering = ["date"]

    def __str__(self):
        return f"Vocal de {self.user} sur post {self.post_id}"

    @property
    def formatted_duration(self):
        """Retourne la durée formatée en MM:SS."""
        minutes = self.duree // 60
        seconds = self.duree % 60
        return f"{minutes:02d}:{seconds:02d}"

    def transcribe(self):
        from .services import transcribe_object

        return transcribe_object(self)
