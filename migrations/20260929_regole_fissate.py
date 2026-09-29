"""Le regole si fissano sulla partita (ADR-075).

Cinque colonne nuove su `match`:

* `start_rule`, `break_rule` — chi apre e chi spacca;
* `set_distance` — triangoli per set, nelle partite a set;
* `x_with_challenge` — sulle X: si sostituiscono con una prova?
* `categories_snapshot` — le categorie dei giocatori (JSON), che in una gara
  con handicap decidono se la partita conta per l'ELO.

E un **riempimento** delle partite esistenti, anche delle colonne che c'erano
già ma valevano NULL = «eredita dalla gara» (`is_race_to`, `is_race_to_sets`,
`discipline`, `has_handicap`). Il valore scritto è quello che l'app usa **oggi**
leggendo la gara (e il campionato), con le stesse catene di ripiego:

* chi apre: gara → campionato → `first_player` (il comportamento storico);
* chi spacca: gara → campionato → `alternate`;
* handicap: gara → campionato → no;
* categorie: quelle scritte oggi sulle iscrizioni.

Quindi nessuna partita cambia comportamento: da qui in poi, però, un cambio
della gara non le raggiunge più. Tocca solo i valori NULL: rilanciata, non fa
niente.

Una tabella o una colonna assente è un no-op dichiarato, non un errore: una
migration che solleva non viene marcata applicata e `auto_deploy` la ritenta
ogni notte per niente.
"""

import json
import sqlite3

migration_name = "20260929_regole_fissate"

COLONNE = (
    ("start_rule", "VARCHAR(20)"),
    ("break_rule", "VARCHAR(20)"),
    ("set_distance", "INTEGER"),
    ("x_with_challenge", "BOOLEAN"),
    ("categories_snapshot", "TEXT"),
)

INIZIO = {"first_player", "lag"}
APERTURA = {"alternate", "winner_breaks", "loser_breaks", "alternate_two"}


def _valida(valore, ammessi):
    return valore if valore in ammessi else None


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        presenti = _colonne(cursor, "match")
        if not presenti:
            print("  match non esiste ancora: niente da fare")
            return
        for colonna, tipo in COLONNE:
            if colonna not in presenti:
                cursor.execute(f"ALTER TABLE match ADD COLUMN {colonna} {tipo}")
                print(f"  ✓ match.{colonna}")

        _riempi(cursor)
        conn.commit()
    finally:
        conn.close()


def _riempi(cursor) -> None:
    colonne_gara = _colonne(cursor, "gara")
    colonne_camp = _colonne(cursor, "campionato")
    if not colonne_gara:
        return

    def campo(nome, colonne, alias):
        return f"{alias}.{nome}" if nome in colonne else "NULL"

    gare = {}
    query_gare = f"""
        SELECT g.id, g.is_race_to, {campo('is_race_to_sets', colonne_gara, 'g')},
               g.discipline, {campo('has_handicap', colonne_gara, 'g')},
               {campo('start_rule', colonne_gara, 'g')},
               {campo('break_rule', colonne_gara, 'g')},
               g.distance, {campo('odd_number_policy', colonne_gara, 'g')},
               {campo('has_handicap', colonne_camp, 'c')},
               {campo('default_start_rule', colonne_camp, 'c')},
               {campo('default_break_rule', colonne_camp, 'c')}
        FROM gara g LEFT JOIN campionato c ON c.id = g.campionato_id
        """
    for riga in cursor.execute(query_gare):
        (
            gid,
            irt,
            irts,
            disc,
            hh,
            sr,
            br,
            dist,
            odd,
            c_hh,
            c_sr,
            c_br,
        ) = riga
        if hh is not None:
            handicap = bool(hh)
        else:
            handicap = bool(c_hh) if c_hh is not None else False
        gare[gid] = {
            "is_race_to": irt,
            "is_race_to_sets": irts,
            "discipline": disc,
            "has_handicap": 1 if handicap else 0,
            "start_rule": _valida(sr, INIZIO)
            or _valida(c_sr, INIZIO)
            or "first_player",
            "break_rule": _valida(br, APERTURA)
            or _valida(c_br, APERTURA)
            or "alternate",
            "distance": dist,
            "x_with_challenge": 1 if odd == "bye_with_challenge" else 0,
        }

    categorie = {}
    if _colonne(cursor, "inscription"):
        query_iscrizioni = (
            "SELECT gara_id, user_id, categoria_id FROM inscription "
            "ORDER BY is_withdrawn DESC, id ASC"
        )
        for gara_id, user_id, cat in cursor.execute(query_iscrizioni):
            categorie[(gara_id, user_id)] = cat

    trii = {}
    if _colonne(cursor, "trio_match"):
        for match_id, p1, p2, p3 in cursor.execute(
            "SELECT match_id, player1_id, player2_id, player3_id FROM trio_match"
        ):
            trii[match_id] = (p1, p2, p3)

    partite = cursor.execute("""
        SELECT id, gara_id, player1_id, player2_id, is_bye, is_multi_set,
               is_race_to, is_race_to_sets, discipline, has_handicap,
               start_rule, break_rule, set_distance, x_with_challenge,
               categories_snapshot
        FROM match WHERE gara_id IS NOT NULL
        """).fetchall()

    toccate = 0
    for (
        mid,
        gid,
        p1,
        p2,
        is_bye,
        multi,
        irt,
        irts,
        disc,
        hh,
        sr,
        br,
        sd,
        xwc,
        snap,
    ) in partite:
        g = gare.get(gid)
        if g is None:
            continue
        nuovi = {}
        if irt is None and g["is_race_to"] is not None:
            nuovi["is_race_to"] = g["is_race_to"]
        if irts is None and g["is_race_to_sets"] is not None:
            nuovi["is_race_to_sets"] = g["is_race_to_sets"]
        if not disc and g["discipline"]:
            nuovi["discipline"] = g["discipline"]
        if hh is None:
            nuovi["has_handicap"] = g["has_handicap"]
        if sr is None:
            nuovi["start_rule"] = g["start_rule"]
        if br is None:
            nuovi["break_rule"] = g["break_rule"]
        if multi and sd is None and g["distance"]:
            nuovi["set_distance"] = g["distance"]
        if is_bye and xwc is None:
            nuovi["x_with_challenge"] = g["x_with_challenge"]
        if snap is None:
            giocatori = [p for p in (p1, p2, *trii.get(mid, ())) if p]
            if giocatori:
                nuovi["categories_snapshot"] = json.dumps(
                    {str(p): categorie.get((gid, p)) for p in sorted(set(giocatori))}
                )
        if not nuovi:
            continue
        assegnazioni = ", ".join(f"{colonna} = ?" for colonna in nuovi)
        cursor.execute(
            f"UPDATE match SET {assegnazioni} WHERE id = ?", (*nuovi.values(), mid)
        )
        toccate += 1
    print(f"  ✓ regole fissate su {toccate} partite")


if __name__ == "__main__":
    upgrade_sqlite()
