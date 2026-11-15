"""Objetos de Flask que se crean una vez y se conectan en la fábrica de la app."""

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()
