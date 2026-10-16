"""
database.py - FACHADA DE ACCESO AL NÚCLEO TRANSACCIONAL (DECRETÓMETRO 2.0)
Mantiene compatibilidad binaria y funcional absoluta con todas las páginas de Streamlit,
redireccionando las llamadas hacia los repositorios especializados de db_core/.
Fase 3: Refactorización Estructural con Patrón Fachada.
"""
from db_core import *
import db_core

__all__ = db_core.__all__
