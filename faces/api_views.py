from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from core.models import Notification, notify
from posts.models import Post

from .engine import get_engine
from .models import DetectedFace, FaceEncoding, TagSuggestion
from .serializers import (
    DetectedFaceSerializer,
    FaceEncodingSerializer,
    TagStatusUpdateSerializer,
    TagSuggestionSerializer,
)
from .services import confirm_tag, detect_faces_for_post, encode_user


class FaceEncodingView(APIView):
    """
    CRUD for the authenticated user's face encoding (biometric fingerprint).
    - GET: Retrieve current user's reference face encoding.
    - POST: Generate or refresh face encoding from current profile picture.
    - DELETE: Remove face encoding.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        encoding = FaceEncoding.objects.filter(user=request.user).first()
        if not encoding:
            return Response(
                {"detail": "Aucun encodage facial enregistré pour cet utilisateur."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = FaceEncodingSerializer(encoding, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        if not request.user.photo_profil:
            return Response(
                {"detail": "Veuillez d'abord configurer une photo de profil."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        engine = get_engine()
        if not engine.recognition:
            return Response(
                {"detail": "Le moteur de reconnaissance faciale n'est pas encore initialisé."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        encoding = encode_user(request.user)
        if not encoding or not encoding.vecteur_encoding:
            return Response(
                {"detail": "Aucun visage net n'a été détecté sur votre photo de profil."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = FaceEncodingSerializer(encoding, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        deleted_count, _ = FaceEncoding.objects.filter(user=request.user).delete()
        if not deleted_count:
            return Response(
                {"detail": "Aucun encodage facial à supprimer."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostFaceDetectionView(APIView):
    """
    Handles face detection and tag suggestions for a specific post.
    - POST /api/posts/<post_id>/detect-faces/ : Runs detection on post photo.
    - GET /api/posts/<post_id>/detected-faces/ : Lists detected faces & tag suggestions.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        if post.auteur != request.user and not request.user.is_staff:
            return Response(
                {"detail": "Seul l'auteur de la publication peut lancer la détection."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not post.image:
            return Response(
                {"detail": "Cette publication ne contient aucune image à analyser."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        faces = detect_faces_for_post(post)
        serializer = DetectedFaceSerializer(faces, many=True, context={"request": request})
        return Response(
            {
                "message": f"{len(faces)} visage(s) détecté(s).",
                "count": len(faces),
                "faces": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request, post_id):
        post = get_object_or_404(Post.objects.visible_to(request.user), pk=post_id)
        faces = (
            post.detected_faces.select_related("user_identifie")
            .prefetch_related("tag_suggestions__user_suggere")
            .all()
        )
        serializer = DetectedFaceSerializer(faces, many=True, context={"request": request})
        return Response(serializer.data)


class DetectedFaceViewSet(ModelViewSet):
    """
    CRUD on DetectedFace objects.
    - GET /api/detected-faces/<id>/
    - DELETE /api/detected-faces/<id>/ (Removes false positive / detection)
    - PATCH /api/detected-faces/<id>/ (Allows author to manually assign user_identifie)
    """
    serializer_class = DetectedFaceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            DetectedFace.objects.filter(
                post__in=Post.objects.visible_to(self.request.user)
            )
            .select_related("post", "user_identifie")
            .prefetch_related("tag_suggestions__user_suggere")
        )

    def perform_destroy(self, instance):
        if instance.post.auteur != self.request.user and not self.request.user.is_staff:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Seul l'auteur de la publication peut supprimer un visage détecté.")
        if instance.image_source:
            instance.image_source.delete(save=False)
        instance.delete()


class TagSuggestionViewSet(GenericViewSet):
    """
    CRUD & Validation interactions on Tag Suggestions.
    - GET /api/tags/suggestions/ : List pending suggestions for the logged in user.
    - PATCH /api/tags/suggestions/<id>/status/ : Accept or reject a tag suggestion.
    - DELETE /api/tags/suggestions/<id>/ : Remove a tag.
    """
    serializer_class = TagSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            TagSuggestion.objects.select_related("detected_face__post__auteur", "user_suggere")
            .filter(user_suggere=self.request.user)
        )

    def list(self, request):
        """Lists all pending suggestions for the current authenticated user."""
        suggestions = self.get_queryset().filter(statut=TagSuggestion.Statut.EN_ATTENTE)
        serializer = self.get_serializer(suggestions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="status")
    def update_status(self, request, pk=None):
        suggestion = get_object_or_404(
            TagSuggestion.objects.select_related("detected_face__post__auteur", "user_suggere"),
            pk=pk,
        )
        # Only the suggested user or the post author can update
        is_suggested_user = suggestion.user_suggere == request.user
        is_post_author = suggestion.detected_face.post.auteur == request.user
        if not (is_suggested_user or is_post_author or request.user.is_staff):
            return Response(
                {"detail": "Vous n'avez pas la permission de modifier cette suggestion."},
                status=status.HTTP_403_FORBIDDEN,
            )

        validator = TagStatusUpdateSerializer(data=request.data)
        validator.is_valid(raise_exception=True)
        new_status = validator.validated_data["statut"]

        with transaction.atomic():
            face = suggestion.detected_face
            post = face.post
            suggestion.statut = new_status
            suggestion.save(update_fields=["statut"])

            if new_status == TagSuggestion.Statut.ACCEPTE:
                face.user_identifie = suggestion.user_suggere
                face.save(update_fields=["user_identifie"])
                # If accepted by the suggested user, notify post author
                if request.user == suggestion.user_suggere and post.auteur != request.user:
                    notify(
                        post.auteur,
                        Notification.Type.TAG,
                        f"{request.user} a accepté le tag sur votre publication.",
                        acteur=request.user,
                        lien=post.get_absolute_url(),
                    )
            elif new_status == TagSuggestion.Statut.REFUSE:
                if face.user_identifie == suggestion.user_suggere:
                    face.user_identifie = None
                    face.save(update_fields=["user_identifie"])

        return Response(self.get_serializer(suggestion).data)

    def destroy(self, request, pk=None):
        suggestion = get_object_or_404(TagSuggestion, pk=pk)
        is_suggested_user = suggestion.user_suggere == request.user
        is_post_author = suggestion.detected_face.post.auteur == request.user
        if not (is_suggested_user or is_post_author or request.user.is_staff):
            return Response(
                {"detail": "Vous n'avez pas la permission de supprimer ce tag."},
                status=status.HTTP_403_FORBIDDEN,
            )
        face = suggestion.detected_face
        if face.user_identifie == suggestion.user_suggere:
            face.user_identifie = None
            face.save(update_fields=["user_identifie"])
        suggestion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
