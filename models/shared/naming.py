"""Normalizzazione dei nomi negli elenchi definiti dall'utente.

Squadre e categorie hanno lo stesso problema: sono elenchi che le persone
compilano scrivendo, e "Circolo  X" / "circolo x" — o "B" / " b " — sono la
stessa voce. La forma normalizzata è ciò su cui il DB impone l'unicità, quindi
deve essere **una sola**: se i due elenchi normalizzassero in modo diverso, si
comporterebbero in modo diverso davanti allo stesso refuso.
"""

from __future__ import annotations


def normalize_list_name(name: str) -> str:
    """Forma normalizzata usata per l'unicità e per il confronto.

    Minuscole e spazi interni compattati. Serve a prevenire i doppioni al
    momento della scrittura invece di doverli rincorrere dopo.
    """
    return " ".join((name or "").split()).lower()


def clean_display_name(name: str) -> str:
    """Il nome come va mostrato: spazi compattati, maiuscole rispettate."""
    return " ".join((name or "").split())
