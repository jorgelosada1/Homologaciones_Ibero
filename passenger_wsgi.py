"""Punto de entrada para hostings con Phusion Passenger (cPanel → Setup Python App)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as application  # noqa: E402,F401
