"""Le colonne enum non devono dipendere dai **nomi** dei membri Python.

Il 2026-08-17 il rinomino di `MatchStatus.COMPLETED`/`VALIDATED` in
`CLOSED_UNILATERALLY`/`CONFIRMED_BY_BOTH` (PR #125) ha mandato la dashboard in
500 su ogni installazione con dati preesistenti:

    LookupError: 'VALIDATED' is not among the defined enum values.
                 Enum name: matchstatus.

Il rinomino aveva verificato che i **valori** restassero `"completed"` e
`"validated"`, ed era vero — ma `individual_match.status` era mappata come
`db.Enum(MatchStatus)` senza `values_callable`, e SQLAlchemy in quel caso
persiste il **nome del membro**. Sul disco c'era `VALIDATED`.

Perché i 3747 test non l'hanno visto: creano le righe e le rileggono nello
stesso processo, quindi scrivono e ricaricano lo stesso nome nuovo, in modo
perfettamente coerente. Un round-trip non può rivelare un disallineamento con
dati **già scritti**: bisogna metterceli, quei dati, nella forma in cui stanno
sul disco. È quello che fa la prima classe qui sotto, ed è la forma di test che
mancava.

La seconda classe è il presidio generale: elenca tutte le colonne `db.Enum` che
ancora salvano i nomi, così rinominare un membro di quegli enum resta una
decisione presa e non un effetto collaterale scoperto in produzione.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Enum as SAEnum, text

from models.base import db, utc_now
from models.individual_match.models import IndividualMatch
from models.status_enum import MatchStatus

# ══ La colonna che si era rotta ══════════════════════════════════════════════


@pytest.fixture
def partita_casual(db_session):
    """Una partita casual, creata via ORM."""
    from models.user.models import User

    giocatori = []
    for numero in (1, 2):
        utente = User(
            username=f"casual{numero}",
            email=f"casual{numero}@example.test",
            role="player",
        )
        utente.set_password("password")
        db_session.add(utente)
        giocatori.append(utente)
    db_session.flush()

    partita = IndividualMatch(
        player1_id=giocatori[0].id,
        player2_id=giocatori[1].id,
        scheduled_at=utc_now(),
        status=MatchStatus.CONFIRMED_BY_BOTH,
    )
    db_session.add(partita)
    db_session.commit()
    return partita


@pytest.mark.unit
def test_su_disco_finisce_il_valore_non_il_nome_del_membro(db_session, partita_casual):
    """Il cuore della correzione, letto col SQL grezzo.

    Se qui comparisse `CONFIRMED_BY_BOTH`, la colonna dipenderebbe di nuovo dai
    nomi Python e il prossimo rinomino romperebbe di nuovo i dati esistenti.
    """
    scritto = db_session.execute(
        text("SELECT status FROM individual_match WHERE id = :id"),
        {"id": partita_casual.id},
    ).scalar()

    assert scritto == "validated"
    assert scritto == MatchStatus.CONFIRMED_BY_BOTH.value


@pytest.mark.unit
def test_una_riga_gia_sul_disco_si_rilegge(db_session, partita_casual):
    """La forma di test che mancava: dato scritto **prima**, letto via ORM.

    Un round-trip nello stesso processo non poteva accorgersi di nulla —
    scriveva e rileggeva la stessa rappresentazione, qualunque fosse. Qui il
    valore viene messo con SQL grezzo, come se ce l'avesse lasciato una
    versione precedente dell'applicazione.
    """
    db_session.execute(
        text("UPDATE individual_match SET status = 'completed' WHERE id = :id"),
        {"id": partita_casual.id},
    )
    db_session.commit()
    db_session.expire_all()

    riletta = db_session.get(IndividualMatch, partita_casual.id)
    assert riletta is not None
    assert riletta.status == MatchStatus.CLOSED_UNILATERALLY


@pytest.mark.unit
def test_i_filtri_per_stato_continuano_a_funzionare(db_session, partita_casual):
    """La query passa dall'enum, non dalla stringa: deve tradurre nel valore."""
    trovate = IndividualMatch.query.filter(
        IndividualMatch.status == MatchStatus.CONFIRMED_BY_BOTH
    ).all()

    assert partita_casual.id in [p.id for p in trovate]


# ══ Il presidio generale ════════════════════════════════════════════════════


#: Colonne `db.Enum` che salvano ancora il **nome** del membro.
#:
#: Non è un elenco di difetti da correggere subito: convertirle costa una
#: migration ciascuna, e finché nessuno rinomina un membro di quegli enum non
#: succede niente. È un elenco di **avvertimenti**: rinominare un membro di uno
#: di questi enum rende illeggibili le righe già scritte, esattamente come il
#: 2026-08-17, e va accompagnato da una migration sui dati.
COLONNE_CHE_SALVANO_I_NOMI = {
    "achievement.category",
    "achievement.difficulty",
    "leaderboard_entry.leaderboard_type",
    "match_proposal.proposal_type",
    "match_proposal.status",
    "match_rating_history.rating_system",
    "notification.notification_type",
    "notification.priority",
    "notification.status",
    "notification_preference.notification_type",
    "notification_template.default_priority",
    "notification_template.notification_type",
    "player_rating.rating_system",
    "playoff_configuration.playoff_type",
    "playoff_qualification.status",
    "proposal_invitation.status",
    "quest.quest_type",
    "quest.status",
    "streak_tracker.streak_type",
    "xp_transaction.transaction_type",
}


def _colonne_enum():
    """(nome_qualificato, colonna) per ogni colonna `db.Enum` del metadata."""
    for tabella in db.metadata.sorted_tables:
        for colonna in tabella.columns:
            if isinstance(colonna.type, SAEnum) and colonna.type.enum_class:
                yield f"{tabella.name}.{colonna.name}", colonna


@pytest.mark.unit
def test_individual_match_status_salva_i_valori(app):
    """La colonna che si era rotta non deve tornare a salvare i nomi."""
    colonne = dict(_colonne_enum())
    colonna = colonne["individual_match.status"]

    assert colonna.type.values_callable is not None, (
        "individual_match.status è tornata a salvare i nomi dei membri: un "
        "rinomino in MatchStatus renderebbe di nuovo illeggibili le righe già "
        "scritte (incidente 2026-08-17)"
    )


@pytest.mark.unit
def test_l_elenco_delle_colonne_a_nomi_e_aggiornato(app):
    """Una colonna `db.Enum` nuova va guardata in faccia, non aggiunta di
    soppiatto.

    Se questo test cade, hai introdotto (o convertito) una colonna enum:
    decidi se deve salvare i valori — `values_callable=lambda e: [m.value for
    m in e]`, la scelta giusta per un dominio i cui nomi possono cambiare — e
    se no, aggiungila all'elenco sapendo cosa comporta.
    """
    a_nomi = {
        nome
        for nome, colonna in _colonne_enum()
        if colonna.type.values_callable is None
    }

    assert a_nomi == COLONNE_CHE_SALVANO_I_NOMI, (
        "elenco disallineato.\n"
        f"  nuove a nomi: {sorted(a_nomi - COLONNE_CHE_SALVANO_I_NOMI)}\n"
        f"  non più a nomi: {sorted(COLONNE_CHE_SALVANO_I_NOMI - a_nomi)}"
    )
