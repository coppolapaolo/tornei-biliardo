"""Cosa deve essere chiuso prima di avviare il turno successivo.

`SPECIFICHE.md`, «Cosa deve essere chiuso prima del turno successivo»
(2026-09-13). Con le strategie che costruiscono ogni turno sulla classifica il
turno dopo parte solo quando quello prima e' chiuso **davvero**:

* le partite: tutte concluse. Fino al 2026-09-13 lo controllavano le due route
  che avviano il turno ma non il servizio, quindi ogni altra strada — la
  simulazione di una prova, uno script — poteva saltarlo;
* la **prova al posto della X** convalidata dal direttore. Il match della X
  nasce gia' concluso, quindi il turno risultava chiuso anche con la prova da
  convalidare: e' come una partita non validata, perche' il suo punteggio e'
  la differenza triangoli del turno, e un turno Amalfi calcolato senza
  abbinerebbe su una classifica che non c'e';
* gli **esercizi fra i turni** agganciati a quel turno: almeno un tentativo
  per ogni iscritto ancora in gara. Chi ha dato forfait non e' piu' al tavolo
  e non ha niente da registrare.

Con la strategia casuale i turni nascono tutti all'avvio: non c'e' un turno da
avviare, e prove ed esercizi non bloccano nessuno.

Una domanda sola, tre lettori: `RoundCreationService.start_next_round` che
rifiuta, la fascia del direttore (`comando_per`) che annuncia il comando
bloccato col conto di cosa manca, e il comando che toglie un tentativo di
esercizio, che vale finche' il turno dopo non e' partito.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask_babel import gettext as _
from flask_babel import ngettext

from models.base import db
from models.exceptions import ConflictError
from models.status_enum import MatchStatus


@dataclass(frozen=True)
class PendenzeTurno:
    """Quel che manca per considerare chiuso il turno `turno`."""

    turno: int
    partite_aperte: int = 0
    prove_x: int = 0
    #: Righe «da fare»: una per esercizio e per giocatore senza tentativi.
    esercizi: int = 0

    @property
    def bloccano(self) -> bool:
        return bool(self.partite_aperte or self.prove_x or self.esercizi)


def _turni_pregenerati(gara: Any) -> bool:
    """La strategia casuale: tutti i turni nascono all'avvio."""
    return bool(gara.creates_all_rounds_at_startup())


def pendenze_del_turno(gara: Any, turno: int) -> PendenzeTurno:
    """Cosa tiene aperto il turno `turno` di questa gara."""
    if turno < 1 or _turni_pregenerati(gara):
        return PendenzeTurno(turno=turno)

    from models.match.models import Match

    partite = Match.query.filter_by(gara_id=gara.id, round_number=turno).all()
    aperte = sum(
        1 for m in partite if not m.is_bye and not MatchStatus.is_finished(m.status)
    )
    return PendenzeTurno(
        turno=turno,
        partite_aperte=aperte,
        prove_x=_prove_x_da_convalidare(gara, turno, partite),
        esercizi=_esercizi_da_registrare(gara, turno),
    )


def _forfait(gara_id: int) -> set:
    from models.competition.withdraw_policy_service import WithdrawPolicyService

    return WithdrawPolicyService.get_forfeit_user_ids(gara_id)


def _prove_x_da_convalidare(gara: Any, turno: int, partite: list) -> int:
    from models.matchmaking.configuration import OddNumberPolicy

    if gara.odd_number_policy != OddNumberPolicy.BYE_WITH_CHALLENGE.value:
        return 0
    x = [m for m in partite if m.is_bye and m.player1_id is not None]
    if not x:
        return 0

    from models.competition.gara_bye_challenge import GaraByeChallenge

    convalidate = {
        p.user_id
        for p in GaraByeChallenge.query.filter_by(
            gara_id=gara.id, round_number=turno
        ).filter(GaraByeChallenge.validated_at.isnot(None))
    }
    fuori = _forfait(gara.id)
    return sum(
        1 for m in x if m.player1_id not in convalidate and m.player1_id not in fuori
    )


def _esercizi_da_registrare(gara: Any, turno: int) -> int:
    if not gara.ammette_esercizi_fra_i_turni:
        return 0

    from models.competition.gara_challenge import (
        GaraChallenge,
        GaraChallengeAttempt,
    )
    from models.competition.models import Inscription

    esercizi = GaraChallenge.query.filter_by(
        gara_id=gara.id, round_number=turno, is_active=True
    ).all()
    if not esercizi:
        return 0

    in_gara = {
        i.user_id
        for i in Inscription.query.filter_by(gara_id=gara.id)
        .filter(Inscription.is_withdrawn.isnot(True))
        .filter(Inscription.is_waitlist.isnot(True))
        .filter(Inscription.is_forfeit.isnot(True))
    }
    fatti = set(
        db.session.query(
            GaraChallengeAttempt.gara_challenge_id, GaraChallengeAttempt.user_id
        )
        .filter(
            GaraChallengeAttempt.gara_challenge_id.in_([e.id for e in esercizi]),
            GaraChallengeAttempt.completed.is_(True),
        )
        .distinct()
        .all()
    )
    return sum(1 for e in esercizi for u in in_gara if (e.id, u) not in fatti)


def turno_successivo_partito(gara: Any, turno: int) -> bool:
    """Il turno dopo `turno` e' gia' avviato: quel turno non si tocca piu'.

    Con la strategia casuale i turni esistono tutti dall'inizio, e nessuno di
    loro e' «partito» nel senso che conta qui: la risposta e' sempre no.
    """
    if _turni_pregenerati(gara):
        return False

    from models.match.models import Match

    return (
        db.session.query(Match.id)
        .filter(Match.gara_id == gara.id, Match.round_number > turno)
        .first()
        is not None
    )


def descrivi(pendenze: PendenzeTurno) -> list:
    """Le cose che mancano, in parole, nell'ordine in cui il direttore le fa."""
    parti = []
    if pendenze.partite_aperte:
        parti.append(
            ngettext(
                "%(num)d partita ancora aperta",
                "%(num)d partite ancora aperte",
                pendenze.partite_aperte,
            )
        )
    if pendenze.prove_x:
        parti.append(
            ngettext(
                "%(num)d prova della X da convalidare",
                "%(num)d prove della X da convalidare",
                pendenze.prove_x,
            )
        )
    if pendenze.esercizi:
        parti.append(
            ngettext(
                "%(num)d esercizio da registrare",
                "%(num)d esercizi da registrare",
                pendenze.esercizi,
            )
        )
    return parti


def verifica_turno_chiuso(gara: Any, turno_da_avviare: int) -> None:
    """Solleva `ConflictError` se il turno prima di `turno_da_avviare` e' aperto."""
    if turno_da_avviare <= 1:
        return
    pendenze = pendenze_del_turno(gara, turno_da_avviare - 1)
    if not pendenze.bloccano:
        return
    raise ConflictError(
        _(
            "Prima di avviare il turno %(n)s: %(cosa)s.",
            n=turno_da_avviare,
            cosa=", ".join(descrivi(pendenze)),
        )
    )


__all__ = [
    "PendenzeTurno",
    "descrivi",
    "pendenze_del_turno",
    "turno_successivo_partito",
    "verifica_turno_chiuso",
]
