"""La parte casuale di un esercizio, e la scala con cui si conta (#452, ADR-066).

Ci sono esercizi in cui **una parte della consegna si decide al tavolo, colpo
per colpo, ed è casuale**. «Kicking Madness» è il caso da cui nasce la
richiesta: a ogni colpo servono un numero di sponde e una bilia, e oggi il
giocatore dovrebbe tenere aperto random.org in un'altra scheda. L'estrazione la
fa l'app.

Due cose, e nessuna delle due è un numero grezzo:

* le **sorgenti**: liste indipendenti di voci già scritte a parole — «3 o più
  sponde», «bilia 7» — che l'estrazione compone in una consegna. Un generatore
  che stampasse `37` lascerebbe la decodifica al giocatore, che è proprio il
  lavoro che gli si vuole togliere;
* gli **esiti**: una scala di voci con un nome e un valore (0, 1, 2, 4, 8), non
  un superato/non superato e nemmeno un contatore che sale di uno.

Sta in una colonna JSON (`challenge.draw_spec`) e non in due tabelle: non la
interroga nessuno — si legge tutta insieme, e solo mentre si esegue — e le
tabelle avrebbero chiesto un ordine, due chiavi e due migration per ogni
ritocco. Il rifiuto di una specifica storta sta qui, come `parse_scene` per il
disegno.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

from models.exceptions import ValidationError

MAX_SOURCES = 3
MAX_OPTIONS = 30
MAX_OUTCOMES = 8
MAX_LABEL = 60
MAX_OPTION = 40
MAX_POINTS = 99
SPEC_VERSION = 1
#: Come si legge la consegna composta: «3 o più sponde, bilia 7».
JOIN = ", "


@dataclass(frozen=True)
class Source:
    label: str
    options: List[str]


@dataclass(frozen=True)
class Outcome:
    label: str
    points: int
    hint: str = ""


@dataclass(frozen=True)
class DrawSpec:
    sources: List[Source]
    outcomes: List[Outcome]

    @property
    def max_points(self) -> int:
        return max(o.points for o in self.outcomes)

    def draw(self, rng: Optional[random.Random] = None) -> str:
        """Una consegna, già a parole. Le sorgenti sono indipendenti."""
        tiratore = rng or random.Random()
        return JOIN.join(tiratore.choice(s.options) for s in self.sources)

    def outcome_at(self, indice: Any) -> Outcome:
        """L'esito scelto. Fuori scala è un rifiuto, mai il primo per ripiego."""
        try:
            posizione = int(indice)
        except (TypeError, ValueError):
            raise ValidationError("Questo esito non è di questo esercizio")
        if not 0 <= posizione < len(self.outcomes):
            raise ValidationError("Questo esito non è di questo esercizio")
        return self.outcomes[posizione]


def _text(valore: Any, quanto: int, che_cosa: str) -> str:
    if not isinstance(valore, str) or not valore.strip():
        raise ValidationError(f"{che_cosa}: manca il testo")
    pulito = " ".join(valore.split())
    if len(pulito) > quanto:
        raise ValidationError(f"{che_cosa}: il testo è troppo lungo")
    return pulito


def build_spec(sources: Sequence[dict], outcomes: Sequence[dict]) -> DrawSpec:
    """Convalida e normalizza. Solleva ``ValidationError`` su tutto il resto."""
    if not 1 <= len(sources) <= MAX_SOURCES:
        raise ValidationError(f"L'estrazione ha da una a {MAX_SOURCES} liste di voci")
    lette: List[Source] = []
    for sorgente in sources:
        opzioni = sorgente.get("options") if isinstance(sorgente, dict) else None
        if not isinstance(opzioni, list) or not 2 <= len(opzioni) <= MAX_OPTIONS:
            raise ValidationError(
                f"Ogni lista ha da due a {MAX_OPTIONS} voci fra cui estrarre"
            )
        lette.append(
            Source(
                label=_text(sorgente.get("label"), MAX_LABEL, "La lista"),
                options=[_text(o, MAX_OPTION, "La voce") for o in opzioni],
            )
        )

    if not 2 <= len(outcomes) <= MAX_OUTCOMES:
        raise ValidationError(f"Gli esiti sono da due a {MAX_OUTCOMES}")
    scala: List[Outcome] = []
    for esito in outcomes:
        if not isinstance(esito, dict):
            raise ValidationError("L'esito non è leggibile")
        punti = esito.get("points")
        if not isinstance(punti, int) or isinstance(punti, bool):
            raise ValidationError("Ogni esito vale un numero intero di punti")
        if not 0 <= punti <= MAX_POINTS:
            raise ValidationError(f"I punti di un esito vanno da 0 a {MAX_POINTS}")
        scala.append(
            Outcome(
                label=_text(esito.get("label"), MAX_LABEL, "L'esito"),
                points=punti,
                hint=" ".join(str(esito.get("hint") or "").split())[:MAX_LABEL],
            )
        )
    if max(o.points for o in scala) == 0:
        raise ValidationError("Almeno un esito deve valere dei punti")
    return DrawSpec(sources=lette, outcomes=scala)


def dump_spec(spec: DrawSpec) -> str:
    return json.dumps(
        {
            "v": SPEC_VERSION,
            "sources": [{"label": s.label, "options": s.options} for s in spec.sources],
            "outcomes": [
                {"label": o.label, "points": o.points, "hint": o.hint}
                for o in spec.outcomes
            ],
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def parse_draw_spec(raw: Optional[str]) -> Optional[DrawSpec]:
    """La specifica scritta in colonna, o ``None`` se non c'è.

    Tollerante come ``target_from_scene``: una specifica illeggibile dà
    ``None``, non un errore. Il rifiuto sta a monte, quando si salva.
    """
    if not raw:
        return None
    try:
        dato = json.loads(raw)
        if not isinstance(dato, dict):
            return None
        return build_spec(dato.get("sources") or [], dato.get("outcomes") or [])
    except (ValueError, TypeError, ValidationError):
        return None


# ────────────────────────────────────────────────────────────────────────
# Come si scrive nel modulo: una voce per riga
# ────────────────────────────────────────────────────────────────────────
def parse_sources_text(testo: str) -> List[dict]:
    """«sponde: 1 sponda | 2 sponde | 3 o più sponde», una lista per riga."""
    liste: List[dict] = []
    for riga in (testo or "").splitlines():
        if not riga.strip():
            continue
        nome, _, resto = riga.partition(":")
        if not resto.strip():
            raise ValidationError("Ogni lista si scrive «nome: voce | voce | voce»")
        liste.append(
            {
                "label": nome.strip(),
                "options": [v for v in (p.strip() for p in resto.split("|")) if v],
            }
        )
    return liste


def parse_outcomes_text(testo: str) -> List[dict]:
    """«Imbucata = 4», un esito per riga, dal peggiore al migliore."""
    esiti: List[dict] = []
    for riga in (testo or "").splitlines():
        if not riga.strip():
            continue
        nome, _, punti = riga.rpartition("=")
        if not nome.strip():
            raise ValidationError("Ogni esito si scrive «nome = punti»")
        try:
            valore = int(punti.strip())
        except ValueError:
            raise ValidationError("I punti di un esito sono un numero intero")
        esiti.append({"label": nome.strip(), "points": valore})
    return esiti


def sources_to_text(spec: DrawSpec) -> str:
    return "\n".join(f"{s.label}: {' | '.join(s.options)}" for s in spec.sources)


def outcomes_to_text(spec: DrawSpec) -> str:
    return "\n".join(f"{o.label} = {o.points}" for o in spec.outcomes)


__all__ = [
    "DrawSpec",
    "Outcome",
    "Source",
    "build_spec",
    "dump_spec",
    "parse_draw_spec",
    "parse_sources_text",
    "parse_outcomes_text",
    "sources_to_text",
    "outcomes_to_text",
]
