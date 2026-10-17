"""Bibliothèque d'analyses (DAT-09 à DAT-19) : chaque module enregistre son opération."""

from app.analytics.operations import (  # noqa: F401
    aberrantes,
    anciennete,
    benford,
    doublons,
    extraction,
    jointure,
    rapprochement,
    sequence,
    stratification,
    synthese,
)
from app.analytics.operations.base import REGISTRY, AnalysisError, Operation, validate

__all__ = ["REGISTRY", "AnalysisError", "Operation", "validate"]
