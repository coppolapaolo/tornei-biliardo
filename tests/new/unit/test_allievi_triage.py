"""Le tre sezioni di «I miei allievi», e cosa ci mette dentro un allievo.

Questo file esiste perché il triage è il punto del lavoro in cui è più facile
scrivere una metrica che *sembra* vera. Un istruttore che legge «è costante»
ci crede, e nessuno va a controllare da dove viene il numero. Quindi ogni
definizione è qui, eseguibile, con il caso che la fa scattare **e** quello che
non la deve far scattare.

* **Valuta il passaggio di livello**: tante sedute di fila sopra la soglia
  quante la scheda ne chiede — la regola della fine seduta, non una nuova;
* **Da guardare**: due fatti, «non si allena da N giorni» e «da N sedute non
  supera il suo massimo»;
* **Tutto bene**: il resto. Non è una misura, e infatti non c'è nessun test
  che dica «è bravo»: c'è quello che dice che chi non rientra nelle prime due
  finisce lì, con sotto un fatto.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import List, Optional

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.istruttore import GruppoService, build_allievi
from models.istruttore.allievi_view import (
    GIORNI_ASSENZA,
    GIORNI_NUOVI,
    SEDUTE_SENZA_MIGLIORARE,
)
from models.training_sheet import (
    LevelUp,
    SheetItemSpec,
    SheetMeasure,
    TrainingSheetService,
)
from models.training_sheet.models import TrainingEntry, TrainingSession
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

ISTRUTTORE = GrantableRole.INSTRUCTOR

#: Il «quanto farne» di tutte le schede di questo file: le sedute valgono su 60.
SU_QUANTO = 60


# ── allestimento ────────────────────────────────────────────────────────────


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"tri_{uid}", email=f"tri_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


def _challenge() -> Challenge:
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=True,  # «riusciti» vuole un esito netto (ADR-072)
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def _scheda(
    allievo: User,
    istruttore: User,
    *,
    soglia: Optional[int] = None,
    serie: int = 1,
    nome: str = "Tecnica di base",
    livello: Optional[int] = 3,
    level_up: LevelUp = LevelUp.INSTRUCTOR,
):
    """Una scheda dell'allievo, aperta all'istruttore, che vale 60.

    Nasce con «lo conferma un istruttore» (D8) perché è la sola risposta che
    fa comparire qualcuno in «Valuta il passaggio di livello»: con `auto` il
    gradino se l'è già timbrato la soglia, e non c'è niente da valutare.
    """
    scheda = TrainingSheetService.create_sheet(allievo, nome)
    TrainingSheetService.save_composition(
        scheda.id,
        allievo,
        name=nome,
        items=[
            SheetItemSpec(
                challenge_id=_challenge().id,
                measure=SheetMeasure.MADE,
                amount=SU_QUANTO,
            )
        ],
        level=livello,
        threshold=soglia,
        threshold_streak=serie,
        level_up=level_up,
    )
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    return scheda


def _sedute(scheda, allievo: User, totali: List[int], *, ogni: int = 2) -> None:
    """Sedute chiuse con questi totali, **dalla più vecchia alla più recente**.

    ``ogni`` è la distanza in giorni fra una e l'altra, all'indietro da oggi:
    l'ultima della lista è quella di oggi.
    """
    voce = scheda.active_items[0]
    quante = len(totali)
    for posto, totale in enumerate(totali):
        quando = utc_now() - timedelta(days=(quante - 1 - posto) * ogni)
        seduta = TrainingSession(
            sheet_id=scheda.id,
            user_id=allievo.id,
            sheet_version=scheda.version,
            started_at=quando,
            ended_at=quando,
        )
        db.session.add(seduta)
        db.session.flush()
        db.session.add(
            TrainingEntry(
                session_id=seduta.id,
                item_id=voce.id,
                value=totale,
                measure=SheetMeasure.MADE.value,
                target_amount=SU_QUANTO,
            )
        )
    db.session.flush()


def _invecchia_il_permesso(scheda, giorni: int) -> None:
    """Sposta indietro la data in cui la scheda è stata aperta."""
    for lettore in scheda.readers:
        lettore.granted_at = utc_now() - timedelta(days=giorni)
    db.session.flush()


@pytest.fixture
def admin(db_session):
    return _user(UserRole.ADMIN.value)


@pytest.fixture
def luca(db_session, admin):
    istruttore = _user()
    RoleGrantService.grant(istruttore.id, ISTRUTTORE, admin)
    return istruttore


@pytest.fixture
def paolo(db_session):
    return _user()


def _riga(pagina, allievo: User):
    tutte = pagina.passaggio + pagina.guardare + pagina.bene
    trovate = [riga for riga in tutte if riga.persona.id == allievo.id]
    assert len(trovate) == 1, "un allievo sta in una sezione sola"
    return trovate[0]


# ── chi compare, e chi no ───────────────────────────────────────────────────


def test_senza_schede_aperte_non_c_e_nessun_allievo(db_session, luca):
    assert build_allievi(luca).vuota


def test_chi_ti_ha_appena_aperto_una_scheda_e_in_cima(db_session, luca, paolo):
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [40])

    pagina = build_allievi(luca)

    assert [riga.persona.id for riga in pagina.nuovi] == [paolo.id]
    # «Nuovo» non è una sezione a parte: la persona sta anche nel triage.
    assert pagina.totale == 1


def test_dopo_una_settimana_non_e_piu_una_novita(db_session, luca, paolo):
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [40])
    _invecchia_il_permesso(scheda, GIORNI_NUOVI + 1)

    assert build_allievi(luca).nuovi == []


# ── valuta il passaggio di livello ──────────────────────────────────────────


def test_il_gradino_raggiunto_chiede_una_decisione(db_session, luca, paolo):
    """Due sedute di fila sopra 48, e la scheda ne chiede due."""
    scheda = _scheda(paolo, luca, soglia=48, serie=2)
    _sedute(scheda, paolo, [46, 48, 51])

    pagina = build_allievi(luca)

    assert [riga.persona.id for riga in pagina.passaggio] == [paolo.id]
    assert _riga(pagina, paolo).segnale.tipo == "passaggio"


def test_il_segnale_del_gradino_mostra_i_numeri_e_la_soglia(db_session, luca, paolo):
    scheda = _scheda(paolo, luca, soglia=48, serie=2)
    _sedute(scheda, paolo, [46, 48, 51])

    frase = _riga(build_allievi(luca), paolo).segnale.frase

    assert "46, 48, 51" in frase
    assert "60" in frase
    assert "48" in frase


def test_una_sola_seduta_sopra_non_basta_se_ne_chiede_due(db_session, luca, paolo):
    """Un colpo di fortuna non è un livello raggiunto: lo dice la scheda."""
    scheda = _scheda(paolo, luca, soglia=48, serie=2)
    _sedute(scheda, paolo, [51, 46, 51])

    assert build_allievi(luca).passaggio == []


def test_una_scheda_che_si_promuove_da_sola_non_chiede_niente(db_session, luca, paolo):
    """Con `auto` il gradino l'ha già timbrato la soglia (D8): non c'è da valutare.

    L'allievo resta in elenco — è sempre un allievo — ma in un'altra sezione:
    mettere in «Valuta il passaggio» chi non ha bisogno di te sarebbe un invito
    a premere qualcosa che non esiste.
    """
    scheda = _scheda(paolo, luca, soglia=48, serie=2, level_up=LevelUp.AUTO)
    _sedute(scheda, paolo, [46, 48, 51])

    pagina = build_allievi(luca)

    assert pagina.passaggio == []
    assert _riga(pagina, paolo).segnale.tipo != "passaggio"


def test_una_scheda_senza_soglia_non_ha_gradini(db_session, luca, paolo):
    scheda = _scheda(paolo, luca, soglia=None)
    _sedute(scheda, paolo, [58, 59, 60])

    assert build_allievi(luca).passaggio == []


def test_il_gradino_viene_prima_di_tutto(db_session, luca, paolo):
    """Chiede una decisione: anche se poi è sparito, va detto."""
    scheda = _scheda(paolo, luca, soglia=48, serie=1)
    _sedute(scheda, paolo, [50], ogni=0)
    for seduta in scheda.sessions:
        seduta.ended_at = utc_now() - timedelta(days=GIORNI_ASSENZA + 10)
    db.session.flush()

    assert [riga.persona.id for riga in build_allievi(luca).passaggio] == [paolo.id]


# ── da guardare · non si allena ─────────────────────────────────────────────


def test_chi_non_chiude_una_seduta_da_due_settimane_va_guardato(
    db_session, luca, paolo
):
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [40, 42], ogni=1)
    for seduta in scheda.sessions:
        seduta.ended_at = utc_now() - timedelta(days=GIORNI_ASSENZA + 2)
    db.session.flush()

    riga = _riga(build_allievi(luca), paolo)

    assert riga.segnale.tipo == "assenza"
    assert str(GIORNI_ASSENZA + 2) in riga.segnale.frase


def test_una_settimana_saltata_non_e_un_allarme(db_session, luca, paolo):
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [40, 42], ogni=1)
    for seduta in scheda.sessions:
        seduta.ended_at = utc_now() - timedelta(days=GIORNI_ASSENZA - 2)
    db.session.flush()

    assert _riga(build_allievi(luca), paolo).segnale.tipo == "sereno"


def test_chi_ha_appena_aperto_la_scheda_non_e_assente(db_session, luca, paolo):
    """Non ha ancora cominciato, e non è la stessa cosa che aver smesso."""
    _scheda(paolo, luca)

    riga = _riga(build_allievi(luca), paolo)

    assert riga.segnale.tipo == "sereno"
    assert riga.nuovo


def test_chi_non_ha_mai_cominciato_dopo_due_settimane_va_guardato(
    db_session, luca, paolo
):
    scheda = _scheda(paolo, luca)
    _invecchia_il_permesso(scheda, GIORNI_ASSENZA + 1)

    riga = _riga(build_allievi(luca), paolo)

    assert riga.segnale.tipo == "assenza"


# ── da guardare · non supera il suo massimo ─────────────────────────────────


def test_chi_non_supera_il_suo_massimo_da_cinque_sedute(db_session, luca, paolo):
    """Il 38 è la sesta seduta a ritroso: da allora, cinque sotto."""
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [38, 35, 36, 34, 37, 33], ogni=2)

    riga = _riga(build_allievi(luca), paolo)

    assert riga.segnale.tipo == "stallo"
    assert "38" in riga.segnale.frase


def test_chi_lo_supera_non_e_in_stallo(db_session, luca, paolo):
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [38, 35, 36, 34, 37, 41], ogni=2)

    assert _riga(build_allievi(luca), paolo).segnale.tipo == "sereno"


def test_senza_una_seduta_prima_del_blocco_non_si_puo_dire(db_session, luca, paolo):
    """Con esattamente cinque sedute non c'è un massimo «di allora»."""
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [35] * SEDUTE_SENZA_MIGLIORARE, ogni=2)

    assert _riga(build_allievi(luca), paolo).segnale.tipo == "sereno"


def test_chi_e_al_massimo_possibile_non_e_in_stallo(db_session, luca, paolo):
    """Ha finito i numeri disponibili: dirgli che non sale sarebbe falso."""
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [SU_QUANTO] * 6, ogni=2)

    assert _riga(build_allievi(luca), paolo).segnale.tipo == "sereno"


def test_l_assenza_viene_prima_dello_stallo(db_session, luca, paolo):
    """A chi non si allena da tre settimane non si parla di punteggio."""
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [38, 35, 36, 34, 37, 33], ogni=2)
    for seduta in scheda.sessions:
        seduta.ended_at -= timedelta(days=GIORNI_ASSENZA + 1)
    db.session.flush()

    assert _riga(build_allievi(luca), paolo).segnale.tipo == "assenza"


# ── tutto bene: il resto, con un fatto sotto ────────────────────────────────


def test_chi_non_rientra_nelle_prime_due_sta_nel_resto(db_session, luca, paolo):
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [30, 34, 38, 41], ogni=3)

    pagina = build_allievi(luca)

    assert [riga.persona.id for riga in pagina.bene] == [paolo.id]


def test_sotto_il_nome_c_e_un_fatto_non_un_giudizio(db_session, luca, paolo):
    scheda = _scheda(paolo, luca)
    _sedute(scheda, paolo, [30, 34, 38, 41], ogni=3)

    frase = _riga(build_allievi(luca), paolo).segnale.frase

    assert "oggi" in frase
    assert "4" in frase  # quattro sedute nelle ultime quattro settimane


# ── i gruppi filtrano, e nient'altro ────────────────────────────────────────


def test_un_gruppo_filtra_gli_allievi(db_session, luca, paolo):
    altro = _user()
    _scheda(paolo, luca)
    _scheda(altro, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    pagina = build_allievi(luca, gruppo)

    assert pagina.totale == 1
    assert _riga(pagina, paolo).gruppo.id == gruppo.id


def test_senza_filtro_ci_sono_tutti(db_session, luca, paolo):
    altro = _user()
    _scheda(paolo, luca)
    _scheda(altro, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    pagina = build_allievi(luca)

    assert pagina.totale == 2
    assert [g.id for g in pagina.gruppi] == [gruppo.id]


def test_chi_ti_ha_richiuso_la_scheda_sparisce_anche_dal_gruppo(
    db_session, luca, paolo
):
    """La riga del gruppo resta, ma questa è la pagina di chi si allena."""
    scheda = _scheda(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)
    TrainingSheetService.remove_reader(scheda.id, luca.id, paolo)

    assert build_allievi(luca).vuota
    assert build_allievi(luca, gruppo).vuota
    assert [m.user_id for m in gruppo.active_members] == [paolo.id]
