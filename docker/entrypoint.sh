#!/bin/sh
set -e

# Attend que la base soit prête (PostgreSQL démarre parfois après le conteneur web).
until python manage.py migrate --noinput; do
  echo "Base de données indisponible, nouvel essai dans 2 s…"
  sleep 2
done

python manage.py setup_face_models || echo "Modèles faciaux indisponibles : tags manuels uniquement."

if [ "${SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo --admin
fi

exec gunicorn blink.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --worker-class gthread --workers ${GUNICORN_WORKERS:-2} --threads 4 \
  --timeout 180 --access-logfile -
