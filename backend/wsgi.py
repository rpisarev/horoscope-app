"""Gunicorn factory entry point; importing this module does not create an app."""

from app import create_app

__all__ = ["create_app"]
