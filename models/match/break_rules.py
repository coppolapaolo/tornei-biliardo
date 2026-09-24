"""Chi comincia la partita, e chi apre ogni triangolo (ADR-056).

Due domande distinte, e il regolamento FIBiS le tiene distinte:

* la **regola di inizio** (`StartRule`) dice *come* si decide chi apre il primo
  triangolo — d'ufficio il primo giocatore, oppure con l'acchito;
* la **regola di apertura** (`BreakRule`) dice come il tiro di apertura passa
  da un triangolo al successivo.

Sull'acchito, «Regole generali pool» 1.2: «L'acchito è il primo tiro della
partita e determina l'ordine di gioco. Il giocatore che vince l'acchito
**sceglie chi** eseguirà il tiro di apertura.» Sono quindi **due** domande —
chi ha vinto, e chi apre — e la seconda può rispondere l'avversario. La
`SPECIFICHE.md` lasciava intendere che chi vince cominci: emendata il
2026-08-28 (riga 131 e nota in coda alla sezione «Match»).

Nota lessicale, dallo stesso regolamento: «acchito» ha **due** significati — il
primo tiro che decide l'ordine (1.2) e la preparazione delle bilie nel
triangolo (1.4 «Acchito delle bilie»). Qui vale sempre il primo.

`break_player_for_rack` è una funzione pura: non tocca il DB e non conosce i
modelli. Serve a due chiamanti che devono per forza rispondere allo stesso
modo — chi **registra** il triangolo (e ci scrive sopra `break_player_id`) e
chi **disegna** la pastiglia SPACCA per il triangolo ancora da giocare. Finché
la risposta viene da qui, le due non possono divergere.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence

from flask_babel import gettext as _

__all__ = [
    "StartRule",
    "BreakRule",
    "DEFAULT_START_RULE",
    "DEFAULT_BREAK_RULE",
    "LEGACY_START_RULE",
    "break_player_for_rack",
]


class _StrEnum(str, Enum):
    """Enum di stringhe: compatibile con JSON, logging e confronti diretti."""

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)


class StartRule(_StrEnum):
    """Come si decide chi esegue il tiro di apertura del **primo** triangolo."""

    #: Apre il primo giocatore della coppia, senza chiedere niente a nessuno.
    #: Era il default fino al 2026-09-24, e resta il ripiego di ciò che è nato
    #: prima dell'ADR-056 senza una regola (`LEGACY_START_RULE`).
    FIRST_PLAYER = "first_player"
    #: Si tira l'acchito. Il segnapunti fa le due domande del regolamento —
    #: chi ha vinto, e chi apre — prima di lasciar segnare il primo triangolo.
    #: È il default: nei tornei si comincia così.
    LAG = "lag"

    @property
    def display_name(self) -> str:
        return {
            StartRule.FIRST_PLAYER: _("Primo giocatore"),
            StartRule.LAG: _("Acchito"),
        }.get(self, self.value)

    @property
    def description(self) -> str:
        return {
            StartRule.FIRST_PLAYER: _("Apre il primo dei due, senza sorteggio."),
            StartRule.LAG: _(
                "Si tira l'acchito: chi vince sceglie chi esegue "
                "il tiro di apertura, e può scegliere l'avversario."
            ),
        }.get(self, "")

    @classmethod
    def normalize(cls, value) -> "Optional[StartRule]":
        """Il membro corrispondente, o ``None`` sul valore ignoto.

        Il ripiego lo sceglie il chiamante: nasconderlo qui è esattamente il
        modo in cui un disallineamento resta invisibile per mesi (vedi
        `Discipline.normalize`).
        """
        if isinstance(value, cls):
            return value
        if value is None:
            return None
        try:
            return cls(str(value))
        except ValueError:
            return None


class BreakRule(_StrEnum):
    """Come passa il tiro di apertura da un triangolo al successivo."""

    #: Apre chi ha vinto il triangolo precedente («break continuo»).
    WINNER_BREAKS = "winner_breaks"
    #: Tiri di apertura alternati: la regola standard FIBiS.
    ALTERNATE = "alternate"
    #: Alternati **ogni due** triangoli. Nuova con l'ADR-056: non esisteva né
    #: nella specifica né nel codice.
    ALTERNATE_TWO = "alternate_two"
    #: Apre chi ha perso il triangolo precedente.
    LOSER_BREAKS = "loser_breaks"

    @property
    def display_name(self) -> str:
        return {
            BreakRule.WINNER_BREAKS: _("Spacca chi ha vinto"),
            BreakRule.ALTERNATE: _("A turno"),
            BreakRule.ALTERNATE_TWO: _("A turno ogni due"),
            BreakRule.LOSER_BREAKS: _("Spacca chi ha perso"),
        }.get(self, self.value)

    @property
    def description(self) -> str:
        return {
            BreakRule.WINNER_BREAKS: _("Apre chi ha vinto il triangolo prima."),
            BreakRule.ALTERNATE: _(
                "Tiri di apertura alternati, la regola standard FIBiS."
            ),
            BreakRule.ALTERNATE_TWO: _("Due triangoli a testa, poi si cambia."),
            BreakRule.LOSER_BREAKS: _("Apre chi ha perso il triangolo prima."),
        }.get(self, "")

    @classmethod
    def normalize(cls, value) -> "Optional[BreakRule]":
        """Il membro corrispondente, o ``None`` sul valore ignoto."""
        if isinstance(value, cls):
            return value
        if value is None:
            return None
        try:
            return cls(str(value))
        except ValueError:
            return None


#: Radice delle due catene di ereditarietà. `alternate` era già il default
#: della colonna sulle sfide individuali dal 2026-02: cambiarlo qui
#: cambierebbe il passato di quelle partite.
#:
#: La regola di inizio è l'acchito dal 2026-09-24 (rilievo della gara del
#: 23/09): è quella che i moduli propongono e che le righe nuove ricevono.
DEFAULT_START_RULE = StartRule.LAG
#: Cosa vuol dire una regola di inizio **assente** — una gara senza campionato
#: nata prima dell'ADR-056, un match staccato dalla sua gara. Per quelle righe
#: NULL ha sempre voluto dire «apre il primo giocatore», e deve continuare a
#: dirlo: col default nuovo, una gara già cominciata si sarebbe trovata le
#: domande dell'acchito a metà. Non è il default, e non va usato come tale.
LEGACY_START_RULE = StartRule.FIRST_PLAYER
DEFAULT_BREAK_RULE = BreakRule.ALTERNATE


def break_player_for_rack(
    rule,
    rack_index: int,
    first_breaker_id: Optional[int],
    other_player_id: Optional[int],
    previous_winners: Sequence[Optional[int]],
) -> Optional[int]:
    """Chi esegue il tiro di apertura del triangolo ``rack_index`` (0 = il primo).

    Args:
        rule: un `BreakRule`, o il suo valore persistito. Un valore ignoto
            ricade su `DEFAULT_BREAK_RULE` — qui il ripiego è giusto, perché il
            chiamante è un segnapunti al tavolo: preferisce una pastiglia
            plausibile a un'eccezione.
        rack_index: indice del triangolo, 0-based.
        first_breaker_id: chi apre il **primo** triangolo. ``None`` quando
            l'acchito non è ancora stato registrato: allora non si sa chi apra
            nessuno dei triangoli, e la risposta è ``None`` per tutti.
        other_player_id: l'altro dei due.
        previous_winners: i vincitori dei triangoli già giocati, in ordine.
            Serve solo alle due regole che guardano indietro; le alternate lo
            ignorano, ed è per questo che restano corrette anche quando un
            triangolo viene annullato.

    Returns:
        L'id di chi apre, oppure ``None`` se non è determinabile.
    """
    if first_breaker_id is None:
        return None
    if rack_index <= 0:
        return first_breaker_id

    resolved = BreakRule.normalize(rule) or DEFAULT_BREAK_RULE

    def altro(player_id: Optional[int]) -> Optional[int]:
        if player_id is None:
            return None
        return other_player_id if player_id == first_breaker_id else first_breaker_id

    if resolved in (BreakRule.WINNER_BREAKS, BreakRule.LOSER_BREAKS):
        # Chi ha vinto il triangolo prima. Se non lo sappiamo — storico
        # incompleto, triangoli annullati — la pastiglia non si inventa niente.
        if rack_index - 1 >= len(previous_winners):
            return None
        previous_winner = previous_winners[rack_index - 1]
        if previous_winner is None:
            return None
        if resolved is BreakRule.WINNER_BREAKS:
            return previous_winner
        return altro(previous_winner)

    if resolved is BreakRule.ALTERNATE_TWO:
        return (
            first_breaker_id if (rack_index // 2) % 2 == 0 else altro(first_breaker_id)
        )

    return first_breaker_id if rack_index % 2 == 0 else altro(first_breaker_id)
