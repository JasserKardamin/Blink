"""
Crée un jeu de données de démonstration : utilisateurs, amitiés, publications
(images générées procéduralement), légendes IA, commentaires et réactions.

    python manage.py seed_demo            # données de démo
    python manage.py seed_demo --admin    # + compte admin / admin12345
"""
import io
import math
import random

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageDraw, ImageFilter

from accounts.models import Friendship, User
from posts.ai import local_caption
from posts.models import Comment, Post, Reaction

PASSWORD = "blink12345"

USERS = [
    ("nour", "Nour", "Benali", "Tunis", "Photographe amatrice, fan de golden hour 🌅"),
    ("sami", "Sami", "Trabelsi", "Sousse", "Toujours partant pour un road trip."),
    ("yassine", "Yassine", "Haddad", "Sfax", "Café, code et coucher de soleil."),
    ("lina", "Lina", "Mansour", "Bizerte", "Aquarelle & voyages ✏️"),
]

SCENES = [
    # (ciel haut, ciel bas, soleil, montagnes, sol, légende auteur)
    ((255, 140, 90), (255, 205, 130), (255, 90, 70), (139, 123, 255), (60, 40, 110), "Coucher de soleil entre amis"),
    ((40, 90, 200), (102, 197, 255), (255, 240, 200), (30, 60, 120), (20, 110, 160), "Journée à la plage"),
    ((20, 18, 50), (70, 40, 120), (240, 240, 255), (40, 30, 80), (19, 17, 42), "Nuit étoilée au désert"),
    ((120, 200, 140), (200, 240, 200), (255, 230, 120), (40, 120, 70), (30, 90, 50), "Randonnée en forêt"),
    ((255, 170, 200), (255, 220, 235), (255, 255, 255), (200, 120, 200), (150, 80, 160), "Rêve pastel"),
    ((255, 120, 60), (255, 190, 90), (255, 230, 120), (120, 60, 40), (80, 40, 30), "Golden hour en ville"),
]

COMMENTS = [
    "Trop beau ce coucher de soleil, on y retourne demain !",
    "Je prends les sandwichs 😄",
    "Magnifique photo 😍",
    "La lumière est incroyable",
    "Il faut absolument que tu m'emmènes là-bas !",
]


def make_scene(top, bottom, sun, mountains, ground, seed, size=(1080, 1080)):
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    if sum(top) < 200:  # étoiles pour les scènes de nuit
        for _ in range(160):
            x, y = rng.randrange(w), rng.randrange(int(h * 0.6))
            r = rng.choice([1, 1, 2])
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    sx, sy, sr = rng.randint(180, w - 180), rng.randint(160, 380), rng.randint(70, 120)
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([sx - sr * 2, sy - sr * 2, sx + sr * 2, sy + sr * 2], fill=sun + (90,))
    img.paste(glow.filter(ImageFilter.GaussianBlur(60)), (0, 0), glow.filter(ImageFilter.GaussianBlur(60)))
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=sun)
    for layer, base in enumerate((0.62, 0.72)):
        color = tuple(int(c * (0.8 + 0.2 * layer)) for c in mountains)
        pts = [(0, h)]
        for x in range(0, w + 40, 40):
            y = h * base - 120 * math.sin(x / (160 + 60 * layer) + seed) - rng.randint(0, 40)
            pts.append((x, y))
        pts.append((w, h))
        draw.polygon(pts, fill=color)
    draw.rectangle([0, int(h * 0.86), w, h], fill=ground)
    buf = io.BytesIO()
    img.filter(ImageFilter.SMOOTH).save(buf, format="JPEG", quality=88)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Remplit la base avec des données de démonstration Blink."

    def add_arguments(self, parser):
        parser.add_argument("--admin", action="store_true", help="Crée aussi le superutilisateur admin / admin12345")

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(42)
        users = []
        for username, first, last, ville, bio in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@blink.demo", "first_name": first, "last_name": last, "bio": bio},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
                user.profile.ville = ville
                user.profile.save()
            users.append(user)

        if options["admin"] and not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@blink.demo", "admin12345", first_name="Admin")
            self.stdout.write(self.style.SUCCESS("Superutilisateur admin / admin12345 créé."))

        for i, a in enumerate(users):
            for b in users[i + 1:]:
                if not a.friendship_with(b):
                    Friendship.objects.create(user_from=a, user_to=b, statut=Friendship.Statut.ACCEPTE)
                    a.follow(b)
                    b.follow(a)

        if Post.objects.filter(auteur__in=users).exists():
            self.stdout.write("Les publications de démo existent déjà.")
            return

        styles = ["poetique", "marketing", "humoristique"]
        for idx, (top, bottom, sun, mountains, ground, title) in enumerate(SCENES):
            author = users[idx % len(users)]
            data = make_scene(top, bottom, sun, mountains, ground, seed=idx + 1)
            style = styles[idx % 3]
            ai = local_caption(data, style)
            post = Post(
                auteur=author,
                caption=f"{title}\n{ai['caption']}",
                caption_ia=ai["caption"],
                caption_style=style,
                hashtags_ia=" ".join(f"#{t}" for t in ai["hashtags"]),
                visibilite=Post.Visibilite.PUBLIC if idx % 3 else Post.Visibilite.AMIS,
            )
            post.image.save(f"demo_{idx + 1}.jpg", ContentFile(data), save=False)
            post.save()
            for other in users:
                if other != author and rng.random() < 0.75:
                    Reaction.objects.create(user=other, post=post, type=rng.choice(["love", "love", "like", "haha"]))
            for other in rng.sample([u for u in users if u != author], 2):
                Comment.objects.create(user=other, post=post, contenu=rng.choice(COMMENTS))

        self.stdout.write(self.style.SUCCESS(
            f"{len(users)} utilisateurs (mot de passe : {PASSWORD}) et {len(SCENES)} publications créés."
        ))
