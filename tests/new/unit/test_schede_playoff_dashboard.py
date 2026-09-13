"""Le schede dei playoff in dashboard, dopo la risposta e fuori zona.

Rilievo del 2026-09-13: la dashboard mostrava il playoff solo come invito da
accettare, quindi chi rispondeva lo perdeva di vista e chi era fuori zona non
lo vedeva mai. Il parallelo con le gare, deciso dall'utente:

* chi ha **accettato** → una gara a cui è iscritto, che sta per iniziare;
* chi è **fuori zona** → una gara in cui è in lista d'attesa;
* chi ha **rifiutato** → una gara a cui non è iscritto, con le iscrizioni
  chiuse.

L'invito ancora senza risposta resta la sezione in cima (decisione del
2026-09-10): non genera una scheda. Presidia `models/dashboard/playoff_cards.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import utc_now
from models.campionato.models import Campionato
from models.classification.models import Classification
from models.competition.models import Gara
from models.dashboard.gara_cards import build_gara_cards
from models.dashboard.playoff_cards import (
    MotivoChiuso,
    PostoPlayoff,
    build_playoff_cards,
    unisci_schede_playoff,
)
from models.dashboard.view_models import UnifiedDashboardItem
from models.matchmaking.configuration import MatchmakingStrategy
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(db_session, nome: str) -> User:
    sigla = uuid.uuid4().hex[:6]
    utente = User(
        username=f"{nome}_{sigla}",
        email=f"{nome}_{sigla}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("test1234")
    db_session.add(utente)
    db_session.flush()
    return utente


@pytest.fixture
def playoff(db_session):
    """Un playoff a due posti, inviti partiti, sei giocatori in classifica.

    * p1 ha accettato, p2 ha rifiutato e al suo posto è stato chiamato p3,
      che non ha ancora risposto;
    * p4 e p6 sono fuori zona e chiamabili, in quest'ordine;
    * p5 è in classifica ma non ha il minimo di gare: non è chiamabile.
    """
    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type=MatchmakingStrategy.AMALFI.value,
        is_active=True,
    )
    db_session.add(camp)
    db_session.flush()

    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=2,
        positions_from=1,
        positions_to=2,
        min_garas_played=1,
        is_active=True,
        location="Sala Centrale",
    )
    db_session.add(cfg)
    db_session.flush()

    giocatori = {}
    for pos in range(1, 7):
        utente = _utente(db_session, f"p{pos}")
        giocatori[f"p{pos}"] = utente
        db_session.add(
            Classification(
                campionato_id=camp.id,
                user_id=utente.id,
                position=pos,
                total_matches_won=10 - pos,
                total_point_difference=20 - pos,
                gare_played=0 if pos == 5 else 5,
            )
        )
    giocatori["estraneo"] = _utente(db_session, "estraneo")

    adesso = utc_now()
    inviti = {}
    for chi, pos, stato in (
        ("p1", 1, QualificationStatus.CONFIRMED),
        ("p2", 2, QualificationStatus.DECLINED),
        ("p3", 3, QualificationStatus.PENDING),
    ):
        invito = PlayoffQualification(
            configuration_id=cfg.id,
            user_id=giocatori[chi].id,
            qualifying_position=pos,
            qualification_reason=f"Posizione {pos}",
            status=stato,
            invited_at=adesso,
        )
        db_session.add(invito)
        inviti[chi] = invito
    inviti["p2"].replaced_by_id = giocatori["p3"].id

    camp.terminated_at = adesso
    db_session.commit()
    return {"campionato": camp, "config": cfg, "inviti": inviti, **giocatori}


def _gara_di_playoff(db_session, playoff, status: str) -> Gara:
    gara = Gara(
        campionato_id=playoff["campionato"].id,
        number=1,
        name="Finale",
        date=date.today() + timedelta(days=7),
        discipline=Discipline.NINE_BALL.value,
        status=status,
        rounds_count=1,
        distance=5,
        max_participants=2,
        playoff_config_id=playoff["config"].id,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _scheda(utente: User):
    schede = build_playoff_cards(utente.id)
    assert len(schede) <= 1
    return schede[0] if schede else None


class TestChiVedeCosa:
    def test_chi_ha_accettato_e_iscritto(self, playoff):
        scheda = _scheda(playoff["p1"])
        assert scheda is not None
        assert scheda.posto == PostoPlayoff.ISCRITTO.value
        assert scheda.ha_un_fatto_mio

    def test_chi_ha_rifiutato_trova_le_iscrizioni_chiuse(self, playoff):
        scheda = _scheda(playoff["p2"])
        assert scheda is not None
        assert scheda.posto == PostoPlayoff.CHIUSO.value
        assert scheda.motivo == MotivoChiuso.RIFIUTATO.value
        assert not scheda.ha_un_fatto_mio

    def test_l_invito_in_attesa_resta_nella_sezione_in_cima(self, playoff):
        assert _scheda(playoff["p3"]) is None

    def test_gli_esclusi_sono_in_lista_nell_ordine_della_cascata(self, playoff):
        primo = _scheda(playoff["p4"])
        secondo = _scheda(playoff["p6"])
        assert primo is not None and secondo is not None
        assert primo.posto == secondo.posto == PostoPlayoff.IN_LISTA.value
        assert (primo.posizione_in_lista, secondo.posizione_in_lista) == (1, 2)
        assert primo.ha_un_fatto_mio

    def test_chi_non_ha_i_requisiti_non_e_in_lista(self, playoff):
        """p5 sta davanti a p6 in classifica, ma la cascata lo salta."""
        scheda = _scheda(playoff["p5"])
        assert scheda is not None
        assert scheda.posto == PostoPlayoff.CHIUSO.value
        assert scheda.motivo == MotivoChiuso.REQUISITI.value

    def test_chi_non_ha_giocato_il_campionato_non_vede_niente(self, playoff):
        assert _scheda(playoff["estraneo"]) is None

    @pytest.mark.parametrize(
        "stato, motivo",
        [
            (QualificationStatus.EXPIRED, MotivoChiuso.SCADUTO),
            (QualificationStatus.REPLACED, MotivoChiuso.SOSTITUITO),
        ],
    )
    def test_scaduto_e_sostituito_valgono_come_un_rifiuto(
        self, db_session, playoff, stato, motivo
    ):
        playoff["inviti"]["p2"].status = stato
        db_session.commit()
        scheda = _scheda(playoff["p2"])
        assert scheda is not None
        assert scheda.posto == PostoPlayoff.CHIUSO.value
        assert scheda.motivo == motivo.value

    def test_la_scheda_conta_i_posti_presi_e_gli_inviti_aperti(self, playoff):
        scheda = _scheda(playoff["p1"])
        assert scheda is not None
        assert (scheda.confermati, scheda.posti) == (1, 2)
        assert scheda.inviti_aperti


class TestQuandoCompare:
    def test_prima_degli_inviti_non_c_e_niente(self, db_session, playoff):
        for invito in playoff["inviti"].values():
            invito.invited_at = None
        db_session.commit()
        assert _scheda(playoff["p1"]) is None
        assert _scheda(playoff["p4"]) is None

    def test_un_campionato_eliminato_non_lascia_schede(self, db_session, playoff):
        playoff["campionato"].deleted_at = utc_now()
        db_session.commit()
        assert _scheda(playoff["p1"]) is None
        assert _scheda(playoff["p4"]) is None

    def test_una_configurazione_disattivata_non_lascia_schede(
        self, db_session, playoff
    ):
        playoff["config"].is_active = False
        db_session.commit()
        assert _scheda(playoff["p2"]) is None

    def test_con_la_gara_creata_la_scheda_la_porta(self, db_session, playoff):
        gara = _gara_di_playoff(db_session, playoff, GaraStatus.INSCRIPTION.value)
        scheda = _scheda(playoff["p1"])
        assert scheda is not None
        assert scheda.gara is not None and scheda.gara.id == gara.id

    def test_a_playoff_cominciato_resta_la_tessera_della_gara(
        self, db_session, playoff
    ):
        _gara_di_playoff(db_session, playoff, GaraStatus.PLAYING.value)
        assert _scheda(playoff["p1"]) is None
        assert _scheda(playoff["p2"]) is None


def _item(gara: Gara, *, can_manage: bool = False) -> UnifiedDashboardItem:
    return UnifiedDashboardItem(
        type="gara",
        id=gara.id,
        name=gara.name or "",
        entity=gara,
        next_prova_date=gara.date,
        can_manage=can_manage,
    )


class TestUnaSchedaPerGara:
    def test_la_tessera_della_gara_lascia_il_posto_alla_scheda(
        self, db_session, playoff
    ):
        gara = _gara_di_playoff(db_session, playoff, GaraStatus.INSCRIPTION.value)
        gare = build_gara_cards([_item(gara)], [], [])
        assert [c.id for c in gare.aperte] == [gara.id]

        unisci_schede_playoff(gare, build_playoff_cards(playoff["p2"].id))

        assert gare.aperte == []
        assert [s.posto for s in gare.in_arrivo] == [PostoPlayoff.CHIUSO.value]

    def test_chi_ha_accettato_la_trova_fra_le_sue(self, playoff):
        gare = build_gara_cards([], [], [])
        unisci_schede_playoff(gare, build_playoff_cards(playoff["p1"].id))
        assert [s.posto for s in gare.mie] == [PostoPlayoff.ISCRITTO.value]
        assert gare.in_arrivo == []

    def test_chi_dirige_la_gara_tiene_la_sua_tessera(self, db_session, playoff):
        gara = _gara_di_playoff(db_session, playoff, GaraStatus.INSCRIPTION.value)
        gare = build_gara_cards([_item(gara, can_manage=True)], [], [])
        assert [c.id for c in gare.mie] == [gara.id]

        unisci_schede_playoff(gare, build_playoff_cards(playoff["p1"].id))

        assert len(gare.mie) == 1
        assert gare.mie[0].can_manage
