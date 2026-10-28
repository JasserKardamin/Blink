from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.models import Report
from core.serializers import ReportCreateSerializer, ReportResolveSerializer, ReportSerializer
from core.services import process_report_resolution


class ReportViewSet(viewsets.ModelViewSet):
    """
    Gestion des signalements (Modération Blink).
    - POST /api/reports/ : Signaler un post, un commentaire ou un utilisateur.
    - GET /api/reports/ :
        * Staff : Accès à toute la file de modération (avec filtres ?statut=en_attente).
        * Utilisateur normal : Liste uniquement ses propres signalements déposés.
    - GET /api/reports/<id>/ : Détail d'un signalement.
    - PATCH /api/reports/<id>/resolve/ : (Staff uniquement) Valider ou rejeter un signalement avec action.
    - DELETE /api/reports/<id>/ : Supprimer un signalement (Staff ou auteur tant qu'il est en attente).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Report.objects.select_related("auteur", "moderateur", "post__auteur", "comment__user", "reported_user")
        if not user.is_staff:
            return qs.filter(auteur=user)
        
        # Filtrage optionnel pour les modérateurs
        statut = self.request.query_params.get("statut")
        motif = self.request.query_params.get("motif")
        if statut:
            qs = qs.filter(statut=statut)
        if motif:
            qs = qs.filter(motif=motif)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ReportCreateSerializer
        if self.action == "resolve":
            return ReportResolveSerializer
        return ReportSerializer

    def perform_create(self, serializer):
        serializer.save(auteur=self.request.user)

    @action(detail=True, methods=["patch"], url_path="resolve")
    def resolve(self, request, pk=None):
        if not request.user.is_staff:
            raise PermissionDenied("Seuls les modérateurs peuvent statuer sur un signalement.")

        report = get_object_or_404(Report.objects.select_related("post__auteur", "comment__user"), pk=pk)
        validator = ReportResolveSerializer(data=request.data)
        validator.is_valid(raise_exception=True)

        data = validator.validated_data
        updated_report = process_report_resolution(
            report=report,
            statut=data["statut"],
            action_prise=data.get("action_prise", Report.Action.AUCUNE),
            moderateur=request.user,
            notes=data.get("notes_moderation", ""),
        )
        return Response(ReportSerializer(updated_report).data)

    def perform_destroy(self, instance):
        is_owner = instance.auteur == self.request.user and instance.statut == Report.Statut.EN_ATTENTE
        if not (self.request.user.is_staff or is_owner):
            raise PermissionDenied("Vous ne pouvez pas supprimer ce signalement.")
        instance.delete()
