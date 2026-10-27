FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MEDIA_ROOT=/data/media \
    FACE_MODELS_DIR=/app/ml_models

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Le CSS Tailwind est déjà compilé dans static/css/app.css (npm run build:css).
RUN SECRET_KEY=build DEBUG=0 python manage.py collectstatic --noinput \
    && (python manage.py setup_face_models || echo "Modèles faciaux : téléchargement au démarrage")

RUN useradd --create-home blink && mkdir -p /data/media /app/ml_models && chown -R blink /data /app
USER blink

VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
