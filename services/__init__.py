"""Services métier partagés (calculs sectoriels, alertes).

Ce paquet est importé par api/routers/v1/sectors.py — le __init__.py
garantit un import fiable quel que soit le mode de lancement
(uvicorn, passenger, tests), sans dépendre du namespace package implicite.
"""
