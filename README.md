# Blink — Poste. Parle. L'IA fait le reste.

Réseau social multimédia boosté à l'IA, développé avec **Django 5.2**.
Les utilisateurs publient des photos accompagnées de messages vocaux ; l'IA écrit des
légendes stylisées, propose des hashtags, transcrit les vocaux, crée des images
artistiques et reconnaît les amis sur les photos.

| Fonctionnalité | Technologie | Sans clé d'API |
|---|---|---|
| Publication photo + audio | Django, Pillow | ✅ |
| Notes personnelles privées sur ses amis | Django ORM | ✅ |
| Légendes stylisées (poétique, marketing, humoristique) | Gemini API | générateur local (analyse des couleurs) |
| Hashtags automatiques | Gemini API | générateur local |
| Filtres IA / images dérivées / avatars | Hugging Face (Stable Diffusion) | filtres OpenCV (anime, peinture, cyberpunk…) |
| Transcription audio (accessibilité) | Whisper (Hugging Face) → Gemini | saisie manuelle |
| Reconnaissance faciale & tags d'amis | OpenCV YuNet + SFace (ONNX) | ✅ (100 % local) |
| Likes / réactions, commentaires texte et vocaux, amis, abonnements | Django ORM | ✅ |
| Authentification, profils | Django Auth | ✅ |

L'application fonctionne entièrement **sans aucune clé** : chaque service d'IA externe
dispose d'une solution de repli locale. Ajoute `GEMINI_API_KEY` et/ou `HF_TOKEN` dans
`.env` pour activer les modèles distants.

---

## Démarrage rapide (local)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                     # optionnel : clés Gemini / Hugging Face
.venv/bin/python manage.py migrate
.venv/bin/python manage.py setup_face_models   # modèles de reconnaissance faciale (~40 Mo)
.venv/bin/python manage.py seed_demo --admin   # données de démonstration
.venv/bin/python manage.py runserver
```

Ouvre http://127.0.0.1:8000.

| Compte de démo | Mot de passe |
|---|---|
| `nour`, `sami`, `yassine`, `lina` (ou leur e-mail `…@blink.demo`) | `blink12345` |
| `admin` (dashboard : http://127.0.0.1:8000/admin/) | `admin12345` |

> L'enregistrement vocal dans le navigateur nécessite `localhost` ou HTTPS (règle des navigateurs pour le micro).

## Déploiement (Docker + PostgreSQL)

```bash
docker compose up --build
```

- `db` : PostgreSQL 16 ; `web` : Gunicorn (workers `gthread`) + WhiteNoise pour les fichiers statiques.
- Au démarrage : migrations, modèles faciaux, et données de démo si `SEED_DEMO=1` (valeur par défaut dans `docker-compose.yml`).
- Les médias sont stockés dans le volume `/data`. Variables utiles : `SECRET_KEY`, `ALLOWED_HOSTS`,
  `CSRF_TRUSTED_ORIGINS`, `GEMINI_API_KEY`, `HF_TOKEN`, `SECURE_COOKIES=1` derrière HTTPS.
- Pour un hébergeur PaaS (Render, Railway, Fly.io…), le `Dockerfile` suffit : fournir `DATABASE_URL` et `PORT`.

## Tests

```bash
.venv/bin/python manage.py test
```

64 tests couvrent les règles de visibilité, les flux publication/réaction/commentaire,
la transcription (services IA simulés), les filtres d'images, la reconnaissance faciale
sur une vraie photo, les permissions, l'API REST et le dashboard admin.

---

## Architecture

```
Navigateur ── gabarits Django + Tailwind + JS (fetch) ──┐
                                                         │ HTTP / JSON
┌────────────────────────── Django (MVT) ────────────────▼────────────────────────┐
│  Vues génériques (ListView, DetailView, CreateView…)    API REST (DRF)          │
│  Modèles / ORM ── signaux ── tâches IA asynchrones (threads après commit)       │
│  Intégrations IA : Gemini (texte, audio) · Hugging Face (SD, Whisper) · OpenCV  │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                     PostgreSQL / SQLite  +  stockage médias (local / volume)
```

Les appels IA lents (transcription, diffusion, détection de visages) sont lancés en
arrière-plan après le commit de la transaction (`core/tasks.py`) ; l'interface suit
leur statut via l'API (`/api/transcriptions/<id>/`, `/api/generated-images/<id>/`).

### Structure du projet (une application par « gestion »)

| Application | Gestion | Modèles |
|---|---|---|
| `accounts` | Commune : utilisateurs, profils, amis, notes privées | `User`, `Profile`, `Friendship`, `Follow`, `PersonalNote` |
| `posts` | 1 — Publications + Gemini | `Post`, `Reaction`, `Comment`, `AIGeneration` |
| `audio` | 2 — Audio & transcription | `AudioPost`, `Transcription`, `AudioComment` |
| `aistudio` | 3 — IA générative d'images | `GeneratedImage`, `AIPromptTemplate`, `ImageFilter` |
| `faces` | 4 — Reconnaissance faciale & tags | `FaceEncoding`, `DetectedFace`, `TagSuggestion` |
| `core` | Accueil, recherche, notifications, modération, dashboard | `Notification`, `Report` |
| `api` | API REST (Django REST Framework) | — |

```
blink/          configuration (settings, urls, wsgi)
templates/      gabarits (base, partials réutilisables, pages par app, admin)
static/         CSS compilé (Tailwind), JS, images ; sources dans static/src/
core/templatetags/blink_tags.py   balises et filtres personnalisés
docker/, Dockerfile, docker-compose.yml   déploiement
```

### Classes génériques utilisées

`ListView` (fil, explorer, hashtags, vocaux, galerie IA, notifications),
`DetailView` (post, profil, vocal, image IA, tags), `CreateView` / `UpdateView` /
`DeleteView` (posts, commentaires, vocaux, transcriptions, filtres, modèles de prompt),
`TemplateView`, `LoginView`/`LogoutView`, mixins `LoginRequiredMixin`,
`UserPassesTestMixin` (`core/mixins.py → OwnerRequiredMixin`), et côté API
`ModelViewSet`, `ReadOnlyModelViewSet`, `GenericViewSet` + mixins.

### Moteur de gabarits

Héritage (`base.html` → pages), blocs, `{% include %}` avec paramètres (cartes de post,
lecteur audio, enregistreur), balises personnalisées : `{% icon %}`, `{% avatar %}`
(inclusion tag), `{% waveform %}`, `{% url_replace %}` ; filtres `hashtagify`
(liens #hashtags/@mentions avec échappement), `duration`, `short_since`, `get_item`.

### Dashboard admin

Site d'administration personnalisé (`core/admin_site.py`) : indicateurs clés,
histogramme des publications sur 14 jours, statistiques IA par moteur, signalements à
traiter. Chaque modèle est enregistré avec vignettes, filtres, recherche, inlines et
actions de modération (masquer des publications, désactiver des comptes, relancer
une transcription…).

### API REST (extrait)

| Méthode | URL | Rôle |
|---|---|---|
| POST | `/api/auth/token/` | obtenir un jeton (`Authorization: Token …`) |
| GET/POST | `/api/posts/` (`?feed=1`, `?auteur=`, `?hashtag=`) | fil, création |
| POST | `/api/posts/<id>/react/` | réagir (like, love, haha, sad) |
| GET/POST | `/api/posts/<id>/comments/` | commentaires |
| POST | `/api/posts/<id>/generate_ai/` | légende + hashtags IA enregistrés |
| GET | `/api/posts/<id>/faces/` | visages détectés et suggestions |
| POST | `/api/ai/caption/` | légende IA à partir d'une image (avant publication) |
| CRUD | `/api/audio-posts/`, `/api/audio-comments/`, `/api/transcriptions/` | audio |
| CRUD | `/api/generated-images/`, `/api/filters/`, `/api/prompt-templates/` | studio IA |
| GET | `/api/users/`, `/api/friendships/`, `/api/notifications/` | social |
| GET | `/api/ai/status/` | services IA actifs |

L'API navigable de DRF est disponible sur `/api/`. Elle permet de brancher un
front-end React ou une application mobile sur le même back-end.

## Charte graphique

Maya Blue `#66C5FF` · Midnight Violet `#13112A` · Soft Periwinkle `#8B7BFF` ·
Salmon `#FF7A6B` · Alice Blue `#F2F9FF` — Sora (titres) et Inter (texte).
Après modification des gabarits : `npm install && npm run build:css`.

## Équipe

Chouat Ayoub · Kardamine Jasser · Ben Taleb Ilef · Azizi Amine
