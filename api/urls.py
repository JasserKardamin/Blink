from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from core import api_views as core_api
from faces import api_views as faces_api
from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("posts", views.PostViewSet, basename="post")
router.register("comments", views.CommentViewSet, basename="comment")
router.register("audio-posts", views.AudioPostViewSet, basename="audiopost")
router.register("audio-comments", views.AudioCommentViewSet, basename="audiocomment")
router.register("transcriptions", views.TranscriptionViewSet, basename="transcription")
router.register("generated-images", views.GeneratedImageViewSet, basename="generatedimage")
router.register("filters", views.ImageFilterViewSet, basename="imagefilter")
router.register("prompt-templates", views.AIPromptTemplateViewSet, basename="prompttemplate")
router.register("friendships", views.FriendshipViewSet, basename="friendship")
router.register("notifications", views.NotificationViewSet, basename="notification")

# Gestion 4 : Reconnaissance Faciale & Tagging ViewSets
router.register("detected-faces", faces_api.DetectedFaceViewSet, basename="detected-face")
router.register("tags/suggestions", faces_api.TagSuggestionViewSet, basename="tag-suggestion")

# Gestion 5 : Modération & Signalements
router.register("reports", core_api.ReportViewSet, basename="report")

urlpatterns = [
    # Face Encoding endpoints
    path("faces/encoding/generate/", faces_api.FaceEncodingView.as_view(), name="face_encoding_generate"),
    path("faces/encoding/", faces_api.FaceEncodingView.as_view(), name="face_encoding_detail"),

    # Post Face Detection endpoints
    path("posts/<int:post_id>/detect-faces/", faces_api.PostFaceDetectionView.as_view(), name="post_detect_faces"),
    path("posts/<int:post_id>/detected-faces/", faces_api.PostFaceDetectionView.as_view(), name="post_detected_faces"),

    path("", include(router.urls)),
    path("ai/caption/", views.generate_caption, name="ai_caption"),
    path("ai/status/", views.ai_status, name="ai_status"),
    path("auth/token/", views.TwoFactorObtainAuthToken.as_view(), name="token"),
    # La page de connexion de l'API navigable passe par Blink (double authentification).
    path("auth/login/", RedirectView.as_view(url=reverse_lazy("accounts:login"), query_string=True)),
    path("auth/", include("rest_framework.urls")),
]
