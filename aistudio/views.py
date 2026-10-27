from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import OwnerRequiredMixin, SuccessMessageDeleteMixin
from core.tasks import run_async
from faces.services import detect_faces_by_post_id
from posts.models import Post

from .forms import GenerateForm, ImageFilterForm, PromptTemplateForm
from .models import AIPromptTemplate, GeneratedImage, ImageFilter, Style
from .services import copy_source_image, process_generation_by_id


class StudioView(LoginRequiredMixin, ListView):
    """Galerie des images générées par l'utilisateur."""

    template_name = "aistudio/studio.html"
    context_object_name = "images"
    paginate_by = 24

    def get_queryset(self):
        qs = GeneratedImage.objects.filter(user=self.request.user).select_related("post")
        if self.request.GET.get("type") in GeneratedImage.Type.values:
            qs = qs.filter(type=self.request.GET["type"])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["my_posts"] = Post.objects.filter(auteur=self.request.user)[:12]
        ctx["types"] = GeneratedImage.Type.choices
        return ctx


class GenerateFromPostView(LoginRequiredMixin, CreateView):
    form_class = GenerateForm
    template_name = "aistudio/generate.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.post_obj = get_object_or_404(Post, pk=kwargs["pk"], auteur=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_initial(self):
        return {"type": GeneratedImage.Type.FILTRE, "style": Style.ANIME}

    def get_context_data(self, **kwargs):
        return super().get_context_data(source=self.post_obj, styles=Style.choices, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            gen = form.save(commit=False)
            gen.user, gen.post = self.request.user, self.post_obj
            gen.style = form.cleaned_data["style"]
            gen.image_originale.save("source.jpg", copy_source_image(self.post_obj.image), save=False)
            gen.save()
            run_async(process_generation_by_id, gen.pk)
        return redirect(gen.get_absolute_url())


class GenerateAvatarView(LoginRequiredMixin, CreateView):
    form_class = GenerateForm
    template_name = "aistudio/generate.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.photo_profil:
            messages.info(request, "Ajoute d'abord une photo de profil pour générer ton avatar.")
            return redirect("accounts:edit")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user, "avatar": True}

    def get_initial(self):
        return {"style": Style.ANIME}

    def get_context_data(self, **kwargs):
        return super().get_context_data(avatar=True, styles=Style.choices, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            gen = form.save(commit=False)
            gen.user, gen.type = self.request.user, GeneratedImage.Type.AVATAR
            gen.style = form.cleaned_data["style"]
            gen.image_originale.save("avatar_source.jpg", copy_source_image(self.request.user.photo_profil), save=False)
            gen.save()
            run_async(process_generation_by_id, gen.pk)
        return redirect(gen.get_absolute_url())


class GeneratedImageDetailView(OwnerRequiredMixin, DetailView):
    model = GeneratedImage
    template_name = "aistudio/image_detail.html"
    context_object_name = "gen"


class GeneratedImageDeleteView(OwnerRequiredMixin, SuccessMessageDeleteMixin, DeleteView):
    model = GeneratedImage
    template_name = "posts/confirm_delete.html"
    success_url = reverse_lazy("aistudio:studio")
    success_message = "Image supprimée."

    def form_valid(self, form):
        self.object.image_originale.delete(save=False)
        self.object.image_generee.delete(save=False)
        return super().form_valid(form)


class UseAsAvatarView(LoginRequiredMixin, View):
    def post(self, request, pk):
        gen = get_object_or_404(GeneratedImage, pk=pk, user=request.user, statut=GeneratedImage.Statut.TERMINE)
        profile = request.user.profile
        gen.image_generee.open("rb")
        profile.avatar.save(f"avatar_{gen.pk}.jpg", ContentFile(gen.image_generee.read()), save=True)
        gen.image_generee.close()
        messages.success(request, "Nouvel avatar appliqué ✨")
        return redirect(request.user.get_absolute_url())


class PublishGeneratedView(LoginRequiredMixin, View):
    """Publie l'image générée comme nouvelle publication."""

    def post(self, request, pk):
        gen = get_object_or_404(GeneratedImage, pk=pk, user=request.user, statut=GeneratedImage.Statut.TERMINE)
        gen.image_generee.open("rb")
        data = gen.image_generee.read()
        gen.image_generee.close()
        caption = f"Version {gen.get_style_display()} générée avec Blink ✨ #blinkstudio #{gen.style}"
        if gen.post_id and gen.post.caption:
            caption = f"{gen.post.caption}\n\n{caption}"
        with transaction.atomic():
            post = Post(auteur=request.user, caption=caption,
                        visibilite=gen.post.visibilite if gen.post_id else Post.Visibilite.PUBLIC)
            post.image.save(f"blink_ia_{gen.pk}.jpg", ContentFile(data), save=False)
            post.save()
            run_async(detect_faces_by_post_id, post.pk)
        messages.success(request, "C'est publié !", extra_tags=f"link:{post.get_absolute_url()}|Voir")
        return redirect(post.get_absolute_url())


# --- CRUD : modèles de prompt ---------------------------------------------------

class PromptTemplateListView(LoginRequiredMixin, ListView):
    template_name = "aistudio/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return AIPromptTemplate.objects.filter(user=self.request.user)


class PromptTemplateCreateView(LoginRequiredMixin, CreateView):
    form_class = PromptTemplateForm
    template_name = "aistudio/simple_form.html"
    success_url = reverse_lazy("aistudio:templates")
    extra_context = {"title": "Nouveau modèle de prompt"}

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Modèle enregistré.")
        return super().form_valid(form)


class PromptTemplateUpdateView(OwnerRequiredMixin, UpdateView):
    model = AIPromptTemplate
    form_class = PromptTemplateForm
    template_name = "aistudio/simple_form.html"
    success_url = reverse_lazy("aistudio:templates")
    extra_context = {"title": "Modifier le modèle"}
    allow_staff = False


class PromptTemplateDeleteView(OwnerRequiredMixin, SuccessMessageDeleteMixin, DeleteView):
    model = AIPromptTemplate
    template_name = "posts/confirm_delete.html"
    success_url = reverse_lazy("aistudio:templates")
    success_message = "Modèle supprimé."


# --- CRUD : filtres -------------------------------------------------------------

class ImageFilterListView(LoginRequiredMixin, ListView):
    template_name = "aistudio/filter_list.html"
    context_object_name = "filters"

    def get_queryset(self):
        return ImageFilter.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        return super().get_context_data(system_filters=ImageFilter.objects.filter(user__isnull=True), **kwargs)


class ImageFilterCreateView(LoginRequiredMixin, CreateView):
    form_class = ImageFilterForm
    template_name = "aistudio/simple_form.html"
    success_url = reverse_lazy("aistudio:filters")
    extra_context = {"title": "Nouveau filtre"}

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Filtre créé.")
        return super().form_valid(form)


class ImageFilterUpdateView(OwnerRequiredMixin, UpdateView):
    model = ImageFilter
    form_class = ImageFilterForm
    template_name = "aistudio/simple_form.html"
    success_url = reverse_lazy("aistudio:filters")
    extra_context = {"title": "Modifier le filtre"}
    allow_staff = False


class ImageFilterDeleteView(OwnerRequiredMixin, SuccessMessageDeleteMixin, DeleteView):
    model = ImageFilter
    template_name = "posts/confirm_delete.html"
    success_url = reverse_lazy("aistudio:filters")
    success_message = "Filtre supprimé."
