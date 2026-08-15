"""
Module: models/classification/position_points.py
Purpose: punti di campionato per posizione nelle gare a tabellone
Requirements: piano "Eliminazione diretta e doppio KO", Step 9 (US-17)

I valori di default sono quelli della spec (`CLASSIFICATION_SYSTEM.md` §7.5):
25 / 18 / 15 / 12, poi 8 punti dal 5° all'8° e 4 dal 9° al 16°. Un campionato
può sovrascriverli (`Campionato.position_points`); chi non lo fa non deve
configurare nulla.

**Perché una terza tabella punti.** Nel codice ce ne sono già due —
`statistics_service.py` (10/7/5/4…) e
`campionato_strategies.PointBasedCampionatoClassificationStrategy`
(1000/800/500…) — e la tentazione di unificarle è forte. Non si fa: sono
alimentate da campionati esistenti, e cambiarne i valori riscriverebbe in
silenzio classifiche già pubblicate. Restano dove sono; questa serve al solo
sistema POSITION.

Tutti i pari merito di una banda ricevono lo stesso punteggio, perché la banda
**è** la posizione: quattro quartifinalisti sono tutti 5° e prendono tutti i
punti del 5°.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# (posizione_massima, punti): la prima soglia che copre la posizione vince.
DEFAULT_POSITION_POINTS: Tuple[Tuple[int, int], ...] = (
    (1, 25),
    (2, 18),
    (3, 15),
    (4, 12),
    (8, 8),
    (16, 4),
)

# Oltre l'ultima soglia si è comunque partecipato, ma non si porta punti.
DEFAULT_POINTS_BEYOND = 0


def points_for_position(
    position: Optional[int], table: Optional[Dict[int, int]] = None
) -> int:
    """Punti di campionato per una posizione di gara.

    `table` è una mappa `posizione -> punti` esplicita (quella configurata sul
    campionato). Assente, valgono le soglie di default. Una posizione non
    coperta vale 0: aver partecipato non è di per sé un punteggio, e inventare
    un valore di consolazione sarebbe una decisione di prodotto mai presa.
    """
    if not position or position < 1:
        return 0

    if table:
        if position in table:
            return table[position]
        # Con una tabella esplicita, le posizioni oltre l'ultima dichiarata
        # valgono quanto dice l'ultima soglia utile, se ce n'è una che le
        # copre; altrimenti zero.
        covering = [pos for pos in sorted(table) if pos >= position]
        return table[covering[0]] if covering else 0

    for threshold, points in DEFAULT_POSITION_POINTS:
        if position <= threshold:
            return points
    return DEFAULT_POINTS_BEYOND


def default_table() -> Dict[int, int]:
    """Tabella di default espansa posizione per posizione (per la UI)."""
    expanded: Dict[int, int] = {}
    last = DEFAULT_POSITION_POINTS[-1][0]
    for position in range(1, last + 1):
        expanded[position] = points_for_position(position)
    return expanded


def parse_points_table(raw: Optional[str]) -> Optional[Dict[int, int]]:
    """Legge la tabella salvata sul campionato, o None se non c'è / non è valida.

    Il campo è JSON di forma `{"1": 25, "2": 18, ...}`. Un contenuto illeggibile
    **non** solleva: la classifica di un campionato non deve smettere di
    calcolarsi per un campo di configurazione scritto male. Si degrada al
    default e lo si scrive nel log, dove qualcuno può accorgersene.
    """
    if not raw:
        return None

    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Tabella punti posizione illeggibile, uso il default: %r", raw)
        return None

    if not isinstance(decoded, dict) or not decoded:
        logger.warning("Tabella punti posizione non è un oggetto JSON: %r", raw)
        return None

    table: Dict[int, int] = {}
    for key, value in decoded.items():
        try:
            table[int(key)] = int(value)
        except (TypeError, ValueError):
            logger.warning(
                "Voce non numerica nella tabella punti posizione: %r -> %r", key, value
            )
            return None
    return table


def serialize_points_table(table: Optional[Dict[int, int]]) -> Optional[str]:
    """Forma persistibile della tabella (None = "usa il default")."""
    if not table:
        return None
    return json.dumps({str(position): points for position, points in table.items()})


def points_table_for_campionato(campionato) -> Optional[Dict[int, int]]:
    """Tabella del campionato, o None per il default."""
    if campionato is None:
        return None
    return parse_points_table(getattr(campionato, "position_points", None))


def form_rows(campionato=None) -> List[Tuple[int, str, int]]:
    """Righe del form "punti per posizione": ``(soglia, etichetta, valore)``.

    Si espongono le **soglie** e non le sedici posizioni: sei caselle dicono
    già tutto, perché `points_for_position` risolve una posizione scoperta con
    la prima soglia che la contiene. L'etichetta è la banda che quella soglia
    copre — ``1°``, ``5°-8°``, ``9°-16°`` — cioè esattamente il pari merito
    che riceverà quei punti.

    Il valore è quello configurato sul campionato, o il default se non lo è
    (compreso il caso `campionato=None`, cioè la creazione).
    """
    configured = points_table_for_campionato(campionato) or {}
    rows: List[Tuple[int, str, int]] = []
    previous = 0
    for threshold, points in DEFAULT_POSITION_POINTS:
        label = (
            f"{threshold}°"
            if threshold == previous + 1
            else f"{previous + 1}°-{threshold}°"
        )
        rows.append((threshold, label, configured.get(threshold, points)))
        previous = threshold
    return rows


def describe_default() -> List[str]:
    """Descrizione leggibile delle soglie di default (UI e messaggi)."""
    rows: List[str] = []
    previous = 0
    for threshold, points in DEFAULT_POSITION_POINTS:
        if threshold == previous + 1:
            rows.append(f"{threshold}° = {points} punti")
        else:
            rows.append(f"{previous + 1}°-{threshold}° = {points} punti")
        previous = threshold
    return rows


__all__ = [
    "DEFAULT_POINTS_BEYOND",
    "DEFAULT_POSITION_POINTS",
    "default_table",
    "describe_default",
    "form_rows",
    "parse_points_table",
    "points_for_position",
    "points_table_for_campionato",
    "serialize_points_table",
]
