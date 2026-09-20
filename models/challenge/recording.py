"""Come si registra una prova di un esercizio (ADR-066).

È una proprietà **dell'esercizio**, non una scelta di chi si allena: due prove
dello stesso esercizio devono potersi confrontare, e un 37 fatto di venti colpi
col bersaglio non si confronta con un 37 scritto a mano.

In colonna sta il **valore** (`challenge.recording_mode` è una String): un
membro rinominato non rompe i dati già scritti — la trappola delle colonne
`db.Enum`, presidiata da `test_enum_columns_store_values.py`.
"""

from __future__ import annotations

from enum import Enum

from flask_babel import lazy_gettext as _l


class RecordingMode(str, Enum):
    """I modi di registrare. L'ordine è quello in cui il modulo li propone."""

    #: Il punteggio, o l'esito, scritto a fine prova. È il modo di sempre, e
    #: copre sia gli esercizi a punteggio sia quelli riuscita-o-no.
    TOTAL = "total"
    #: Colpo per colpo: ogni colpo ha un esito e, se imbucato, il punto in cui
    #: si è fermata la battente. Il punteggio discende dai colpi.
    SHOTS = "shots"

    @property
    def label(self):
        return _LABELS[self]

    @property
    def is_sequence(self) -> bool:
        """La prova è una sequenza di colpi, non un numero scritto alla fine."""
        return self is not RecordingMode.TOTAL

    @classmethod
    def parse(cls, raw) -> "RecordingMode":
        """Dal modulo o dalla colonna. L'ignoto e il vuoto sono il modo di sempre."""
        try:
            return cls(raw)
        except ValueError:
            return cls.TOTAL


_LABELS = {
    RecordingMode.TOTAL: _l("Col totale"),
    RecordingMode.SHOTS: _l("Colpo per colpo"),
}

#: Quanti colpi può avere una prova. Il tetto non è del dominio: è ciò che si
#: regge a registrare in piedi accanto al tavolo.
MIN_SHOTS = 1
MAX_SHOTS = 100

__all__ = ["RecordingMode", "MIN_SHOTS", "MAX_SHOTS"]
