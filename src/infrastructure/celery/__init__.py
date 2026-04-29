"""Celery package entry point.

Expose `celery_app` so the CLI can discover the app with:
    celery -A src.infrastructure.celery worker ...
"""

from src.infrastructure.celery.app import celery_app

__all__ = ["celery_app"]
