from __future__ import annotations
from typing import Sequence, Callable, List, Set

from .base import PairingStrategy, Pairing, ValidationResult

# Solo letture dal dominio (nessun side‑effect)
from models import Inscription, RoundClassification, PlayerEncounter


class AmalfiStrategy(PairingStrategy):
    """Adapter per l'engine Amalfi esistente.

    Il costruttore accetta due callable iniettati per evitare dipendenze forti:
      - `validate_fn(prova) -> tuple[bool, tuple[str, ...]]`
      - `propose_fn(prova, round_number) -> list[tuple[int, ...]]`

    Dove `propose_fn` restituisce solo la *forma* degli abbinamenti
    (id giocatori per match/trio);
    l'Adapter converte in Value Objects `Pairing`.

    Se l'engine legacy esegue direttamente i side‑effect
    (creazione Match, PlayerEncounter),
    questa Strategy si limita a riflettere il risultato in `Pairing`.

    Sprint 2: aggiunta `preview()` **senza side‑effects**.
    """

    name = "Amalfi"

    def __init__(
        self,
        *,
        validate_fn: Callable[[object], tuple[bool, tuple[str, ...]]],
        propose_fn: Callable[[object, int], list[tuple[int, ...]]],
    ) -> None:
        self._validate_fn = validate_fn
        self._propose_fn = propose_fn

    # ── validate ──────────────────────────────────────────────────────────────
    def validate(self, prova: object) -> ValidationResult:
        ok, messages = self._validate_fn(prova)
        return ValidationResult(ok=ok, messages=messages)

    # ── preview (no IO) ──────────────────────────────────────────────────────
    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Calcola gli abbinamenti *in anteprima* senza scrivere su DB.
        Ritorna una lista di `Pairing` coerenti con l'algoritmo Amalfi.
        """
        if round_number < 1:
            return []

        # Round 1: usa gli iscritti ordinati in modo deterministico
        if round_number == 1:
            inscriptions = (
                Inscription.query.filter_by(prova_id=prova.id)
                .order_by(Inscription.id.asc())
                .all()
            )
            players = [insc.user_id for insc in inscriptions]

            pairings: List[Pairing] = []
            for i in range(0, len(players), 2):
                if i + 1 < len(players):
                    pairings.append(
                        Pairing(players=(players[i], players[i + 1]), round_number=1)
                    )
                else:
                    # disparità: se il torneo consente trio e c'è almeno
                    # un match normale → trio
                    without_x = bool(getattr(prova.tournament, "without_x", False))
                    if without_x and pairings:
                        last = pairings[-1]
                        pairings[-1] = Pairing(
                            players=(last.players[0], last.players[1], players[i]),
                            round_number=1,
                        )
                    else:
                        pairings.append(
                            Pairing(players=(players[i],), is_bye=True, round_number=1)
                        )
            return pairings

        # Round >= 2: usa classifica round precedente (solo lettura) e applica il salto
        prev = (
            RoundClassification.query.filter_by(
                prova_id=prova.id, round_number=round_number - 1
            )
            .order_by(RoundClassification.position.asc())
            .all()
        )
        if not prev:
            # nessuna classifica → niente preview (non calcoliamo in memoria qui)
            return []

        salto = max(0, int(getattr(prova, "rounds_count", 0)) - int(round_number))
        matched: Set[int] = set()
        result: List[Pairing] = []
        order = prev  # già ordinati per posizione
        n = len(order)

        def find_target(idx: int) -> int | None:
            if n == 0:
                return None
            steps = 0
            target = (idx + salto) % n
            me = order[idx].user_id
            while steps < n:
                candidate = order[target].user_id
                if (
                    candidate not in matched
                    and me not in matched
                    and candidate != me
                    and not PlayerEncounter.have_played(prova.id, me, candidate)
                ):
                    return target
                target = (target + 1) % n
                steps += 1
            return None

        for i, rc in enumerate(order):
            if rc.user_id in matched:
                continue
            tgt = find_target(i)
            if tgt is not None:
                me = rc.user_id
                you = order[tgt].user_id
                result.append(Pairing(players=(me, you), round_number=round_number))
                matched.update({me, you})

        # gestisci l'eventuale disparità
        rest = [rc.user_id for rc in order if rc.user_id not in matched]
        if rest:
            without_x = bool(getattr(prova.tournament, "without_x", False))
            if without_x and result:
                last = result[-1]
                result[-1] = Pairing(
                    players=(last.players[0], last.players[1], rest[0]),
                    round_number=round_number,
                )
            else:
                result.append(
                    Pairing(players=(rest[0],), is_bye=True, round_number=round_number)
                )

        return result

    # ── propose (side‑effects via engine) ─────────────────────────────────────
    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
        raw = self._propose_fn(prova, round_number)
        result: list[Pairing] = []
        for players in raw:
            is_bye = len(players) == 1  # convenzione: (X,) se bye
            result.append(
                Pairing(
                    players=tuple(int(p) for p in players),
                    round_number=round_number,
                    is_bye=is_bye,
                )
            )
        return result
