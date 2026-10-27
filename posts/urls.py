from django.urls import path

from . import views

app_name = "posts"

urlpatterns = [
    path("nouveau/", views.PostCreateView.as_view(), name="create"),
    path("explorer/", views.ExploreView.as_view(), name="explore"),
    path("tag/<str:tag>/", views.HashtagView.as_view(), name="hashtag"),
    path("<int:pk>/", views.PostDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.PostUpdateView.as_view(), name="update"),
    path("<int:pk>/supprimer/", views.PostDeleteView.as_view(), name="delete"),
    path("<int:pk>/reagir/", views.ReactView.as_view(), name="react"),
    path("<int:pk>/commenter/", views.CommentCreateView.as_view(), name="comment"),
    path("<int:pk>/signaler/", views.ReportCreateView.as_view(), name="report"),
    path("commentaire/<int:pk>/modifier/", views.CommentUpdateView.as_view(), name="comment_update"),
    path("commentaire/<int:pk>/supprimer/", views.CommentDeleteView.as_view(), name="comment_delete"),
]
