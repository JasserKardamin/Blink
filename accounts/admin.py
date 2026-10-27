from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import Follow, Friendship, Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("avatar_thumb", "username", "email", "first_name", "last_name", "nb_posts", "is_active", "is_staff", "date_joined")
    list_display_links = ("avatar_thumb", "username")
    list_filter = ("is_active", "is_staff", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    fieldsets = BaseUserAdmin.fieldsets + (("Blink", {"fields": ("photo_profil", "bio")}),)
    actions = ["desactiver", "activer"]

    @admin.display(description="")
    def avatar_thumb(self, obj):
        url = obj.display_avatar_url
        if url:
            return format_html('<img src="{}" style="width:32px;height:32px;border-radius:50%;object-fit:cover">', url)
        return format_html(
            '<span style="display:inline-grid;place-items:center;width:32px;height:32px;border-radius:50%;background:{};color:#fff">{}</span>',
            obj.avatar_color, obj.initial,
        )

    @admin.display(description="Posts")
    def nb_posts(self, obj):
        return obj.posts.count()

    @admin.action(description="Désactiver les comptes sélectionnés")
    def desactiver(self, request, queryset):
        updated = queryset.exclude(pk=request.user.pk).update(is_active=False)
        self.message_user(request, f"{updated} compte(s) désactivé(s).")

    @admin.action(description="Réactiver les comptes sélectionnés")
    def activer(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} compte(s) réactivé(s).")


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("user_from", "user_to", "statut", "date")
    list_filter = ("statut",)
    search_fields = ("user_from__username", "user_to__username")
    autocomplete_fields = ("user_from", "user_to")


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "followed", "date")
    search_fields = ("follower__username", "followed__username")
    autocomplete_fields = ("follower", "followed")
