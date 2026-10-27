from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Notification affichée dans la cloche de la barre de navigation."""

    class Type(models.TextChoices):
        REACTION = "reaction", "Réaction"
        COMMENTAIRE = "commentaire", "Commentaire"
        COMMENTAIRE_VOCAL = "commentaire_vocal", "Commentaire vocal"
        DEMANDE_AMI = "demande_ami", "Demande d'ami"
        AMI_ACCEPTE = "ami_accepte", "Ami accepté"
        ABONNEMENT = "abonnement", "Nouvel abonné"
        TAG = "tag", "Identification"
        IA = "ia", "Traitement IA"

    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    message = models.CharField(max_length=255)
    lien = models.CharField(max_length=255, blank=True)
    lu = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        indexes = [models.Index(fields=["destinataire", "lu"])]

    def __str__(self):
        return f"→ {self.destinataire}: {self.message}"


class Report(models.Model):
    """Signalement d'une publication (consulté par l'administrateur)."""

    class Motif(models.TextChoices):
        SPAM = "spam", "Spam"
        HAINE = "haine", "Discours haineux"
        NUDITE = "nudite", "Contenu inapproprié"
        HARCELEMENT = "harcelement", "Harcèlement"
        AUTRE = "autre", "Autre"

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="reports")
    motif = models.CharField(max_length=20, choices=Motif.choices, default=Motif.AUTRE)
    details = models.TextField(blank=True, max_length=1000)
    traite = models.BooleanField("traité", default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "signalement"
        ordering = ["traite", "-date"]
        constraints = [models.UniqueConstraint(fields=["auteur", "post"], name="unique_report")]

    def __str__(self):
        return f"Signalement #{self.pk} – {self.get_motif_display()}"


def notify(destinataire, type, message, acteur=None, lien=""):
    """Crée une notification (ignorée si l'utilisateur agit sur son propre contenu)."""
    if acteur is not None and acteur == destinataire:
        return None
    return Notification.objects.create(
        destinataire=destinataire, acteur=acteur, type=type, message=message[:255], lien=lien
    )
