"""Che cosa può volere chi si pone un obiettivo (#316, #175).

Tre forme, e sono le tre che l'utente ha nominato guardando il disegno: un
risultato su un esercizio, un'abilità che sale, la costanza. Non sono tre
sottoclassi né tre tabelle — sono tre modi di leggere gli stessi numeri, e
quello che cambia è **da dove si legge il progresso**, non com'è fatta la riga.

Il valore sta in colonna, in una ``String``: un membro rinominato non rompe i
dati già scritti (presidio `test_enum_columns_store_values.py`).
"""

from __future__ import annotations

from flask_babel import lazy_gettext as _l

from ..status_enum import _StrEnum

#: Quanti obiettivi attivi per volta. Tre perché un elenco di obiettivi non è
#: un elenco di cose da fare: oltre, smette di essere una scelta e torna a
#: essere il catalogo.
MAX_ATTIVI = 3

#: Su quante prove si fa la media, quando l'obiettivo è «e tenerlo».
FINESTRA_MEDIA = 5
#: Quante volte a settimana propone il modulo, e i limiti.
MIN_VOLTE = 1
MAX_VOLTE = 14
#: Per quante settimane di fila. Una sola non è costanza.
MIN_SETTIMANE = 2
MAX_SETTIMANE = 52


class GoalKind(_StrEnum):
    """Le tre domande."""

    ESERCIZIO = "esercizio"
    ABILITA = "abilita"
    COSTANZA = "costanza"

    @property
    def label(self):
        return {
            GoalKind.ESERCIZIO: _l("Un risultato su un esercizio"),
            GoalKind.ABILITA: _l("Un'abilità che sale"),
            GoalKind.COSTANZA: _l("La costanza"),
        }[self]

    @property
    def hint(self):
        return {
            GoalKind.ESERCIZIO: _l("arrivare a un punteggio, e tenerlo"),
            GoalKind.ABILITA: _l("portare una categoria alla banda successiva"),
            GoalKind.COSTANZA: _l("allenarmi con una certa frequenza"),
        }[self]

    @classmethod
    def parse(cls, value: object):
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return None


class GoalRule(_StrEnum):
    """Quando un obiettivo su un esercizio vale raggiunto.

    La differenza fra le due non è di severità, è di **che cosa si vuole**: la
    media dice «lo so fare», una volta sola dice «ci sono arrivato». Chi punta
    a un record vuole la seconda, chi punta a un livello la prima.
    """

    MEDIA = "media"
    UNA_VOLTA = "una_volta"

    @property
    def label(self):
        return {
            GoalRule.MEDIA: _l("Media delle ultime %(n)s prove", n=FINESTRA_MEDIA),
            GoalRule.UNA_VOLTA: _l("Basta una volta"),
        }[self]

    @classmethod
    def parse(cls, value: object) -> "GoalRule":
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return cls.MEDIA


class GoalDeadline(_StrEnum):
    """Entro quando. È una scelta a tre voci, non una data da scrivere.

    Una data precisa su un obiettivo di allenamento è una finta precisione:
    nessuno decide di arrivare a otto su dieci entro il 14 novembre.
    """

    MESE = "mese"
    TRIMESTRE = "trimestre"
    NESSUNA = "nessuna"

    @property
    def giorni(self):
        return {GoalDeadline.MESE: 30, GoalDeadline.TRIMESTRE: 90}.get(self)

    @property
    def label(self):
        return {
            GoalDeadline.MESE: _l("Un mese"),
            GoalDeadline.TRIMESTRE: _l("Tre mesi"),
            GoalDeadline.NESSUNA: _l("Senza scadenza"),
        }[self]

    @classmethod
    def parse(cls, value: object) -> "GoalDeadline":
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return cls.NESSUNA


__all__ = [
    "GoalDeadline",
    "GoalKind",
    "GoalRule",
    "FINESTRA_MEDIA",
    "MAX_ATTIVI",
    "MAX_SETTIMANE",
    "MAX_VOLTE",
    "MIN_SETTIMANE",
    "MIN_VOLTE",
]
