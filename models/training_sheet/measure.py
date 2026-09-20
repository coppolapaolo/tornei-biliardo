"""Come si segna una voce di scheda (ADR-067).

È la **libertà della voce**, ed è ciò che permette a una scheda sola di reggere
sia il foglio di Rōnin ASD — sei esercizi «riusciti su cinque tiri», un totale,
una soglia — sia una scheda fatta di tiri, partite e minuti su giorni A · B · C
senza nessun totale. La scheda non ha due forme: ha voci che si segnano in modi
diversi (decisione dell'utente del 19/09).

In colonna sta il **valore** (`training_sheet_item.measure` è una String): un
membro rinominato non rompe i dati già scritti — la trappola delle colonne
`db.Enum`, presidiata da `test_enum_columns_store_values.py`.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from flask_babel import lazy_gettext as _l


class SheetMeasure(str, Enum):
    """I modi di segnare una voce. L'ordine è quello in cui il foglio li propone."""

    #: Spuntata e basta: «rastrello, 10 tiri», e o l'hai fatto o no.
    DONE = "done"
    #: Riusciti su N tiri. È l'unità del foglio di carta, ed è **l'unica** che
    #: entra nella soglia della scheda (D17).
    MADE = "made"
    #: Il punteggio della prova, com'è tarato dall'esercizio.
    SCORE = "score"
    #: Partite vinte su N giocate — «contro il ghost, 5 partite».
    WINS = "wins"
    #: Minuti. Una voce a tempo non ha un esito, ha una durata.
    MINUTES = "minutes"

    @property
    def label(self):
        return _LABELS[self]

    @property
    def unit(self):
        """Come si chiama il «quanto farne»: tiri, partite, minuti."""
        return _UNITS[self]

    @property
    def is_numeric(self) -> bool:
        """La voce si registra con un numero; ``DONE`` con una spunta."""
        return self is not SheetMeasure.DONE

    @property
    def counts_toward_threshold(self) -> bool:
        """Se la voce entra nel totale della scheda, e quindi nella soglia.

        Solo «riusciti» (D17). Sommare partite vinte e minuti a dei tiri
        riusciti darebbe un numero che non vuol dire niente, e la soglia è un
        numero che qualcuno guarda per decidere un passaggio di livello.
        """
        return self is SheetMeasure.MADE

    @property
    def wants_amount(self) -> bool:
        """Se il «quanto farne» è obbligatorio.

        Col punteggio non lo è, e **non deve esserci**: quanto vale al massimo
        quella prova lo dice già l'esercizio (`Challenge.max_score`), e un
        secondo numero accanto sarebbe un secondo tetto da tenere allineato a
        mano. Con «fatto» è facoltativo: «10 tiri» lì è un promemoria, non un
        conto.
        """
        return self in (SheetMeasure.MADE, SheetMeasure.WINS, SheetMeasure.MINUTES)

    @property
    def caps_value(self) -> bool:
        """Se il valore registrato non può superare il «quanto farne».

        Riusciti e vinte sì — cinque su cinque è il massimo. I minuti no: chi
        si ferma dieci minuti in più ha fatto dieci minuti in più.
        """
        return self in (SheetMeasure.MADE, SheetMeasure.WINS)

    @classmethod
    def parse(cls, raw) -> "SheetMeasure":
        """Dal modulo o dalla colonna. L'ignoto e il vuoto sono «riusciti».

        Il ripiego è la misura del foglio di carta, quella che si usa quasi
        sempre: un valore storto non deve trasformare una voce in una spunta,
        che perderebbe il numero già registrato.
        """
        try:
            return cls(raw)
        except ValueError:
            return cls.MADE


_LABELS = {
    SheetMeasure.DONE: _l("Fatto"),
    SheetMeasure.MADE: _l("Riusciti"),
    SheetMeasure.SCORE: _l("Punteggio"),
    SheetMeasure.WINS: _l("Vinte"),
    SheetMeasure.MINUTES: _l("Minuti"),
}


class LevelUp(str, Enum):
    """Chi sancisce il gradino, quando la soglia è stata tenuta (D8).

    Sono tre risposte a una domanda sola — «chi dice che hai passato il
    livello?» — e nessuna delle tre è un ripiego dell'altra: chi si allena da
    solo non ha nessuno che confermi, e chi va in sala da un maestro non vuole
    che lo decida un conteggio.

    In colonna sta il **valore**, come per `SheetMeasure`.
    """

    #: La scheda non è fatta a livelli: non c'è nessun gradino da passare.
    NONE = "none"
    #: Lo sancisce la soglia stessa, alla seduta in cui viene tenuta.
    AUTO = "auto"
    #: Lo sancisce un istruttore fra quelli che leggono la scheda.
    INSTRUCTOR = "instructor"

    @property
    def label(self):
        return _LEVEL_UP_LABELS[self]

    @property
    def hint(self):
        return _LEVEL_UP_HINTS[self]

    @classmethod
    def parse(cls, raw) -> "LevelUp":
        """Dal modulo o dalla colonna. L'ignoto è «alla soglia».

        Il ripiego è il comportamento che la scheda aveva prima che questa
        colonna esistesse: la fine seduta diceva già «gradino raggiunto».
        """
        try:
            return cls(raw)
        except ValueError:
            return cls.AUTO


_LEVEL_UP_LABELS = {
    LevelUp.NONE: _l("Nessuno"),
    LevelUp.AUTO: _l("La soglia"),
    LevelUp.INSTRUCTOR: _l("Un istruttore"),
}

_LEVEL_UP_HINTS = {
    LevelUp.NONE: _l("La scheda non è fatta a livelli."),
    LevelUp.AUTO: _l("Tenuta la soglia, il livello è superato."),
    LevelUp.INSTRUCTOR: _l("Te lo conferma chi legge la scheda."),
}


_UNITS = {
    SheetMeasure.DONE: _l("tiri"),
    SheetMeasure.MADE: _l("tiri"),
    SheetMeasure.SCORE: _l("tiri"),
    SheetMeasure.WINS: _l("partite"),
    SheetMeasure.MINUTES: _l("minuti"),
}

#: Quanto può valere il «quanto farne» di una voce. Il tetto non è del dominio:
#: è ciò che si regge a fare in una seduta, e un numero incollato per sbaglio
#: diventerebbe una griglia di cento caselle.
MIN_AMOUNT = 1
MAX_AMOUNT = 999

#: Quante voci può avere una scheda. Stessa ragione del tetto qui sopra.
MAX_ITEMS = 40


def amount_label(measure: SheetMeasure, amount: Optional[int]) -> str:
    """«5 tiri», «5 partite», «20 minuti» — o niente, se non c'è un numero."""
    from flask_babel import gettext as _

    if amount is None:
        return ""
    if measure is SheetMeasure.WINS:
        return _("%(n)s partite", n=amount)
    if measure is SheetMeasure.MINUTES:
        return _("%(n)s minuti", n=amount)
    return _("%(n)s tiri", n=amount)


__all__ = [
    "SheetMeasure",
    "LevelUp",
    "MIN_AMOUNT",
    "MAX_AMOUNT",
    "MAX_ITEMS",
    "amount_label",
]
