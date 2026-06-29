import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

"""
NOTE — compatibilité WSGI / Passenger
=======================================
FastAPI est un framework ASGI. Passenger attend une app WSGI.
En production, le backend est servi directement par uvicorn (port 8001) —
voir deploy.sh pour la commande nohup.

Ce fichier sert de fallback pour le panneau d'administration Passenger.
Pour une compatibilité WSGI complète, installer a2wsgi
(pip install a2wsgi) puis :

    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(app)
"""

from src.main import app as application
