from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Lecture pour tous, écriture réservée au propriétaire (attribut `owner_field` de la vue)."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        owner = obj
        for part in getattr(view, "owner_field", "user").split("."):
            owner = getattr(owner, part, None)
        return owner == request.user
