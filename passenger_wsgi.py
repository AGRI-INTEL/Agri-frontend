import os
import sys

# Ajouter le répertoire src au chemin de recherche
sys.path.insert(0, os.path.dirname(__file__))

from src.main import app as application
