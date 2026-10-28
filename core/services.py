from django.utils import timezone
from core.models import Notification, Report, notify


def process_report_resolution(report, statut, action_prise, moderateur, notes=""):
    """
    Applique la décision de modération sur un signalement et exécute les actions (masquer, supprimer).
    Envoie des notifications adaptées au signaleur et à l'auteur du contenu.
    """
    report.statut = statut
    report.action_prise = action_prise
    report.moderateur = moderateur
    report.notes_moderation = notes
    report.date_traitement = timezone.now()

    # 1. Action sur le contenu
    if statut == Report.Statut.APPROUVE:
        if action_prise == Report.Action.MASQUER:
            if report.post:
                report.post.est_masque = True
                report.post.save(update_fields=["est_masque"])
                notify(
                    report.post.auteur,
                    Notification.Type.IA,
                    "Une de vos publications a été masquée suite à un signalement validé.",
                )
        elif action_prise == Report.Action.SUPPRIMER:
            if report.post:
                author = report.post.auteur
                report.post.delete()
                report.post = None
                notify(
                    author,
                    Notification.Type.IA,
                    "Une de vos publications a été supprimée par la modération pour non-respect des règles.",
                )
            elif report.comment:
                author = report.comment.user
                report.comment.delete()
                report.comment = None
                notify(
                    author,
                    Notification.Type.IA,
                    "Un de vos commentaires a été supprimé par la modération.",
                )

        # Notification de remerciement au signaleur
        notify(
            report.auteur,
            Notification.Type.IA,
            "Merci d'avoir signalé ce contenu. Notre équipe a examiné et pris des mesures adaptées.",
        )

    elif statut == Report.Statut.REJETE:
        notify(
            report.auteur,
            Notification.Type.IA,
            "Votre signalement a été examiné par notre équipe et classé sans suite.",
        )

    report.save()
    return report
