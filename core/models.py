from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Notification d'un événement adressée à un utilisateur."""

    class Type(models.TextChoices):
        REACTION = "reaction", "Réaction"
        COMMENTAIRE = "commentaire", "Commentaire"
        AMI = "ami", "Demande d'ami"
        TAG = "tag", "Identification"
        IA = "ia", "Génération IA"

    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    type = models.CharField(max_length=16, choices=Type.choices)
    message = models.CharField(max_length=255)
    lien = models.CharField(max_length=255, blank=True)
    lu = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "notification"
        ordering = ["-date"]
        indexes = [models.Index(fields=["destinataire", "lu"])]

    def __str__(self):
        return f"→ {self.destinataire}: {self.message}"


class Report(models.Model):
    """Signalement de contenu ou d'utilisateur (modération Blink)."""

    class Motif(models.TextChoices):
        SPAM = "spam", "Spam"
        HAINE = "haine", "Discours haineux"
        NUDITE = "nudite", "Contenu inapproprié"
        HARCELEMENT = "harcelement", "Harcèlement"
        AUTRE = "autre", "Autre"

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        APPROUVE = "approuve", "Approuvé"
        REJETE = "rejete", "Rejeté"

    class Action(models.TextChoices):
        AUCUNE = "aucune", "Aucune"
        MASQUER = "masquer", "Contenu masqué"
        SUPPRIMER = "supprimer", "Contenu supprimé"
        AVERTISSEMENT = "avertissement", "Avertissement envoyé"

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    # Cible du signalement (Post, Comment, ou User)
    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, null=True, blank=True, related_name="reports")
    comment = models.ForeignKey("posts.Comment", on_delete=models.CASCADE, null=True, blank=True, related_name="reports")
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="reports_received"
    )

    motif = models.CharField(max_length=20, choices=Motif.choices, default=Motif.AUTRE)
    details = models.TextField(blank=True, max_length=1000)
    
    # Cycle de vie et modération
    statut = models.CharField(max_length=16, choices=Statut.choices, default=Statut.EN_ATTENTE)
    action_prise = models.CharField(max_length=20, choices=Action.choices, default=Action.AUCUNE)
    moderateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="moderated_reports"
    )
    notes_moderation = models.TextField(blank=True, max_length=1000)
    date_traitement = models.DateTimeField(null=True, blank=True)

    # Rétrocompatibilité avec le champ hérité 'traite'
    traite = models.BooleanField("traité", default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "signalement"
        verbose_name_plural = "signalements"
        ordering = ["traite", "-date"]

    def __str__(self):
        cible = self.post or self.comment or self.reported_user or "Inconnu"
        return f"Signalement #{self.pk} [{self.get_motif_display()}] sur {cible}"

    def save(self, *args, **kwargs):
        # Garder 'traite' synchronisé avec 'statut'
        self.traite = self.statut in (self.Statut.APPROUVE, self.Statut.REJETE)
        super().save(*args, **kwargs)


def notify(destinataire, type, message, acteur=None, lien=""):
    """Crée une notification (ignorée si l'utilisateur agit sur son propre contenu)."""
    if acteur is not None and acteur == destinataire:
        return None
    return Notification.objects.create(
        destinataire=destinataire, acteur=acteur, type=type, message=message[:255], lien=lien
    )
