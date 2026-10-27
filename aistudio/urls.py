from django.urls import path

from . import views

app_name = "aistudio"

urlpatterns = [
    path("", views.StudioView.as_view(), name="studio"),
    path("post/<int:pk>/", views.GenerateFromPostView.as_view(), name="generate"),
    path("avatar/", views.GenerateAvatarView.as_view(), name="avatar"),
    path("image/<int:pk>/", views.GeneratedImageDetailView.as_view(), name="detail"),
    path("image/<int:pk>/supprimer/", views.GeneratedImageDeleteView.as_view(), name="delete"),
    path("image/<int:pk>/avatar/", views.UseAsAvatarView.as_view(), name="use_avatar"),
    path("image/<int:pk>/publier/", views.PublishGeneratedView.as_view(), name="publish"),
    path("modeles/", views.PromptTemplateListView.as_view(), name="templates"),
    path("modeles/nouveau/", views.PromptTemplateCreateView.as_view(), name="template_create"),
    path("modeles/<int:pk>/modifier/", views.PromptTemplateUpdateView.as_view(), name="template_update"),
    path("modeles/<int:pk>/supprimer/", views.PromptTemplateDeleteView.as_view(), name="template_delete"),
    path("filtres/", views.ImageFilterListView.as_view(), name="filters"),
    path("filtres/nouveau/", views.ImageFilterCreateView.as_view(), name="filter_create"),
    path("filtres/<int:pk>/modifier/", views.ImageFilterUpdateView.as_view(), name="filter_update"),
    path("filtres/<int:pk>/supprimer/", views.ImageFilterDeleteView.as_view(), name="filter_delete"),
]
