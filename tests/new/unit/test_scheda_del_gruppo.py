"""La scheda del gruppo, la media, le sedute, «N al livello dopo» (fase 8d₃).

Ogni test qui difende **una** definizione contro la definizione sbagliata che
le somiglia — che è l'unico modo per accorgersi di una metrica inventata:

* la media si fa sull'ultima seduta di **ciascuno**, non su tutte le sedute
  (chi si allena di più sposterebbe la media da solo) e si fa in **quota**,
  non sui totali grezzi (una seduta a metà ha un massimo più basso, una copia
  può essere stata cambiata dal suo proprietario);
* «l'hanno presa in 4 su 5» conta le proposte **partite**, e chi non l'ha
  ricevuta si dice a parte;
* «N al livello dopo» conta i timbri (`passed_at`) caduti **mentre** la
  persona era nel gruppo e **mentre** l'istruttore leggeva quella scheda: non
  le proposte di promozione, che con `level_up=auto` non esistono nemmeno.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.istruttore import AssegnazioneService, GruppoService, build_allievi
from models.istruttore.gruppo_view import (
    build_gruppo,
    esiti_dei_corsi,
    media_del_gruppo,
    scheda_del_gruppo,
    sedute_della_settimana,
    settimana_del_corso,
)
from models.istruttore.allievi_view import sedute_per_scheda
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.training_sheet.measure import LevelUp
from models.training_sheet.session_service import TrainingSessionService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

ISTRUTTORE = GrantableRole.INSTRUCTOR


# ── allestimento ────────────────────────────────────────────────────────────


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"grv_{uid}", email=f"grv_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


def _challenge() -> Challenge:
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=False,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def _componi(scheda, proprietario, *, amount: int = 10, **extra):
    """Una scheda con una voce «a riusciti»: il totale è `amount`."""
    TrainingSheetService.save_composition(
        scheda.id,
        proprietario,
        name=scheda.name,
        items=[
            SheetItemSpec(
                challenge_id=_challenge().id, measure=SheetMeasure.MADE, amount=amount
            )
        ],
        **extra,
    )
    return scheda


def _scheda_aperta_a(allievo: User, istruttore: User, nome: str = "Tecnica", **extra):
    """Una scheda dell'allievo, con l'istruttore fra i lettori."""
    scheda = _componi(
        TrainingSheetService.create_sheet(allievo, nome), allievo, **extra
    )
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    return scheda


def _seduta(scheda, allievo: User, valore: int, *, quando=None):
    """Una seduta chiusa con quel numero nella prima casella."""
    seduta = TrainingSessionService.start(scheda.id, allievo)
    TrainingSessionService.record(
        seduta.id, scheda.active_items[0].id, allievo, value=valore
    )
    TrainingSessionService.close(seduta.id, allievo)
    if quando is not None:
        seduta.ended_at = quando
        db.session.flush()
    return seduta


@pytest.fixture
def admin(db_session):
    return _user(UserRole.ADMIN.value)


@pytest.fixture
def luca(db_session, admin):
    """L'istruttore."""
    user = _user()
    RoleGrantService.grant(user.id, ISTRUTTORE, admin)
    return user


@pytest.fixture
def corso(db_session, luca):
    return GruppoService.crea(luca, "Base 1", date.today() - timedelta(days=3))


def _allievo_nel(corso, luca, **extra):
    """Un giocatore che apre una scheda a Luca ed entra nel corso."""
    allievo = _user()
    scheda = _scheda_aperta_a(allievo, luca, **extra)
    GruppoService.aggiungi(corso.id, luca, allievo.id)
    return allievo, scheda


def _vista(luca, corso):
    tutti = build_allievi(luca)
    return build_gruppo(
        luca,
        corso,
        [r for r in tutti.righe if r.gruppo and r.gruppo.id == corso.id],
        [r for r in tutti.righe if r.iscrizione is None],
    )


def _righe_dentro(luca, corso):
    tutti = build_allievi(luca)
    return [r for r in tutti.righe if r.gruppo and r.gruppo.id == corso.id]


# ── la scheda del gruppo ────────────────────────────────────────────────────


def test_senza_proposte_il_gruppo_non_ha_una_scheda(db_session, luca, corso):
    _allievo_nel(corso, luca)
    assert scheda_del_gruppo(corso, _righe_dentro(luca, corso)) is None


def test_i_numeri_del_giro_contano_le_proposte_partite(db_session, luca, corso):
    """«Presa in 2 su 3»: il denominatore sono le proposte, non gli allievi."""
    allievi = [_allievo_nel(corso, luca)[0] for _ in range(3)]
    modello = _componi(TrainingSheetService.create_sheet(luca, "Del corso"), luca)

    nate = AssegnazioneService.proponi(
        luca, modello.id, [a.id for a in allievi], group_id=corso.id
    )
    AssegnazioneService.accetta(nate[0].id, allievi[0])
    AssegnazioneService.accetta(nate[1].id, allievi[1])

    scheda = scheda_del_gruppo(corso, _righe_dentro(luca, corso))
    assert scheda is not None
    assert scheda.modello.id == modello.id
    assert (scheda.prese, scheda.mandate) == (2, 3)
    assert scheda.in_attesa == 1
    assert scheda.senza == []


def test_chi_e_arrivato_dopo_non_conta_fra_i_no(db_session, luca, corso):
    """Non l'ha rifiutata: non l'ha mai ricevuta, ed è una cosa da fare."""
    primo, _ = _allievo_nel(corso, luca)
    modello = _componi(TrainingSheetService.create_sheet(luca, "Del corso"), luca)
    nate = AssegnazioneService.proponi(luca, modello.id, [primo.id], group_id=corso.id)
    AssegnazioneService.accetta(nate[0].id, primo)

    tardi, _ = _allievo_nel(corso, luca)

    scheda = scheda_del_gruppo(corso, _righe_dentro(luca, corso))
    assert scheda is not None
    assert (scheda.prese, scheda.mandate) == (1, 1)
    assert [p.id for p in scheda.senza] == [tardi.id]


def test_una_copia_richiusa_esce_dalle_letture_non_dalle_prese(db_session, luca, corso):
    """Prenderla e fartela leggere sono due decisioni (ADR-071)."""
    allievo, _ = _allievo_nel(corso, luca)
    modello = _componi(TrainingSheetService.create_sheet(luca, "Del corso"), luca)
    nate = AssegnazioneService.proponi(
        luca, modello.id, [allievo.id], group_id=corso.id
    )
    copia = AssegnazioneService.accetta(nate[0].id, allievo)

    TrainingSheetService.remove_reader(copia.id, luca.id, allievo)

    scheda = scheda_del_gruppo(corso, _righe_dentro(luca, corso))
    assert scheda is not None
    assert scheda.prese == 1
    assert scheda.lette == 0


# ── la media ────────────────────────────────────────────────────────────────


def _corso_con_copie(luca, corso, valori):
    """Un corso in cui ciascuno ha preso la scheda comune e segnato quei numeri.

    ``valori`` è una lista di liste: per ogni allievo, le sedute in ordine
    cronologico (l'ultima è l'ultima chiusa).
    """
    modello = _componi(TrainingSheetService.create_sheet(luca, "Del corso"), luca)
    for sedute in valori:
        allievo, _ = _allievo_nel(corso, luca)
        nate = AssegnazioneService.proponi(
            luca, modello.id, [allievo.id], group_id=corso.id
        )
        copia = AssegnazioneService.accetta(nate[0].id, allievo)
        for valore in sedute:
            _seduta(copia, allievo, valore)
    return modello


def test_la_media_e_sull_ultima_seduta_di_ciascuno(db_session, luca, corso):
    """Chi si allena tre volte non sposta la media da solo.

    Con le sedute tutte insieme la media sarebbe (2+4+10+4)/4 = 5 su 10; una
    seduta a testa dà (10+4)/2 = 7.
    """
    _corso_con_copie(luca, corso, [[2, 4, 10], [4]])

    vista = _vista(luca, corso)
    assert vista.media is not None
    assert (vista.media.valore, vista.media.su) == (7, 10)
    assert vista.media.schede == 2


def test_la_media_e_in_quota_e_non_sui_totali_grezzi(db_session, luca, corso):
    """La copia è dell'allievo, e lui può cambiarla: le scale divergono.

    Uno fa 5 su 10, l'altro si è ridotto la scheda a 4 tiri e fa 2 su 4. In
    quota sono 50% e 50%, cioè 5 sulla scala della scheda del gruppo. Sommare i
    numeri grezzi darebbe 3,5.
    """
    modello = _componi(TrainingSheetService.create_sheet(luca, "Del corso"), luca)

    pieno, _ = _allievo_nel(corso, luca)
    nate = AssegnazioneService.proponi(luca, modello.id, [pieno.id], group_id=corso.id)
    copia_piena = AssegnazioneService.accetta(nate[0].id, pieno)
    _seduta(copia_piena, pieno, 5)

    ridotto, _ = _allievo_nel(corso, luca)
    nate = AssegnazioneService.proponi(
        luca, modello.id, [ridotto.id], group_id=corso.id
    )
    copia_ridotta = AssegnazioneService.accetta(nate[0].id, ridotto)
    TrainingSheetService.save_composition(
        copia_ridotta.id,
        ridotto,
        name=copia_ridotta.name,
        items=[
            SheetItemSpec(
                challenge_id=copia_ridotta.active_items[0].challenge_id,
                measure=SheetMeasure.MADE,
                amount=4,
            )
        ],
    )
    _seduta(copia_ridotta, ridotto, 2)

    vista = _vista(luca, corso)
    assert vista.media is not None
    assert (vista.media.valore, vista.media.su) == (5, 10)


def test_chi_non_ha_ancora_fatto_numeri_si_conta_e_non_fa_zero(db_session, luca, corso):
    """Uno zero al posto di un numero che non c'è è la bugia più facile."""
    _corso_con_copie(luca, corso, [[8], []])

    vista = _vista(luca, corso)
    assert vista.media is not None
    assert (vista.media.valore, vista.media.schede, vista.media.fuori) == (8, 1, 1)


def test_senza_copie_lette_non_c_e_nessuna_media(db_session, luca, corso):
    modello = _componi(TrainingSheetService.create_sheet(luca, "Del corso"), luca)
    allievo, _ = _allievo_nel(corso, luca)
    AssegnazioneService.proponi(luca, modello.id, [allievo.id], group_id=corso.id)

    assert _vista(luca, corso).media is None


def test_una_scheda_senza_totale_non_fa_media(db_session, luca, corso):
    """Una scheda di sole spunte non ha un «su 60» da mostrare."""
    modello = TrainingSheetService.create_sheet(luca, "Solo spunte")
    TrainingSheetService.save_composition(
        modello.id,
        luca,
        name=modello.name,
        items=[SheetItemSpec(challenge_id=_challenge().id, measure=SheetMeasure.DONE)],
    )
    allievo, _ = _allievo_nel(corso, luca)
    nate = AssegnazioneService.proponi(
        luca, modello.id, [allievo.id], group_id=corso.id
    )
    copia = AssegnazioneService.accetta(nate[0].id, allievo)
    seduta = TrainingSessionService.start(copia.id, allievo)
    TrainingSessionService.record(
        seduta.id, copia.active_items[0].id, allievo, done=True
    )
    TrainingSessionService.close(seduta.id, allievo)

    assert (
        media_del_gruppo(
            scheda_del_gruppo(corso, _righe_dentro(luca, corso)),
            sedute_per_scheda([copia.id]),
        )
        is None
    )


# ── le sedute della settimana ───────────────────────────────────────────────


def test_la_settimana_e_quella_del_corso(db_session, luca, corso):
    """Comincia nel giorno della settimana in cui è cominciato il corso."""
    da, del_corso = settimana_del_corso(corso)
    assert del_corso is True
    assert da.date() == corso.started_on


def test_senza_data_d_inizio_sono_gli_ultimi_sette_giorni(db_session, luca):
    senza_date = GruppoService.crea(luca, "Senza calendario")
    da, del_corso = settimana_del_corso(senza_date)
    assert del_corso is False
    assert (utc_now() - da).days == 7


def test_si_contano_le_sedute_di_tutte_le_schede_che_leggi(db_session, luca, corso):
    """Chi si allena sulla scheda che aveva già si è allenato lo stesso."""
    allievo, sua = _allievo_nel(corso, luca)
    _seduta(sua, allievo, 6)
    _seduta(sua, allievo, 7)
    _seduta(sua, allievo, 3, quando=utc_now() - timedelta(days=40))

    vista = _vista(luca, corso)
    assert vista.sedute_settimana == 2
    assert vista.settimana_del_corso is True


def test_la_seduta_di_chi_e_fuori_dal_gruppo_non_conta(db_session, luca, corso):
    _dentro, scheda_dentro = _allievo_nel(corso, luca)
    _seduta(scheda_dentro, _dentro, 5)

    fuori = _user()
    scheda_fuori = _scheda_aperta_a(fuori, luca)
    _seduta(scheda_fuori, fuori, 9)

    assert _vista(luca, corso).sedute_settimana == 1


def test_una_seduta_aperta_non_conta(db_session, luca, corso):
    allievo, scheda = _allievo_nel(corso, luca)
    TrainingSessionService.start(scheda.id, allievo)

    assert sedute_della_settimana(corso, sedute_per_scheda([scheda.id])) == 0


# ── «N al livello dopo» ─────────────────────────────────────────────────────


def _con_gradino(allievo, luca, *, kind=LevelUp.AUTO):
    """Una scheda a livelli, aperta a Luca, con soglia 8 su 10."""
    scheda = _scheda_aperta_a(
        allievo, luca, nome="Livello 1", level=1, threshold=8, level_up=kind
    )
    return scheda


def test_conta_le_persone_che_hanno_superato_dentro_il_corso(db_session, luca, corso):
    """Il fatto è il timbro, e con `auto` non c'è nessuna proposta di mezzo."""
    allievo = _user()
    scheda = _con_gradino(allievo, luca)
    GruppoService.aggiungi(corso.id, luca, allievo.id)
    _seduta(scheda, allievo, 9)

    assert scheda.passed_at is not None
    assert esiti_dei_corsi(luca.id, [corso]) == {corso.id: 1}


def test_un_timbro_di_prima_dell_iscrizione_non_conta(db_session, luca, corso):
    """Chi era già di livello 2 quando è arrivato non è passato nel tuo corso.

    Si sposta indietro anche il permesso di lettura, altrimenti il test
    passerebbe per l'altra regola — «non lo leggevi ancora» — e non per questa.
    """
    allievo = _user()
    scheda = _con_gradino(allievo, luca)
    _seduta(scheda, allievo, 9)
    prima = utc_now() - timedelta(days=90)
    scheda.passed_at = prima
    scheda.readers[0].granted_at = prima - timedelta(days=1)
    db.session.flush()
    GruppoService.aggiungi(corso.id, luca, allievo.id)

    assert esiti_dei_corsi(luca.id, [corso]) == {corso.id: 0}


def test_una_scheda_archiviata_dal_passaggio_conta_lo_stesso(db_session, luca, corso):
    """Il passaggio **archivia** la scheda superata: cercarla fra le attive
    vorrebbe dire non trovare mai i passaggi andati a buon fine."""
    allievo = _user()
    scheda = _con_gradino(allievo, luca)
    GruppoService.aggiungi(corso.id, luca, allievo.id)
    _seduta(scheda, allievo, 9)
    TrainingSheetService.archive_sheet(scheda.id, allievo)

    assert esiti_dei_corsi(luca.id, [corso]) == {corso.id: 1}


def test_il_numero_non_cambia_se_l_ex_allievo_ti_richiude_la_scheda(
    db_session, luca, corso
):
    """Lo storico dice quello che hai visto succedere, e resta fermo."""
    allievo = _user()
    scheda = _con_gradino(allievo, luca)
    GruppoService.aggiungi(corso.id, luca, allievo.id)
    _seduta(scheda, allievo, 9)
    GruppoService.chiudi(corso.id, luca)

    TrainingSheetService.remove_reader(scheda.id, luca.id, allievo)

    assert esiti_dei_corsi(luca.id, [corso]) == {corso.id: 1}


def test_un_timbro_arrivato_dopo_la_revoca_non_si_vede(db_session, luca, corso):
    """Chi non leggeva più quella scheda non ha visto niente."""
    allievo = _user()
    scheda = _con_gradino(allievo, luca)
    GruppoService.aggiungi(corso.id, luca, allievo.id)
    TrainingSheetService.remove_reader(scheda.id, luca.id, allievo)
    _seduta(scheda, allievo, 9)

    assert scheda.passed_at is not None
    assert esiti_dei_corsi(luca.id, [corso]) == {corso.id: 0}
