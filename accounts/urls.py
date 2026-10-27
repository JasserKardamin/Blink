from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("inscription/", views.SignUpView.as_view(), name="signup"),
    path("connexion/", views.BlinkLoginView.as_view(), name="login"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("profil/modifier/", views.ProfileUpdateView.as_view(), name="edit"),
    path("amis/", views.FriendsView.as_view(), name="friends"),
    path("amis/demande/<int:pk>/<str:action>/", views.FriendRespondView.as_view(), name="friend_respond"),
    path("u/<str:username>/", views.ProfileDetailView.as_view(), name="profile"),
    path("u/<str:username>/ajouter/", views.FriendRequestView.as_view(), name="friend_request"),
    path("u/<str:username>/retirer/", views.FriendRemoveView.as_view(), name="friend_remove"),
    path("u/<str:username>/suivre/", views.FollowToggleView.as_view(), name="follow"),
]
