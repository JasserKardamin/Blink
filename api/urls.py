from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

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

urlpatterns = [
    path("", include(router.urls)),
    path("ai/caption/", views.generate_caption, name="ai_caption"),
    path("ai/status/", views.ai_status, name="ai_status"),
    path("auth/token/", obtain_auth_token, name="token"),
    path("auth/", include("rest_framework.urls")),
]
