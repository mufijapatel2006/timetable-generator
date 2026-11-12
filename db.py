"""
Database connector module.
Routes database calls to FirebaseService.
"""

from firebase_service import service

def get_db():
    return service