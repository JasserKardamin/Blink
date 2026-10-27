from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("recherche/", views.SearchView.as_view(), name="search"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path("notifications/<int:pk>/", views.NotificationOpenView.as_view(), name="notification_open"),
]
