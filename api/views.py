"""
API REST de Blink (Django REST Framework).

Utilisée par l'interface (requêtes asynchrones : réactions, génération IA,
suivi des transcriptions) et exploitable par un client mobile / React.
Authentification : session ou jeton (`POST /api/auth/token/`).
"""
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from accounts.models import Friendship, TwoFactorDevice, User
from aistudio.models import AIPromptTemplate, GeneratedImage, ImageFilter
from aistudio.services import copy_source_image, process_generation_by_id
from audio.models import AudioComment, AudioPost, Transcription
from audio.services import transcribe_by_id
from audio.views import visible_audio_posts
from core.models import Notification, notify
from core.tasks import run_async
from faces.services import detect_faces_by_post_id
from posts import ai as posts_ai
from posts.models import AIGeneration, Comment, Post, Reaction

from . import serializers as s
from .permissions import IsOwnerOrReadOnly


class AIThrottle(UserRateThrottle):
    rate = "30/min"


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.UserSerializer
    lookup_field = "username"
    queryset = User.objects.filter(is_active=True).select_related("profile")

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs

    @action(detail=False, permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        return Response(self.get_serializer(request.user).data)

    @action(detail=True, permission_classes=[permissions.IsAuthenticated])
    def friends(self, request, username=None):
        user = self.get_object()
        return Response(self.get_serializer(user.friends(), many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def follow(self, request, username=None):
        target = self.get_object()
        if request.user.is_following(target):
            request.user.unfollow(target)
            return Response({"following": False})
        request.user.follow(target)
        return Response({"following": True})


class PostViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    owner_field = "auteur"

    def get_queryset(self):
        qs = Post.objects.visible_to(self.request.user).with_stats()
        if self.request.query_params.get("feed") and self.request.user.is_authenticated:
            qs = Post.objects.feed_for(self.request.user).with_stats()
        auteur = self.request.query_params.get("auteur")
        if auteur:
            qs = qs.filter(auteur__username=auteur)
        tag = self.request.query_params.get("hashtag")
        if tag:
            qs = qs.filter(Q(caption__icontains=f"#{tag}") | Q(hashtags_ia__icontains=f"#{tag}"))
        return qs

    def get_serializer_class(self):
        return s.PostUpdateSerializer if self.action in ("update", "partial_update") else s.PostSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            post = serializer.save(auteur=self.request.user)
            run_async(detect_faces_by_post_id, post.pk)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def react(self, request, pk=None):
        post = self.get_object()
        ser = s.ReactionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reaction = Reaction.toggle(request.user, post, ser.validated_data["type"])
        if reaction:
            notify(post.auteur, Notification.Type.REACTION,
                   f"{request.user} a réagi {reaction.get_type_display()} à ta publication.",
                   acteur=request.user, lien=post.get_absolute_url())
        return Response({"active": bool(reaction), "type": reaction.type if reaction else None,
                         "count": post.get_likes()})

    @action(detail=True, methods=["get", "post"], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def comments(self, request, pk=None):
        post = self.get_object()
        if request.method == "POST":
            ser = s.CommentSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            comment = ser.save(user=request.user, post=post)
            notify(post.auteur, Notification.Type.COMMENTAIRE, f"{request.user} a commenté : « {comment.contenu[:80]} »",
                   acteur=request.user, lien=post.get_absolute_url())
            return Response(s.CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        return Response(s.CommentSerializer(post.comments.select_related("user__profile"), many=True).data)

    @action(detail=True)
    def faces(self, request, pk=None):
        post = self.get_object()
        faces = post.detected_faces.select_related("user_identifie__profile").prefetch_related("tag_suggestions")
        return Response(s.DetectedFaceSerializer(faces, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated],
            throttle_classes=[AIThrottle])
    def generate_ai(self, request, pk=None):
        """Génère et enregistre légende + hashtags IA pour une publication existante."""
        post = self.get_object()
        if post.auteur != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)
        style = request.data.get("style", Post.Style.POETIQUE)
        result = post.generate_ai(style if style in Post.Style.values else Post.Style.POETIQUE)
        return Response({"caption": result["caption"], "hashtags": result["hashtags"], "engine": result["engine"]})


class CommentViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    serializer_class = s.CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def get_queryset(self):
        return Comment.objects.filter(post__in=Post.objects.visible_to(self.request.user)).select_related("user")


class AudioPostViewSet(viewsets.ModelViewSet):
    serializer_class = s.AudioPostSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return visible_audio_posts(self.request.user)

    def perform_create(self, serializer):
        post = serializer.validated_data.get("post")
        if post and post.auteur != self.request.user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Tu ne peux attacher un vocal qu'à tes propres publications.")
        with transaction.atomic():
            audio_post = serializer.save(user=self.request.user)
            Transcription.objects.create(audio_post=audio_post)
            run_async(transcribe_by_id, "post", audio_post.pk)

    @action(detail=True, methods=["post"])
    def transcribe(self, request, pk=None):
        audio_post = self.get_object()
        if audio_post.user != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)
        Transcription.objects.filter(audio_post=audio_post).update(statut=Transcription.Statut.EN_ATTENTE)
        run_async(transcribe_by_id, "post", audio_post.pk)
        return Response({"statut": "en_attente"}, status=status.HTTP_202_ACCEPTED)


class AudioCommentViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                          mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = s.AudioCommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = AudioComment.objects.filter(post__in=Post.objects.visible_to(self.request.user))
        if self.request.query_params.get("post"):
            qs = qs.filter(post_id=self.request.query_params["post"])
        return qs.select_related("user__profile", "transcription")

    def perform_create(self, serializer):
        post = serializer.validated_data["post"]
        if not post.can_view(self.request.user):
            from rest_framework.exceptions import NotFound

            raise NotFound()
        with transaction.atomic():
            comment = serializer.save(user=self.request.user, transcription=Transcription.objects.create())
            run_async(transcribe_by_id, "comment", comment.pk)


class TranscriptionViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Lecture (suivi du statut) et correction manuelle d'une transcription."""

    serializer_class = s.TranscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        visible = Post.objects.visible_to(user)
        return Transcription.objects.filter(
            Q(audio_post__post__isnull=True, audio_post__isnull=False)
            | Q(audio_post__post__in=visible)
            | Q(audio_comment__post__in=visible)
        ).distinct()

    def perform_update(self, serializer):
        if serializer.instance.owner != self.request.user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied()
        serializer.save(statut=Transcription.Statut.TERMINE, moteur="manuel", erreur="")


class GeneratedImageViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                            mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = s.GeneratedImageSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIThrottle]

    def get_queryset(self):
        return GeneratedImage.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError

        data = serializer.validated_data
        if data.get("type") == GeneratedImage.Type.AVATAR:
            if not self.request.user.photo_profil:
                raise ValidationError("Aucune photo de profil.")
            source = self.request.user.photo_profil
        else:
            post = data.get("post")
            if not post or post.auteur != self.request.user:
                raise ValidationError("Choisis une de tes publications.")
            source = post.image
        with transaction.atomic():
            gen = serializer.save(user=self.request.user)
            gen.image_originale.save("source.jpg", copy_source_image(source), save=True)
            run_async(process_generation_by_id, gen.pk)


class ImageFilterViewSet(viewsets.ModelViewSet):
    serializer_class = s.ImageFilterSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return ImageFilter.objects.filter(Q(user__isnull=True) | Q(user=self.request.user))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AIPromptTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = s.AIPromptTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AIPromptTemplate.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class FriendshipViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.FriendshipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        me = self.request.user
        return Friendship.objects.filter(Q(user_from=me) | Q(user_to=me)).select_related("user_from", "user_to")


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = s.NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(destinataire=self.request.user).select_related("acteur")

    @action(detail=False)
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(lu=False).count()})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        self.get_queryset().filter(lu=False).update(lu=True)
        return Response({"ok": True})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([AIThrottle])
def generate_caption(request):
    """
    Génère une légende stylisée + hashtags (Gemini, repli local).
    Accepte une image (multipart) avant publication, ou l'id d'une de mes publications.
    """
    ser = s.CaptionRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    post = None
    if data.get("post_id"):
        post = get_object_or_404(Post, pk=data["post_id"], auteur=request.user)
        image = post.image
    else:
        image = data["image"]
    context = data.get("context", "")
    if data.get("template_id"):
        template = AIPromptTemplate.objects.filter(pk=data["template_id"], user=request.user).first()
        if template:
            context = f"{context}\nConsigne : {template.render(caption=context, style=data['style'], description='')}"
    result = posts_ai.generate_caption(image, style=data["style"], context=context)
    AIGeneration.objects.create(
        post=post, user=request.user, type=AIGeneration.Type.LEGENDE, moteur=result["engine"],
        prompt=result.get("prompt", ""), result={"caption": result["caption"], "hashtags": result["hashtags"]},
    )
    return Response({"caption": result["caption"], "hashtags": result["hashtags"], "engine": result["engine"],
                     "style": data["style"]})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def ai_status(request):
    from django.conf import settings

    from core.ai_clients import gemini_enabled, hf_enabled
    from faces.engine import model_path

    return Response({
        "gemini": gemini_enabled(), "gemini_model": settings.GEMINI_MODEL,
        "huggingface": hf_enabled(), "image_model": settings.HF_IMAGE_MODEL, "whisper_model": settings.HF_WHISPER_MODEL,
        "face_recognition": model_path("sface")[0].exists(),
    })



class TwoFactorObtainAuthToken(ObtainAuthToken):
    """`POST /api/auth/token/` : identifiants + champ `otp` si la double authentification est active."""

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        device = TwoFactorDevice.objects.filter(user=user).first()
        if device is not None:
            otp = str(request.data.get("otp", "")).strip()
            if not otp:
                return Response({"otp": ["Code de double authentification requis."]}, status=status.HTTP_400_BAD_REQUEST)
            if not device.verify(otp):
                return Response({"otp": ["Code incorrect ou déjà utilisé."]}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})
