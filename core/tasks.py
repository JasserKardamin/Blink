"""
Exécution asynchrone légère des traitements IA.

Les appels aux API d'IA peuvent prendre plusieurs secondes : on les lance dans
un thread après le commit de la transaction pour ne pas bloquer la requête HTTP
(« Latence API → traitement asynchrone »). L'interface interroge ensuite
l'API REST pour suivre le statut.
"""
import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction

logger = logging.getLogger("blink.tasks")


def _run(func, args, kwargs):
    close_old_connections()
    try:
        func(*args, **kwargs)
    except Exception:  # noqa: BLE001 - une tâche ne doit jamais faire tomber le serveur
        logger.exception("Échec de la tâche %s", getattr(func, "__name__", func))
    finally:
        close_old_connections()


def run_async(func, *args, **kwargs):
    """Planifie `func(*args, **kwargs)` après le commit de la transaction courante."""
    if settings.BLINK_SYNC_TASKS:
        transaction.on_commit(lambda: _run_sync(func, args, kwargs))
        return

    def start():
        threading.Thread(target=_run, args=(func, args, kwargs), daemon=True).start()

    transaction.on_commit(start)


def _run_sync(func, args, kwargs):
    try:
        func(*args, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("Échec de la tâche %s", getattr(func, "__name__", func))
