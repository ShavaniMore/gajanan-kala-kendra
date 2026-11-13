"""Entry point for a real web server:   gunicorn wsgi:app   (Linux)   or   waitress-serve wsgi:app   (Windows)"""
from app import app
from database import init_db

init_db()
