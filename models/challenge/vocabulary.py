"""I due vocabolari dell'esercizio: che cosa allena e con che gesto (ADR-065).

Un esercizio si descrive su **due assi indipendenti**, e un esercizio può avere
zero, una o più voci di ciascuno:

* l'**abilità** dice che cosa si sta allenando — la risposta a «su cosa devo
  lavorare?»;
* il **gesto** dice con quale colpo — la risposta a «come si tira?».

Lo stesso draw serve a un esercizio di posizione e a uno di difesa: per questo
non sono una lista sola. I radar dell'andamento sono due, uno per asse.

**Fissi di piattaforma.** Le voci le decide la piattaforma, non l'autore
dell'esercizio: un vocabolario che ognuno allunga a piacere smette di essere un
filtro nel giro di un mese («Posizione», «posizionamento», «gioco di pos.»).
Ciò che è libero dell'autore sta altrove, in ``Challenge.family``.

Il valore è ciò che finisce su disco, in una colonna ``String`` — mai in una
``db.Enum``, che senza ``values_callable`` salverebbe il *nome* del membro e
renderebbe ogni rinomina una migrazione dei dati (incidente del 2026-08-17). Il
nome mostrato è una stringa tradotta, non il valore ripulito.

L'ordine di dichiarazione **è** l'ordine in cui le voci compaiono, nel modulo e
sulle card: due esercizi con le stesse voci mostrano le stesse etichette nello
stesso ordine.
"""

from __future__ import annotations

from typing import Optional, TypeVar

from flask_babel import gettext as _

from ..status_enum import _StrEnum

# Un esercizio che allena tutto non dice niente a chi filtra: al più tre
# abilità. I gesti non hanno tetto — sono un fatto («qui si tira di draw e di
# forza»), non una scelta di cosa mettere in evidenza.
MAX_ABILITA = 3

# Il livello dichiarato: 1 per chi comincia, 5 per chi gioca da anni. È
# **dichiarato** dall'autore; quello misurato dai risultati (#174) gli starà
# accanto, non al suo posto.
MIN_LEVEL = 1
MAX_LEVEL = 5

_V = TypeVar("_V", bound="_Vocabolario")


class _Vocabolario(_StrEnum):
    """Base comune: ``normalize`` e le scelte per i moduli."""

    @property
    def display_name(self) -> str:  # pragma: no cover - ridefinita sotto
        return self.value

    @classmethod
    def normalize(cls: type[_V], value: object) -> Optional[_V]:
        """Il membro corrispondente, o ``None`` se il valore non è del vocabolario.

        Il ripiego spetta a chi chiama: un valore ignoto scartato in silenzio è
        il modo in cui un refuso in un modulo diventa un esercizio senza
        categoria.
        """
        if isinstance(value, cls):
            return value
        if not value:
            return None
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return None

    @classmethod
    def get_choices(cls) -> list[tuple[str, str]]:
        return [(voce.value, voce.display_name) for voce in cls]


class CategoryAxis(_StrEnum):
    """Su quale dei due assi sta una voce di ``challenge_category``."""

    ABILITA = "abilita"
    GESTO = "gesto"


class Abilita(_Vocabolario):
    """Che cosa allena l'esercizio."""

    FONDAMENTALI = "fondamentali"
    TIRO = "tiro"
    BATTENTE = "battente"
    POSIZIONE = "posizione"
    SPONDE = "sponde"
    DIFESA = "difesa"
    SPACCATA = "spaccata"

    @property
    def display_name(self) -> str:
        nomi = {
            Abilita.FONDAMENTALI: _("Fondamentali"),
            Abilita.TIRO: _("Tiro"),
            Abilita.BATTENTE: _("Battente"),
            Abilita.POSIZIONE: _("Posizione"),
            Abilita.SPONDE: _("Sponde"),
            Abilita.DIFESA: _("Difesa"),
            Abilita.SPACCATA: _("Spaccata"),
        }
        return nomi[self]


class Gesto(_Vocabolario):
    """Con quale colpo si esegue.

    I nomi restano quelli che si dicono al tavolo, in inglese anche in italiano:
    passano comunque da ``gettext``, così una terza lingua non tocca il codice.
    """

    STOP = "stop"
    STUN = "stun"
    FOLLOW = "follow"
    DRAW = "draw"
    SPIN = "spin"
    FORZA = "forza"
    BANK = "bank"
    KICK = "kick"
    JUMP = "jump"
    MASSE = "masse"

    @property
    def display_name(self) -> str:
        nomi = {
            Gesto.STOP: _("stop"),
            Gesto.STUN: _("stun"),
            Gesto.FOLLOW: _("follow"),
            Gesto.DRAW: _("draw"),
            Gesto.SPIN: _("spin"),
            Gesto.FORZA: _("forza"),
            Gesto.BANK: _("bank"),
            Gesto.KICK: _("kick"),
            Gesto.JUMP: _("jump"),
            Gesto.MASSE: _("massé"),
        }
        return nomi[self]
