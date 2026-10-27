from django.urls import path

from . import views

app_name = "audio"

urlpatterns = [
    path("", views.AudioPostListView.as_view(), name="list"),
    path("nouveau/", views.AudioPostCreateView.as_view(), name="create"),
    path("<int:pk>/", views.AudioPostDetailView.as_view(), name="detail"),
    path("<int:pk>/supprimer/", views.AudioPostDeleteView.as_view(), name="delete"),
    path("transcription/<int:pk>/modifier/", views.TranscriptionUpdateView.as_view(), name="transcription_update"),
    path("<str:kind>/<int:pk>/retranscrire/", views.RetranscribeView.as_view(), name="retranscribe"),
    path("post/<int:pk>/commentaire-vocal/", views.AudioCommentCreateView.as_view(), name="comment_create"),
    path("commentaire/<int:pk>/supprimer/", views.AudioCommentDeleteView.as_view(), name="comment_delete"),
]
