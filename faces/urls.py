from django.urls import path

from . import views

app_name = "faces"

urlpatterns = [
    path("", views.MyTagsView.as_view(), name="my_tags"),
    path("post/<int:pk>/", views.PostTagsView.as_view(), name="post_tags"),
    path("post/<int:pk>/analyser/", views.RedetectView.as_view(), name="redetect"),
    path("tag/<int:pk>/retirer/", views.RemoveTagView.as_view(), name="remove_tag"),
    path("empreinte/<str:action>/", views.FaceEncodingView.as_view(), name="encoding"),
]
