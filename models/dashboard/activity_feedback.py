"""Il blocco «Come stai andando» della home del giocatore.

Produce **un solo dict** (`activity_feedback`) che il template legge senza fare
nessuna decisione: quale metrica sta in prima cella, quale grafico si disegna e
cosa c'e' dentro le tessere lo decide qui il servizio, guardando *quali
attivita' il giocatore ha davvero svolto*.

Due regole che valgono per tutto il modulo:

* **niente numeri inventati.** Se una fonte non ha dati non si mette un
  placeholder: la griglia si stringe e il posto lo prende la metrica
  successiva disponibile. Un giocatore appena iscritto non riceve il blocco
  (`for_player` torna ``None``) ma la card di setup di `setup_card`.
* **la finestra e' «le ultime 10 attivita'»**, non «gli ultimi 30 giorni». Un
  giocatore che gioca due volte l'anno deve vedere le sue due partite, non un
  riquadro vuoto.

Il vocabolario dei profili e' quello dell'handoff di design:
``full``, ``elo_only``, ``drill_only``, ``competition_only``, ``director``,
``hyperactive``, ``returning``, ``declining``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from flask_babel import gettext as _
from flask_babel import ngettext
from sqlalchemy import or_

from models.base import db, utc_now
from models.status_enum import GaraStatus, MatchStatus

# Quante attivita' compongono la finestra di calcolo.
WINDOW = 10

# Sotto le tre attivita' la sparkline non si disegna: due punti non sono un
# andamento, sono un segmento, e suggerirebbe una tendenza che non c'e'.
MIN_POINTS_FOR_CHART = 3

# Oltre questo silenzio il giocatore e' «di rientro»: il blocco cambia tono e
# la linea prosegue tratteggiata fino a oggi invece di fingere continuita'.
RETURNING_AFTER_DAYS = 28

# Chi supera questa soglia nel mese e' «super attivo»: le tessere diventano
# dodici e perdono il testo, con la legenda dei conteggi sotto.
HYPERACTIVE_DAYS = 30
HYPERACTIVE_ACTIVITIES = 30

# Geometria della sparkline. Il viewBox e' stirato in orizzontale
# (`preserveAspectRatio="none"`), quindi lo spessore della linea va protetto
# con `vector-effect="non-scaling-stroke"` lato template.
CHART_W = 130.0
CHART_H = 34.0
CHART_PAD = 4.0

# Massimo di righe nel pannello espanso: oltre, smette di essere un riassunto.
MAX_EXPANDED_ROWS = 4


# ──────────────────────────────────────────────────────────────────────────────
# Una attivita' della finestra
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Activity:
    """Un fatto avvenuto, gia' ridotto a cio' che la striscia deve mostrare.

    `kind` serve a scegliere l'attivita' dominante (quella con piu' eventi
    nella finestra), `outcome` colora la tessera e `text` e' il dato che la
    tessera porta **oltre** al colore — perche' il colore non puo' essere
    l'unico veicolo dell'informazione.
    """

    kind: str  # 'match' | 'gara' | 'drill'
    at: datetime
    outcome: str  # 'win' | 'draw' | 'loss' | 'neutral'
    text: str
    title: str  # testo per title/aria-label
    icon: Optional[str] = None  # usato al posto del testo (drill nel misto)


# ──────────────────────────────────────────────────────────────────────────────
# Raccolta dei fatti
# ──────────────────────────────────────────────────────────────────────────────
def _tournament_match_activities(user_id: int) -> List[Activity]:
    """Le ultime partite di gara concluse, dal punto di vista del giocatore.

    Fuori dalla finestra restano i bye (non c'e' un avversario) e i trio: il
    punteggio del trio non vive su `Match.player1_score`/`player2_score` ma
    nel giro a tre, e una tessera senza punteggio violerebbe la regola per cui
    ogni tessera porta anche il dato.
    """
    from models.match.models import Match

    rows = (
        db.session.query(Match)
        .filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.status.in_(MatchStatus.finished_values()),
            Match.is_bye.isnot(True),
            Match.is_trio.isnot(True),
        )
        .order_by(Match.ended_at.desc().nullslast(), Match.id.desc())
        .limit(WINDOW)
        .all()
    )
    return [
        _match_activity(row, user_id, row.ended_at or row.created_at) for row in rows
    ]


def _individual_match_activities(user_id: int) -> List[Activity]:
    """Le ultime partite casual concluse."""
    from models.individual_match.match_models import IndividualMatch

    rows = (
        db.session.query(IndividualMatch)
        .filter(
            or_(
                IndividualMatch.player1_id == user_id,
                IndividualMatch.player2_id == user_id,
            ),
            IndividualMatch.status.in_(
                [MatchStatus.CLOSED_UNILATERALLY, MatchStatus.CONFIRMED_BY_BOTH]
            ),
        )
        .order_by(
            IndividualMatch.ended_at.desc().nullslast(), IndividualMatch.id.desc()
        )
        .limit(WINDOW)
        .all()
    )
    return [
        _match_activity(
            row, user_id, row.ended_at or row.scheduled_at or row.created_at
        )
        for row in rows
    ]


def _match_activity(match: Any, user_id: int, at: Optional[datetime]) -> Activity:
    """Riduce una partita (di gara o casual) a una tessera."""
    mine, theirs = (
        (match.player1_score, match.player2_score)
        if match.player1_id == user_id
        else (match.player2_score, match.player1_score)
    )
    mine = mine or 0
    theirs = theirs or 0

    if mine > theirs:
        outcome = "win"
    elif mine < theirs:
        outcome = "loss"
    else:
        outcome = "draw"

    text = f"{mine}–{theirs}"
    label = {
        "win": _("vinta"),
        "loss": _("persa"),
        "draw": _("pari"),
    }[outcome]
    return Activity(
        kind="match",
        at=at or utc_now(),
        outcome=outcome,
        text=text,
        title=_("Partita %(score)s, %(outcome)s", score=text, outcome=label),
    )


def _gara_activities(user_id: int) -> List[Activity]:
    """Gli ultimi piazzamenti in gara.

    Il colore dice quanto in alto: podio verde, meta' alta grigio scuro, il
    resto grigio chiaro. Il numero (`5°`) resta sempre scritto sopra.
    """
    from models.classification.models import GaraClassification

    rows = (
        db.session.query(GaraClassification)
        .filter(GaraClassification.user_id == user_id)
        .order_by(GaraClassification.created_at.desc(), GaraClassification.id.desc())
        .limit(WINDOW)
        .all()
    )
    if not rows:
        return []

    field_sizes = _gara_field_sizes([row.gara_id for row in rows])

    out: List[Activity] = []
    for row in rows:
        total = field_sizes.get(row.gara_id, 0)
        if row.position <= 3:
            outcome = "win"
        elif total and row.position <= total / 2:
            outcome = "neutral"
        else:
            outcome = "draw"
        text = _("%(pos)s°", pos=row.position)
        gara_name = row.gara.display_name if row.gara else _("Gara")
        out.append(
            Activity(
                kind="gara",
                at=row.created_at or utc_now(),
                outcome=outcome,
                text=text,
                title=(
                    _(
                        "%(gara)s, %(pos)s° su %(total)s",
                        gara=gara_name,
                        pos=row.position,
                        total=total,
                    )
                    if total
                    else _("%(gara)s, %(pos)s°", gara=gara_name, pos=row.position)
                ),
            )
        )
    return out


def _gara_field_sizes(gara_ids: Sequence[int]) -> Dict[int, int]:
    """Quanti classificati per gara — una query sola, non una per tessera."""
    from models.classification.models import GaraClassification

    if not gara_ids:
        return {}
    rows = (
        db.session.query(
            GaraClassification.gara_id, db.func.count(GaraClassification.id)
        )
        .filter(GaraClassification.gara_id.in_(list(gara_ids)))
        .group_by(GaraClassification.gara_id)
        .all()
    )
    return {gara_id: count for gara_id, count in rows}


def _drill_activities(user_id: int) -> List[Activity]:
    """Le ultime prove di drill completate."""
    from models.challenge.models import Challenge, ChallengeAttempt

    rows = (
        db.session.query(ChallengeAttempt)
        .join(Challenge, Challenge.id == ChallengeAttempt.challenge_id)
        .filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed.is_(True),
        )
        .order_by(ChallengeAttempt.attempted_at.desc(), ChallengeAttempt.id.desc())
        .limit(WINDOW)
        .all()
    )
    out: List[Activity] = []
    for row in rows:
        name = row.challenge.get_display_name() if row.challenge else _("Esercizio")
        if row.passed is True:
            outcome = "win"
        elif row.passed is False:
            outcome = "draw"
        else:
            outcome = "neutral"
        out.append(
            Activity(
                kind="drill",
                at=row.attempted_at or utc_now(),
                outcome=outcome,
                text=name,
                title=(
                    _("%(name)s, punteggio %(score)s", name=name, score=row.score)
                    if not (row.challenge and row.challenge.pass_fail_only)
                    else (
                        _("%(name)s, superato", name=name)
                        if row.passed
                        else _("%(name)s, non superato", name=name)
                    )
                ),
                icon="fa-bullseye",
            )
        )
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Serie numeriche
# ──────────────────────────────────────────────────────────────────────────────
def _elo_series(user_id: int) -> Tuple[List[int], Optional[int], bool]:
    """Gli ultimi punti Elo, il delta sulla finestra e se e' il massimo storico.

    Si preferisce il pool **globale** (tornei + casual): e' quello che il
    giocatore vede come «il suo Elo» in home. Se non ci sono righe globali si
    ripiega sul competitivo. La serie parte dall'`old_rating` della prima riga
    della finestra, cosi' il primo punto e' il valore *prima* di quel match.

    Il terzo valore serve a una frase sola — «massimo» — e va calcolato su
    **tutto** lo storico, non sulla finestra: dire «massimo» guardando dieci
    partite significherebbe dirlo a chiunque stia salendo, che e' esattamente
    il tipo di numero inventato che questo blocco non deve produrre.
    """
    from models.rating.models import MatchRatingHistory, RatingSystem

    def _rows(system: RatingSystem) -> List[Any]:
        return list(
            reversed(
                db.session.query(MatchRatingHistory)
                .filter(
                    MatchRatingHistory.user_id == user_id,
                    MatchRatingHistory.rating_system == system,
                )
                .order_by(MatchRatingHistory.id.desc())
                .limit(WINDOW)
                .all()
            )
        )

    system = RatingSystem.ELO_GLOBAL
    rows = _rows(system)
    if not rows:
        system = RatingSystem.ELO
        rows = _rows(system)
    if not rows:
        return [], None, False

    # Interi: `_current_elo` dichiara `Sequence[int]` e da qui in giù il valore
    # finisce in `str()`. Le colonne sono in virgola mobile per il pool a rack
    # (ADR-052), ma i due pool letti qui scrivono interi per costruzione.
    series = [int(round(rows[0].old_rating))] + [
        int(round(row.new_rating)) for row in rows
    ]
    all_time_high = (
        db.session.query(db.func.max(MatchRatingHistory.new_rating))
        .filter(
            MatchRatingHistory.user_id == user_id,
            MatchRatingHistory.rating_system == system,
        )
        .scalar()
    )
    return series, series[-1] - series[0], series[-1] >= (all_time_high or series[-1])


def _current_elo(user: Any, series: Sequence[int]) -> Optional[int]:
    """L'Elo da mostrare adesso, indipendentemente dallo storico dei delta.

    La serie e' la strada normale, ma non e' l'unica fonte: `User.elo_rating`
    e' la colonna sincronizzata e autorevole, e il pool globale vive su
    `PlayerRating`. Un giocatore le cui partite sono state chiuse prima che il
    registro dei delta esistesse — o senza passare dal motore di rating — ha un
    Elo vero e nessuna riga di storico: leggere solo lo storico glielo
    nasconderebbe, senza che niente lo segnali.

    ``None`` significa davvero «non ha un Elo»: non si ripiega su 1200, che e'
    il valore da cui il motore *parte* e non un punteggio conquistato.
    """
    if series:
        return series[-1]
    if user is None:
        return None
    return getattr(user, "elo_global_rating", None) or getattr(user, "elo_rating", None)


def _tpa_window(user_id: int, user: Any = None) -> Optional[Dict[str, Any]]:
    """I numeri TPA, o ``None`` se il giocatore non ne ha nessuno.

    Il valore grande resta il TPA **di carriera** (e' quello che il giocatore
    riconosce); il delta e la serie del grafico vengono invece dai singoli
    referti della finestra, che sono dati veri e verificabili — non una stima
    del TPA «di dieci attivita' fa», che non e' ricostruibile.
    """
    from models.tpa.stats_service import TpaStatsService

    # Stessa porta del profilo: il TPA si mostra a chi ha sbloccato la funzione
    # o a chi ha gia' un referto compilato su una sua partita.
    if not TpaStatsService.is_visible_for(user_id, user=user):
        return None

    stats = TpaStatsService.career_stats(user_id)
    if not stats or stats.get("tpa") is None:
        return None

    # `matches` arriva dal piu' recente: la finestra si legge in ordine di gioco.
    scored = [m for m in reversed(stats["matches"]) if m.get("tpa") is not None]
    series = [m["tpa"] for m in scored][-WINDOW:]
    delta = (series[-1] - series[0]) if len(series) >= 2 else None
    return {
        "career": stats["tpa"],
        "series": series,
        "delta": delta,
        "referti": stats["referti"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Grafici
# ──────────────────────────────────────────────────────────────────────────────
def _points(
    values: Sequence[float],
    *,
    x_from: float = 0.0,
    x_to: float = CHART_W,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
) -> List[Tuple[float, float]]:
    """Trasforma una serie di numeri nei punti del viewBox della sparkline.

    `lo`/`hi` si passano quando due serie devono condividere la scala verticale
    — o quando una serie deve restare confrontabile con se stessa fra due
    tratti (linea piena + proiezione tratteggiata).
    """
    if not values:
        return []
    lo = min(values) if lo is None else lo
    hi = max(values) if hi is None else hi
    span = (hi - lo) or 1.0
    usable = CHART_H - 2 * CHART_PAD
    step = (x_to - x_from) / (len(values) - 1) if len(values) > 1 else 0.0
    out: List[Tuple[float, float]] = []
    for i, value in enumerate(values):
        x = x_from + step * i
        y = CHART_H - CHART_PAD - ((value - lo) / span) * usable
        out.append((round(x, 1), round(y, 1)))
    return out


def _path(points: Sequence[Tuple[float, float]]) -> str:
    return " ".join(f"{x},{y}" for x, y in points)


def _area(points: Sequence[Tuple[float, float]]) -> str:
    """La stessa linea, chiusa sul fondo: e' il riempimento sotto la curva."""
    if not points:
        return ""
    return _path(points) + f" {points[-1][0]},{CHART_H} {points[0][0]},{CHART_H}"


def _line_chart(
    values: Sequence[float],
    *,
    labels: Dict[str, str],
    positive: bool = False,
    secondary: Optional[Sequence[float]] = None,
    legend: Optional[List[Dict[str, str]]] = None,
    projected: bool = False,
    declining: bool = False,
) -> Optional[Dict[str, Any]]:
    """La sparkline, in tutte le declinazioni previste dal design.

    `projected` (rientro dopo pausa): la linea si ferma dove il giocatore si e'
    fermato e prosegue tratteggiata fino a oggi, con un cerchio vuoto in fondo.
    `declining`: la linea e' grigia, e se gli ultimi tre punti risalgono quel
    tratto torna scuro e piu' spesso — il calo si mostra, la risalita anche.
    """
    if len(values) < MIN_POINTS_FOR_CHART:
        return None

    stop_x = CHART_W * 0.73 if projected else CHART_W
    pts = _points(values, x_to=stop_x)

    chart: Dict[str, Any] = {
        "kind": "line",
        "area": _area(pts),
        "main": _path(pts),
        "muted": None,
        "highlight": None,
        "dashed": None,
        "projection": None,
        "dots": [],
        "labels": labels,
        "legend": legend or [],
    }

    if declining:
        # La linea di fondo diventa grigia; gli ultimi tre punti tornano scuri
        # solo se stanno davvero risalendo.
        chart["muted"] = chart["main"]
        chart["main"] = None
        if len(pts) >= 4 and values[-1] > values[-4]:
            chart["highlight"] = _path(pts[-4:])

    if projected:
        chart["projection"] = _path([pts[-1], (CHART_W, pts[-1][1])])
        chart["dots"].append({"cx": pts[-1][0], "cy": pts[-1][1], "kind": "last"})
        chart["dots"].append({"cx": CHART_W, "cy": pts[-1][1], "kind": "ghost"})
    else:
        # I punti intermedi si vedono solo quando i campioni sono pochi: su
        # dieci punti diventerebbero rumore. Si contano gli **eventi**, non i
        # punti: la serie Elo comincia dal valore *prima* della prima partita,
        # quindi cinque partite disegnano sei punti.
        if len(pts) - 1 <= 5:
            for x, y in pts[:-1]:
                chart["dots"].append({"cx": x, "cy": y, "kind": "mid"})
        chart["dots"].append(
            {
                "cx": pts[-1][0],
                "cy": pts[-1][1],
                "kind": "last-ok" if positive else "last",
            }
        )

    if secondary and len(secondary) >= MIN_POINTS_FOR_CHART:
        chart["dashed"] = _path(_points(secondary, x_to=stop_x))

    return chart


def _bars_chart(
    values: Sequence[float], *, labels: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """Le barre: sessioni di drill, iscritti per gara.

    L'ultima barra e' sempre quella verde — e' «dove sei adesso»; le altre si
    schiariscono verso il basso, cosi' la progressione si legge senza etichette.
    """
    if len(values) < MIN_POINTS_FOR_CHART:
        return None
    hi = max(values) or 1.0
    lo = min(values)
    span = (hi - lo) or 1.0

    bars = []
    for i, value in enumerate(values):
        # Minimo 18% perche' una barra alta zero non si vede ed è comunque un dato.
        pct = 18 + round(((value - lo) / span) * 82)
        if i == len(values) - 1:
            tone = "ok"
        elif (value - lo) / span >= 0.66:
            tone = "dark"
        elif (value - lo) / span >= 0.33:
            tone = "mid"
        else:
            tone = "soft"
        bars.append({"pct": pct, "tone": tone})

    return {
        "kind": "bars",
        "bars": bars,
        "labels": labels,
        "legend": [],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Pezzi della card
# ──────────────────────────────────────────────────────────────────────────────
def _metric(
    label: str,
    value: str,
    *,
    delta: Optional[str] = None,
    delta_tone: str = "flat",
    suffix: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "kind": "metric",
        "label": label,
        "value": value,
        "suffix": suffix,
        "delta": delta,
        "delta_tone": delta_tone,
    }


def _donut(slices: List[Dict[str, Any]], center: str) -> Dict[str, Any]:
    """La torta e' un `conic-gradient`: qui si calcolano gli stop cumulati."""
    total = sum(s["count"] for s in slices) or 1
    stops: List[str] = []
    running = 0.0
    palette = {
        "ok": "var(--c7-ok)",
        "muted": "#C9CFCE",
        "err": "var(--c7-err)",
        "accent": "var(--c7-accent)",
    }
    for item in slices:
        start = running
        running += item["count"] / total * 100
        stops.append(f"{palette[item['color_role']]} {start:.4g}% {running:.4g}%")
    return {
        "kind": "donut",
        "slices": slices,
        "center": center,
        "gradient": "conic-gradient(" + ", ".join(stops) + ")",
    }


def _delta_text(delta: Optional[int], suffix: str) -> Tuple[Optional[str], str]:
    """Il delta come si scrive accanto alla metrica, col suo tono.

    Il meno e' un vero segno meno (U+2212), non un trattino: accanto a una
    cifra in mono, il trattino si legge come un separatore.
    """
    if delta is None:
        return None, "flat"
    if delta > 0:
        return f"+{delta} {suffix}".strip(), "up"
    if delta < 0:
        return f"−{abs(delta)} {suffix}".strip(), "down"
    return _("invariato %(suffix)s", suffix=suffix).strip(), "flat"


def _tpa_value(millesimi: int) -> str:
    """`.742`, `1.000` — come sul referto (stessa regola di `format_tpa`)."""
    if millesimi >= 1000:
        return f"{millesimi // 1000}.{millesimi % 1000:03d}"
    return f".{millesimi:03d}"


def _tpa_delta_text(delta: Optional[int]) -> Tuple[Optional[str], str]:
    if delta is None:
        return None, "flat"
    if delta == 0:
        return _("stabile"), "flat"
    sign = "+" if delta > 0 else "−"
    return f"{sign}{_tpa_value(abs(delta))}", ("up" if delta > 0 else "down")


#: Quante tessere ci stanno prima che il testo dentro diventi illeggibile.
STRIP_TEXT_LIMIT = 6


def _strip(activities: Sequence[Activity], *, label: str, note: str) -> Dict[str, Any]:
    """La striscia delle ultime attivita', dalla piu' vecchia.

    Oltre sei tessere il testo non ci sta piu', e la via d'uscita dipende da
    cosa c'e' dentro. Le partite hanno un esito — si vincono, si pareggiano, si
    perdono — quindi possono stringersi, perdere il punteggio e mandare i
    conteggi nella legenda sotto: il colore continua a dire tutto, e la legenda
    lo traduce in parole. Piazzamenti e drill no: `3°` non e' «una vittoria» e
    un drill numerico non e' ne' superato ne' fallito, quindi una legenda di
    esiti mentirebbe. Li' la striscia si accorcia alle ultime sei e tiene il
    testo, che e' l'informazione vera.
    """
    kinds = {a.kind for a in activities}

    dense = len(activities) > STRIP_TEXT_LIMIT and kinds == {"match"}
    if len(activities) > STRIP_TEXT_LIMIT and not dense:
        activities = activities[-STRIP_TEXT_LIMIT:]

    # L'icona del bersaglio serve a dire «questo e' un drill» in mezzo a dei
    # punteggi. In una striscia di soli drill non distingue niente e ruba il
    # posto al nome, che invece dice quale drill era.
    mixed = len(kinds) > 1
    items = [
        {
            "text": a.text,
            "icon": a.icon if mixed else None,
            "outcome": a.outcome,
            "title": a.title,
        }
        for a in activities
    ]

    legend: List[Dict[str, Any]] = []
    if dense:
        counts = {
            "win": sum(1 for a in activities if a.outcome == "win"),
            "draw": sum(1 for a in activities if a.outcome in ("draw", "neutral")),
            "loss": sum(1 for a in activities if a.outcome == "loss"),
        }
        # Solo le partite arrivano qui, quindi il vocabolario e' uno solo.
        wording = {
            "win": lambda n: ngettext("%(num)s vinta", "%(num)s vinte", n),
            "draw": lambda n: ngettext("%(num)s pari", "%(num)s pari", n),
            "loss": lambda n: ngettext("%(num)s persa", "%(num)s perse", n),
        }
        legend = [
            {"outcome": key, "label": wording[key](count)}
            for key, count in counts.items()
            if count
        ]
    return {
        "label": label,
        "note": note,
        "items": items,
        "dense": dense,
        "legend": legend,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Il pannello espanso
# ──────────────────────────────────────────────────────────────────────────────
def _expanded_rows(user_id: int) -> List[Dict[str, Any]]:
    """Le righe del pannello: solo quelle che hanno un dato vero dietro."""
    rows: List[Dict[str, Any]] = []
    rows.extend(_streak_row(user_id))
    rows.extend(_campionato_row(user_id))
    rows.extend(_drill_row(user_id))
    rows.extend(_level_row(user_id))
    return rows[:MAX_EXPANDED_ROWS]


def _streak_row(user_id: int) -> List[Dict[str, Any]]:
    from models.gamification.models import StreakType
    from models.gamification.streak_service import StreakService

    try:
        info = StreakService.get_streak_info(
            user_id=user_id, streak_type=StreakType.WEEKLY_ACTIVITY
        )
    except Exception:  # pragma: no cover - la home non cade per una streak
        return []
    current = info.get("current_streak") or 0
    if current <= 0:
        return []
    longest = info.get("longest_streak") or current
    subtitle = (
        _("Il tuo record è %(n)s settimane", n=longest)
        if longest > current
        else _("È la tua serie più lunga finora")
    )
    return [
        {
            "icon": "fa-fire",
            "color_role": "err",
            "title": ngettext(
                "%(num)s settimana di streak",
                "%(num)s settimane di streak",
                current,
            ),
            "subtitle": subtitle,
            "value": str(current),
        }
    ]


def _campionato_row(user_id: int) -> List[Dict[str, Any]]:
    from models.classification.models import Classification

    row = (
        db.session.query(Classification)
        .filter(
            Classification.user_id == user_id,
            Classification.position.isnot(None),
        )
        .order_by(
            Classification.gare_played.desc().nullslast(),
            Classification.id.desc(),
        )
        .first()
    )
    if row is None or not row.campionato:
        return []
    total = (
        db.session.query(db.func.count(Classification.id))
        .filter(Classification.campionato_id == row.campionato_id)
        .scalar()
        or 0
    )
    return [
        {
            "icon": "fa-trophy",
            "color_role": "accent",
            "title": _(
                "%(pos)s° in %(campionato)s",
                pos=row.position,
                campionato=row.campionato.name,
            ),
            "subtitle": ngettext(
                "Su %(num)s giocatore in classifica",
                "Su %(num)s giocatori in classifica",
                total,
            ),
            "value": None,
        }
    ]


def _drill_row(user_id: int) -> List[Dict[str, Any]]:
    from models.challenge.models import Challenge, ChallengeAttempt

    total, avg = (
        db.session.query(
            db.func.count(ChallengeAttempt.id), db.func.avg(ChallengeAttempt.score)
        )
        .join(Challenge, Challenge.id == ChallengeAttempt.challenge_id)
        .filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed.is_(True),
            Challenge.pass_fail_only.is_(False),
        )
        .one()
    )
    if not total:
        return []
    subtitle = (
        _("Punteggio medio %(avg)s", avg=round(avg))
        if avg is not None
        else _("Nessun punteggio registrato")
    )
    return [
        {
            "icon": "fa-bullseye",
            "color_role": "accent",
            "title": ngettext(
                "%(num)s esercizio completato",
                "%(num)s esercizi completati",
                total,
            ),
            "subtitle": subtitle,
            "value": None,
        }
    ]


def _level_row(user_id: int) -> List[Dict[str, Any]]:
    from models.gamification.level_service import LevelService

    try:
        progress = LevelService.get_level_progress(user_id)
    except Exception:  # pragma: no cover - vale quanto la streak
        return []
    if not progress:
        return []
    level = progress.get("current_level") or 1
    pct = int(round(progress.get("progress_percentage") or 0))
    unlock = progress.get("next_unlock") or {}
    subtitle = unlock.get("description") or _(
        "Continua a giocare per salire di livello"
    )
    return [
        {
            "icon": None,
            "color_role": "accent",
            "title": _("Livello %(level)s al %(pct)s%%", level=level + 1, pct=pct),
            "subtitle": subtitle,
            "value": None,
            "ring_pct": pct,
        }
    ]


def _toggle_label(profile: str, rows: Sequence[Dict[str, Any]]) -> str:
    """L'etichetta del bottone e' un'anteprima del contenuto, non «Espandi»."""
    if profile == "declining":
        return _("Cosa sta funzionando")
    icons = {row.get("icon") for row in rows}
    if "fa-fire" in icons and "fa-trophy" in icons:
        return _("Streak e classifica")
    return _("Tutti i tuoi numeri")


# ──────────────────────────────────────────────────────────────────────────────
# Profilo
# ──────────────────────────────────────────────────────────────────────────────
def _director_pending(user_id: int) -> int:
    """Gare organizzate ancora da chiudere: e' l'operativita', e viene prima."""
    from models.competition.models import Gara

    return (
        db.session.query(db.func.count(Gara.id))
        .filter(
            Gara.director_id == user_id,
            Gara.status.in_([GaraStatus.PLAYING.value, GaraStatus.AWAITING_SSR.value]),
        )
        .scalar()
        or 0
    )


def _director_garas(user_id: int) -> List[Any]:
    from models.competition.models import Gara

    return (
        db.session.query(Gara)
        .filter(Gara.director_id == user_id)
        .order_by(Gara.date.asc().nullslast(), Gara.id.asc())
        .all()
    )


def has_any_activity(user_id: int, user: Any = None) -> bool:
    """Se questo utente ha qualcosa da raccontare, senza calcolare il blocco.

    E' la stessa condizione da cui `for_player` esce restituendo ``None``, ma
    fatta di `EXISTS`: serve a decidere se disegnare la card di setup **senza**
    costruire prima il blocco intero per poi buttarlo via.

    Niente filtro temporale, e nessun `>=` su `ended_at`: una partita conclusa
    con la data di fine mancante e' comunque una partita giocata, e chi l'ha
    giocata non e' «appena iscritto».
    """
    from models.challenge.models import ChallengeAttempt
    from models.classification.models import GaraClassification
    from models.competition.models import Gara
    from models.individual_match.match_models import IndividualMatch
    from models.match.models import Match

    checks = (
        db.session.query(Match.id).filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.status.in_(MatchStatus.finished_values()),
            Match.is_bye.isnot(True),
            Match.is_trio.isnot(True),
        ),
        db.session.query(IndividualMatch.id).filter(
            or_(
                IndividualMatch.player1_id == user_id,
                IndividualMatch.player2_id == user_id,
            ),
            IndividualMatch.status.in_(
                [MatchStatus.CLOSED_UNILATERALLY, MatchStatus.CONFIRMED_BY_BOTH]
            ),
        ),
        db.session.query(GaraClassification.id).filter(
            GaraClassification.user_id == user_id
        ),
        db.session.query(ChallengeAttempt.id).filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed.is_(True),
        ),
    )
    if any(q.first() is not None for q in checks):
        return True

    # Un direttore con gare organizzate ha il suo blocco anche senza aver
    # giocato: per lui la card di setup sarebbe fuori posto.
    if user is not None and getattr(user, "is_director", False):
        return (
            db.session.query(Gara.id).filter(Gara.director_id == user_id).first()
            is not None
        )
    return False


def activities_since(user_id: int, since: datetime) -> int:
    """Quante attivita' ha svolto un giocatore da una certa data.

    Serve solo a riconoscere il super attivo, e **non** puo' venire dalla
    finestra: quella e' tappata a dieci, quindi «piu' di trenta nel mese» non
    sarebbe mai vero e il profilo resterebbe dichiarato ma irraggiungibile.
    Quattro `COUNT`, nessuna riga materializzata.
    """
    from models.challenge.models import ChallengeAttempt
    from models.classification.models import GaraClassification
    from models.individual_match.match_models import IndividualMatch
    from models.match.models import Match

    tournament = (
        db.session.query(db.func.count(Match.id))
        .filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.status.in_(MatchStatus.finished_values()),
            Match.is_bye.isnot(True),
            Match.is_trio.isnot(True),
            Match.ended_at >= since,
        )
        .scalar()
        or 0
    )
    casual = (
        db.session.query(db.func.count(IndividualMatch.id))
        .filter(
            or_(
                IndividualMatch.player1_id == user_id,
                IndividualMatch.player2_id == user_id,
            ),
            IndividualMatch.status.in_(
                [MatchStatus.CLOSED_UNILATERALLY, MatchStatus.CONFIRMED_BY_BOTH]
            ),
            IndividualMatch.ended_at >= since,
        )
        .scalar()
        or 0
    )
    garas = (
        db.session.query(db.func.count(GaraClassification.id))
        .filter(
            GaraClassification.user_id == user_id,
            GaraClassification.created_at >= since,
        )
        .scalar()
        or 0
    )
    drills = (
        db.session.query(db.func.count(ChallengeAttempt.id))
        .filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed.is_(True),
            ChallengeAttempt.attempted_at >= since,
        )
        .scalar()
        or 0
    )
    return tournament + casual + garas + drills


def _classify(
    *,
    user_id: int,
    activities: Sequence[Activity],
    elo_delta: Optional[int],
    has_tpa: bool,
    is_director: bool,
    director_garas: int,
) -> str:
    """Quale delle otto casistiche e' questo giocatore.

    L'ordine conta: «direttore» e «di rientro» cambiano il *tono* del blocco e
    vincono su tutto il resto; «in calo» viene prima delle classificazioni per
    fonte perche' e' quella che decide se il delta va mostrato in ambra.
    """
    if is_director and director_garas:
        return "director"

    last = max(a.at for a in activities)
    if (utc_now() - last) > timedelta(days=RETURNING_AFTER_DAYS):
        return "returning"

    since = utc_now() - timedelta(days=HYPERACTIVE_DAYS)
    if activities_since(user_id, since) >= HYPERACTIVE_ACTIVITIES:
        return "hyperactive"

    if elo_delta is not None and elo_delta < 0:
        return "declining"

    kinds = {a.kind for a in activities}
    if kinds == {"drill"}:
        return "drill_only"
    if kinds == {"gara"}:
        return "competition_only"
    if has_tpa:
        return "full"
    return "elo_only"


def _outcome_counts(activities: Sequence[Activity]) -> Dict[str, int]:
    return {
        "win": sum(1 for a in activities if a.outcome == "win"),
        "draw": sum(1 for a in activities if a.outcome in ("draw", "neutral")),
        "loss": sum(1 for a in activities if a.outcome == "loss"),
    }


def _results_donut(activities: Sequence[Activity]) -> Dict[str, Any]:
    counts = _outcome_counts(activities)
    total = sum(counts.values())
    slices = [
        {
            "label": ngettext("%(num)s vinta", "%(num)s vinte", counts["win"]),
            "count": counts["win"],
            "color_role": "ok",
        },
        {
            "label": ngettext("%(num)s pari", "%(num)s pari", counts["draw"]),
            "count": counts["draw"],
            "color_role": "muted",
        },
        {
            "label": ngettext("%(num)s persa", "%(num)s perse", counts["loss"]),
            "count": counts["loss"],
            "color_role": "err",
        },
    ]
    return _donut(
        [s for s in slices if s["count"]],
        center=f"{counts['win']}/{total}",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Servizio
# ──────────────────────────────────────────────────────────────────────────────
class ActivityFeedbackService:
    """Il blocco «Come stai andando», o la card di setup se non c'e' nulla."""

    @staticmethod
    def for_player(user_id: int, user: Any = None) -> Optional[Dict[str, Any]]:
        """Il dict del blocco, o ``None`` se il giocatore non ha attivita'.

        ``None`` non e' un errore: e' il caso «appena iscritto», e il template
        al suo posto disegna `setup_card`.
        """
        from models.user.models import User

        if user is None:
            user = db.session.get(User, user_id)
        if user is None:
            return None

        is_director = bool(getattr(user, "is_director", False))
        director_garas = _director_garas(user_id) if is_director else []

        pool = (
            _tournament_match_activities(user_id)
            + _individual_match_activities(user_id)
            + _gara_activities(user_id)
            + _drill_activities(user_id)
        )
        if not pool and not director_garas:
            return None

        # La finestra: le ultime dieci, poi rilette dalla piu' vecchia.
        window = sorted(pool, key=lambda a: a.at)[-WINDOW:]

        elo_series, elo_delta, elo_at_high = _elo_series(user_id)
        elo_current = _current_elo(user, elo_series)
        tpa = _tpa_window(user_id, user=user)

        profile = _classify(
            user_id=user_id,
            activities=window,
            elo_delta=elo_delta,
            has_tpa=tpa is not None,
            is_director=is_director,
            director_garas=len(director_garas),
        )

        if profile == "director":
            block = _build_director(user_id, director_garas)
        else:
            block = _build_player(
                user_id=user_id,
                profile=profile,
                window=window,
                elo_series=elo_series,
                elo_delta=elo_delta,
                elo_at_high=elo_at_high,
                elo_current=elo_current,
                tpa=tpa,
            )

        rows = _expanded_rows(user_id)
        block["expanded_rows"] = rows
        block["toggle_label"] = _toggle_label(profile, rows)
        block["profile"] = profile
        return block

    @staticmethod
    def setup_card(user_id: int, user: Any = None) -> Dict[str, Any]:
        """La card del giocatore appena iscritto: tre passi, nessun numero finto."""
        from models.challenge.models import ChallengeAttempt
        from models.user.models import User

        if user is None:
            user = db.session.get(User, user_id)

        # `User` non ha una sala preferita: la citta' dichiarata
        # nell'onboarding e' l'unico ancoraggio geografico che il profilo ha.
        home_city = getattr(user, "home_city", None) if user else None

        played = bool(
            _tournament_match_activities(user_id)
            or _individual_match_activities(user_id)
        )
        drilled = (
            db.session.query(ChallengeAttempt.id)
            .filter(
                ChallengeAttempt.user_id == user_id,
                ChallengeAttempt.completed.is_(True),
            )
            .first()
            is not None
        )

        steps = [
            {
                "done": True,
                "title": _("Account creato"),
                "subtitle": (
                    _("La tua città: %(city)s", city=home_city)
                    if home_city
                    else _("Il tuo profilo è attivo")
                ),
            },
            {
                "done": played,
                "title": _("Gioca il primo match"),
                "subtitle": _("Da qui parte il tuo Elo"),
            },
            {
                "done": drilled,
                "title": _("Prova un esercizio"),
                "subtitle": _("Sblocca il punteggio di precisione"),
            },
        ]
        done = sum(1 for s in steps if s["done"])
        return {
            "title": _("Il tuo profilo è pronto"),
            "subtitle": _("Fai la prima attività e qui comparirà il tuo andamento."),
            "intro": _(
                "Il tuo Elo parte da 1200: si muove alla prima partita registrata."
            ),
            "steps": steps,
            "done": done,
            "total": len(steps),
            "ring_pct": round(done / len(steps) * 100),
        }


def _build_player(
    *,
    user_id: int,
    profile: str,
    window: Sequence[Activity],
    elo_series: Sequence[int],
    elo_delta: Optional[int],
    elo_at_high: bool,
    elo_current: Optional[int],
    tpa: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Le quattro parti fisse (titolo, metriche, grafico, striscia) per un giocatore."""
    matches = [a for a in window if a.kind == "match"]
    garas = [a for a in window if a.kind == "gara"]
    drills = [a for a in window if a.kind == "drill"]

    # L'attivita' dominante: piu' eventi nella finestra, a parita' la piu' recente.
    dominant = max(
        (group for group in (matches, garas, drills) if group),
        key=lambda group: (len(group), max(a.at for a in group)),
        default=[],
    )
    dominant_kind = dominant[0].kind if dominant else "match"

    block: Dict[str, Any] = {
        "title": _("Come stai andando"),
        "context_badge": None,
        "note": None,
        "primary": None,
        "secondary": None,
        "chart": None,
        "strip": None,
    }

    # ── Metrica primaria ────────────────────────────────────────────────────
    if profile == "drill_only":
        block["primary"] = _drill_primary(user_id, drills)
    elif elo_current is not None:
        label = _("Elo gara") if profile == "competition_only" else _("Elo")
        if not elo_series:
            # L'Elo c'e' — la colonna sincronizzata su `User` e' la fonte
            # autorevole — ma lo storico dei delta no: partite chiuse prima che
            # il registro esistesse, o un ricalcolo mai lanciato. Il valore si
            # mostra lo stesso, senza delta e senza sparkline: dire «quanto sei
            # salito» qui vorrebbe dire inventarselo.
            block["primary"] = _metric(label, str(elo_current))
        elif profile == "returning":
            block["primary"] = _metric(
                _("Elo, invariato"), str(elo_current), delta=_("ti aspetta lì")
            )
        else:
            # Su quante partite e' maturato quel delta: si contano gli eventi
            # di **rating**, non le attivita' della finestra. Le due cose non
            # coincidono — chi ha dieci attivita' ma una sola riga di storico
            # si vedeva scritto «−16 in 10 partite» per un −16 maturato in una
            # partita sola. La finestra dice quanto ha giocato, la serie dice
            # su cosa il numero e' stato calcolato: accanto al delta va la
            # seconda.
            rated = max(len(elo_series) - 1, 1)
            delta_text, tone = _delta_text(
                elo_delta,
                (
                    # Al super attivo si aggiunge « · massimo»: la forma lunga
                    # («in 10 partite · massimo») va a capo e spezza la cella.
                    _("in %(num)s", num=rated)
                    if profile == "hyperactive"
                    else (
                        ngettext("in %(num)s partita", "in %(num)s partite", rated)
                        if dominant_kind == "match"
                        else ngettext("in %(num)s gara", "in %(num)s gare", rated)
                    )
                ),
            )
            # «massimo» si scrive solo se lo e' davvero, su tutto lo storico.
            # La chiamata sta fuori dalla f-string di proposito: l'estrattore
            # di Babel legge una f-string come un unico token e non vedrebbe
            # il `_()` dentro — la stringa resterebbe in italiano per sempre,
            # senza che niente lo segnali.
            if profile == "hyperactive" and elo_at_high:
                massimo = _("massimo")
                delta_text = f"{delta_text} · {massimo}"
            block["primary"] = _metric(
                label, str(elo_current), delta=delta_text, delta_tone=tone
            )
    else:
        # Nessun Elo da nessuna parte. Il posto lo prende la metrica successiva
        # **vera**, non un conteggio delle attivita': quello sarebbe il numero
        # di tessere disegnate due centimetri piu' sotto, e non direbbe niente
        # che la striscia non dica gia'.
        block["primary"] = _no_elo_primary(matches, garas)

    # ── Metrica secondaria ──────────────────────────────────────────────────
    if tpa is not None and profile != "drill_only":
        delta_text, tone = _tpa_delta_text(tpa["delta"])
        block["secondary"] = _metric(
            _("TPA di carriera"),
            _tpa_value(tpa["career"]),
            delta=delta_text,
            delta_tone=tone,
        )
    elif profile == "drill_only":
        block["secondary"] = _drill_secondary(drills)
    elif profile == "competition_only":
        block["secondary"] = _metric(
            _("Miglior piazzamento"),
            min(a.text for a in garas) if garas else "—",
            delta=ngettext("in %(num)s gara", "in %(num)s gare", len(garas)),
        )
    elif profile == "returning":
        block["secondary"] = _metric(
            _("Match giocati"),
            str(len(matches)),
            delta=_(
                "%(won)s vinti",
                won=sum(1 for a in matches if a.outcome == "win"),
            ),
        )
    elif matches:
        block["secondary"] = _results_donut(matches)

    # ── Grafico ─────────────────────────────────────────────────────────────
    if profile == "drill_only":
        block["chart"] = _drill_chart(user_id, drills)
    elif elo_series:
        legend = []
        if tpa is not None and len(tpa["series"]) >= MIN_POINTS_FOR_CHART:
            legend = [
                {"kind": "solid", "label": _("Elo")},
                {"kind": "dashed", "label": _("TPA")},
            ]
        block["chart"] = _line_chart(
            elo_series,
            labels=_elo_labels(elo_series, profile, window),
            positive=(elo_delta or 0) > 0,
            secondary=tpa["series"] if tpa else None,
            legend=legend,
            projected=(profile == "returning"),
            declining=(profile == "declining"),
        )

    # ── Striscia ────────────────────────────────────────────────────────────
    block["strip"] = _strip(
        window,
        label=_strip_label(dominant_kind, mixed=len({a.kind for a in window}) > 1),
        note=_("dalla più vecchia"),
    )

    # ── Tono, badge e nota ──────────────────────────────────────────────────
    if profile == "returning":
        weeks = max(1, (utc_now() - max(a.at for a in window)).days // 7)
        block["title"] = _("Dove eri rimasto")
        block["context_badge"] = {
            "text": ngettext("%(num)s settimana fa", "%(num)s settimane fa", weeks),
            "tone": "neutral",
        }
        block["strip"]["note"] = ""
    elif profile == "hyperactive":
        recent = activities_since(user_id, utc_now() - timedelta(days=HYPERACTIVE_DAYS))
        block["context_badge"] = {
            "text": ngettext(
                "%(num)s attività nel mese",
                "%(num)s attività nel mese",
                recent,
            ),
            "tone": "positive",
        }
    elif profile == "declining" and tpa is not None and (tpa["delta"] or 0) > 0:
        block["note"] = _(
            "L'Elo è scivolato, ma la tua precisione al tavolo continua a crescere."
        )

    return block


def _no_elo_primary(
    matches: Sequence[Activity], garas: Sequence[Activity]
) -> Dict[str, Any]:
    """La prima cella quando l'Elo non esiste ancora.

    Succede a chi ha giocato prima che il rating venisse calcolato, o le cui
    partite sono state chiuse senza passare dal motore. Al posto dell'Elo va
    un fatto che il giocatore riconosce — quante ne ha vinte, o dov'e' arrivato
    — non il numero di attivita', che e' solo la lunghezza della striscia.
    """
    if matches:
        won = sum(1 for a in matches if a.outcome == "win")
        return _metric(
            _("Partite vinte"),
            str(won),
            delta=ngettext("su %(num)s giocata", "su %(num)s giocate", len(matches)),
        )
    if garas:
        best = min(garas, key=lambda a: a.text)
        return _metric(
            _("Miglior piazzamento"),
            best.text,
            delta=ngettext("in %(num)s gara", "in %(num)s gare", len(garas)),
        )
    return _metric(_("Attività recenti"), str(len(matches) + len(garas)))


def _strip_label(kind: str, *, mixed: bool) -> str:
    if mixed:
        return _("Le tue ultime attività")
    return {
        "match": _("Le tue ultime partite"),
        "gara": _("Le tue ultime gare"),
        "drill": _("I tuoi ultimi esercizi"),
    }.get(kind, _("Le tue ultime attività"))


def _elo_labels(
    series: Sequence[int], profile: str, window: Sequence[Activity]
) -> Dict[str, str]:
    if profile == "returning":
        last = max(a.at for a in window)
        return {
            "start": _("ultima partita %(date)s", date=last.strftime("%d/%m")),
            "end": _("oggi"),
        }
    return {
        "start": _("%(value)s all'inizio", value=series[0]),
        "end": _("oggi %(value)s", value=series[-1]),
    }


def _numeric_drills(drills: Sequence[Activity]) -> List[Activity]:
    """Nel dominio un drill pass/fail non ha punteggio: fuori dalle medie."""
    return [d for d in drills if d.outcome == "neutral"]


def _drill_primary(user_id: int, drills: Sequence[Activity]) -> Dict[str, Any]:
    """Il punteggio dei drill, quando ce n'e' uno da fare.

    `Challenge` non ha un massimo (il massimo e' per-esame, ADR-042), quindi
    non si scrive «78/100»: si scrive il punteggio, e basta.
    """
    values = _drill_scores(user_id, drills)
    if not values:
        return _metric(
            _("Esercizi completati"),
            str(len(drills)),
            delta=_("nella tua finestra recente"),
        )
    delta = values[-1] - values[0] if len(values) >= 2 else None
    delta_text, tone = _delta_text(
        delta,
        ngettext("in %(num)s sessione", "in %(num)s sessioni", len(values)),
    )
    return _metric(
        _("Punteggio esercizi"),
        str(values[-1]),
        delta=delta_text,
        delta_tone=tone,
    )


def _drill_scores(user_id: int, drills: Sequence[Activity]) -> List[int]:
    """I punteggi delle prove numeriche della finestra, in ordine di gioco."""
    from models.challenge.models import Challenge, ChallengeAttempt

    if not drills:
        return []
    oldest = min(d.at for d in drills)
    rows = (
        db.session.query(ChallengeAttempt.score)
        .join(Challenge, Challenge.id == ChallengeAttempt.challenge_id)
        .filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed.is_(True),
            Challenge.pass_fail_only.is_(False),
            ChallengeAttempt.score.isnot(None),
            ChallengeAttempt.attempted_at >= oldest,
        )
        .order_by(ChallengeAttempt.attempted_at.asc())
        .limit(WINDOW)
        .all()
    )
    return [row[0] for row in rows]


def _drill_secondary(drills: Sequence[Activity]) -> Optional[Dict[str, Any]]:
    """La torta dei drill superati — solo se ci sono drill pass/fail."""
    passed = sum(1 for d in drills if d.outcome == "win")
    failed = sum(1 for d in drills if d.outcome == "draw")
    if not (passed or failed):
        return _metric(_("Esercizi completati"), str(len(drills)))
    slices = [
        {
            "label": ngettext("%(num)s superato", "%(num)s superati", passed),
            "count": passed,
            "color_role": "ok",
        },
        {
            "label": ngettext("%(num)s fallito", "%(num)s falliti", failed),
            "count": failed,
            "color_role": "muted",
        },
    ]
    return _donut(
        [s for s in slices if s["count"]], center=f"{passed}/{passed + failed}"
    )


def _drill_chart(user_id: int, drills: Sequence[Activity]) -> Optional[Dict[str, Any]]:
    values = _drill_scores(user_id, drills)
    if len(values) < MIN_POINTS_FOR_CHART:
        return None
    return _bars_chart(
        values,
        labels={
            "start": _("%(value)s alla prima", value=values[0]),
            "end": _("%(value)s oggi", value=values[-1]),
        },
    )


def _build_director(user_id: int, garas: Sequence[Any]) -> Dict[str, Any]:
    """«Come vanno le tue gare»: il direttore vede il riempimento, non l'Elo."""
    from models.competition.models import Inscription

    counts = dict(
        db.session.query(Inscription.gara_id, db.func.count(Inscription.id))
        .filter(Inscription.gara_id.in_([g.id for g in garas]))
        .group_by(Inscription.gara_id)
        .all()
    )

    filled = [counts.get(g.id, 0) for g in garas]
    capacities = [g.max_participants or 0 for g in garas]

    block: Dict[str, Any] = {
        "title": _("Come vanno le tue gare"),
        "context_badge": None,
        "note": None,
        "primary": _metric(
            _("Gare organizzate"),
            str(len(garas)),
            delta=_("da quando sei direttore"),
        ),
        "secondary": None,
        "chart": None,
        "strip": None,
    }

    pending = _director_pending(user_id)
    if pending:
        block["context_badge"] = {
            "text": ngettext("%(num)s da chiudere", "%(num)s da chiudere", pending),
            "tone": "urgent",
        }

    seats = sum(c for c in capacities if c)
    taken = sum(f for f, c in zip(filled, capacities) if c)
    if seats:
        pct = round(taken / seats * 100)
        block["secondary"] = _donut(
            [
                {
                    "label": _("%(taken)s posti occupati", taken=taken),
                    "count": taken,
                    "color_role": "ok",
                },
                {
                    "label": _("%(free)s liberi", free=seats - taken),
                    "count": max(seats - taken, 0),
                    "color_role": "muted",
                },
            ],
            center=f"{pct}%",
        )
    else:
        total_inscriptions = sum(filled)
        block["secondary"] = _metric(
            _("Iscrizioni gestite"),
            str(total_inscriptions),
            delta=_("in tutte le tue gare"),
        )

    if len(filled) >= MIN_POINTS_FOR_CHART:
        block["chart"] = _bars_chart(
            filled,
            labels={
                "start": _(
                    "%(n)s iscritti a %(gara)s", n=filled[0], gara=garas[0].display_name
                ),
                "end": _("%(n)s a %(gara)s", n=filled[-1], gara=garas[-1].display_name),
            },
        )

    tail = list(zip(garas, filled))[-WINDOW:]
    block["strip"] = {
        "label": _("Le tue ultime gare"),
        "note": _("dalla più vecchia"),
        "dense": len(tail) > 6,
        "legend": [],
        "items": [
            {
                "text": f"{n}/{g.max_participants}" if g.max_participants else str(n),
                "icon": None,
                "outcome": _fill_outcome(n, g.max_participants),
                "title": _("%(gara)s, %(n)s iscritti", gara=g.display_name, n=n),
            }
            for g, n in tail
        ],
    }
    return block


def _fill_outcome(filled: int, capacity: Optional[int]) -> str:
    """Quanto e' piena una gara, tradotto nei quattro toni delle tessere."""
    if not capacity:
        return "neutral"
    ratio = filled / capacity
    if ratio >= 0.95:
        return "win"
    if ratio >= 0.6:
        return "neutral"
    return "draw"


__all__ = ["ActivityFeedbackService", "Activity", "has_any_activity"]
