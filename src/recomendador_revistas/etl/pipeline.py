"""Punto de entrada público del pipeline ETL."""

from .runner import ejecutar_gold, ejecutar_papers, ejecutar_silver, main, validar_bronze

__all__ = ["main", "ejecutar_gold", "ejecutar_papers", "ejecutar_silver", "validar_bronze"]