"""Il blocco della dashboard segue l'**ultima attività**, non il ruolo.

Fino al 2026-08-25 `_classify` chiudeva la partita con una riga sola —
``if is_director and director_garas: return "director"`` — e quella riga
trattava un ruolo come se fosse una casistica di attività. I ruoli però non
scadono: un direttore che gioca (e giocano tutti) non vedeva **mai** il proprio
Elo, nemmeno la sera in cui aveva appena chiuso una partita.

Qui si difendono tre cose:

* il blocco cambia forma con l'ultimo fatto, in tutte e due le direzioni;
* le gare da chiudere restano visibili anche quando il tono passa al giocatore:
  sono l'unica cosa del blocco da direttore che ha una scadenza;
* la striscia «Le tue ultime gare» dice cosa vogliono dire i suoi colori, e
  distingue una gara aperta da una rimasta a metà — che sono l'opposto l'una
  dell'altra e avevano lo stesso grigio.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from models import db
from models.base import utc_now
from models.competition.models import Gara, Inscription
from models.dashboard.activity_feedback import (
    STRIP_TEXT_LIMIT,
    ActivityFeedbackService,
    _classify,
    _director_last_event,
)
from models.individual_match.match_models import IndividualMatch
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user(role: str = UserRole.PLAYER.value) -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"u_{tag}", email=f"{tag}@example.test", role=role)
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _gara(
    director: User,
    *,
    numero: int,
    giorni_fa: int,
    status: str = GaraStatus.COMPLETED.value,
    max_participants: int | None = 12,
    iscritti: int = 0,
) -> Gara:
    quando = utc_now() - timedelta(days=giorni_fa)
    gara = Gara(
        campionato_id=None,
        director_id=director.id,
        number=numero,
        name=f"Open {numero}",
        date=date(2026, 1, 1) + timedelta(days=numero),
        discipline="palla_9",
        distance=5,
        status=status,
        max_participants=max_participants,
        created_at=quando,
    )
    db.session.add(gara)
    db.session.commit()

    for _ in range(iscritti):
        db.session.add(Inscription(user_id=_user().id, gara_id=gara.id))
    db.session.commit()
    return gara


def _partita(giocatore: User, avversario: User, *, giorni_fa: int) -> IndividualMatch:
    quando = utc_now() - timedelta(days=giorni_fa)
    match = IndividualMatch(
        player1_id=giocatore.id,
        player2_id=avversario.id,
        scheduled_at=quando,
        ended_at=quando,
        status=MatchStatus.CONFIRMED_BY_BOTH,
        discipline="palla_9",
        distance=5,
        player1_score=5,
        player2_score=2,
        winner_id=giocatore.id,
    )
    db.session.add(match)
    db.session.commit()
    return match


class TestIlBloccoSegueLUltimaAttivita:
    def test_partita_dopo_la_gara_il_direttore_torna_giocatore(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(direttore, numero=1, giorni_fa=10)
        _partita(direttore, _user(), giorni_fa=1)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["profile"] != "director"
        assert block["title"] != "Come vanno le tue gare"

    def test_gara_dopo_la_partita_resta_il_blocco_delle_gare(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        _partita(direttore, _user(), giorni_fa=10)
        _gara(direttore, numero=1, giorni_fa=1)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["profile"] == "director"

    def test_un_iscritto_alla_sua_gara_e_un_fatto_da_direttore(self, app):
        """Non l'ha fatto lui, ma è successo alla sua gara: conta come tale."""
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore, numero=1, giorni_fa=20)
        _partita(direttore, _user(), giorni_fa=10)

        iscrizione = Inscription(user_id=_user().id, gara_id=gara.id)
        iscrizione.created_at = utc_now() - timedelta(days=1)
        db.session.add(iscrizione)
        db.session.commit()

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["profile"] == "director"

    def test_la_propria_iscrizione_alla_propria_gara_non_conta(self, app):
        """Iscriversi è un atto da giocatore, anche alla gara che organizzi."""
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore, numero=1, giorni_fa=20)

        propria = Inscription(user_id=direttore.id, gara_id=gara.id)
        propria.created_at = utc_now() - timedelta(days=1)
        db.session.add(propria)
        db.session.commit()

        ultimo = _director_last_event(direttore.id)
        assert ultimo is not None
        # Resta la creazione della gara (20 giorni fa), non l'iscrizione di ieri.
        assert (utc_now() - ultimo).days >= 19

    def test_senza_attivita_da_giocatore_resta_il_blocco_delle_gare(self, app):
        """Il caso storico non cambia: chi organizza e basta vede le gare."""
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(direttore, numero=1, giorni_fa=3)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["profile"] == "director"

    def test_senza_data_della_gara_si_resta_al_comportamento_storico(self, app):
        """`created_at` a NULL è «non so», e «non so» non cambia il blocco."""
        direttore = _user(UserRole.DIRECTOR.value)
        assert (
            _classify(
                user_id=direttore.id,
                activities=[],
                elo_delta=None,
                has_tpa=False,
                is_director=True,
                director_garas=2,
                director_last_at=None,
            )
            == "director"
        )


class TestLeGareDaChiudereNonSiPerdono:
    def test_il_badge_sopravvive_al_passaggio_al_blocco_giocatore(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(direttore, numero=1, giorni_fa=10, status=GaraStatus.PLAYING.value)
        _partita(direttore, _user(), giorni_fa=1)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["profile"] != "director"
        assert block["context_badge"] is not None
        assert block["context_badge"]["tone"] == "urgent"
        assert "1" in block["context_badge"]["text"]

    def test_senza_niente_da_chiudere_il_badge_non_si_inventa(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(direttore, numero=1, giorni_fa=10, status=GaraStatus.COMPLETED.value)
        _partita(direttore, _user(), giorni_fa=1)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["context_badge"] is None


class TestLaStrisciaDelleGareSiLegge:
    def test_ogni_colore_ha_la_sua_riga_di_legenda(self, app):
        """Il difetto segnalato: dieci rettangoli colorati e nessuna spiegazione."""
        direttore = _user(UserRole.DIRECTOR.value)
        for n in range(1, 9):
            _gara(direttore, numero=n, giorni_fa=30 - n, iscritti=n)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        strip = block["strip"]

        # Sei tessere col numero leggibile battono dieci rettangoli muti.
        assert len(strip["items"]) == STRIP_TEXT_LIMIT
        assert strip["dense"] is False
        assert all(item["text"] for item in strip["items"])

        # E ogni tono presente nelle tessere compare in legenda, con il colore.
        toni_tessere = {item["outcome"] for item in strip["items"]}
        assert {k["outcome"] for k in strip["legend"]} == toni_tessere
        assert all(k["color_role"] for k in strip["legend"])

    def test_una_gara_aperta_non_e_una_gara_rimasta_a_meta(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        aperta = _gara(
            direttore,
            numero=1,
            giorni_fa=5,
            status=GaraStatus.INSCRIPTION.value,
            iscritti=3,
        )
        _gara(
            direttore, numero=2, giorni_fa=4, iscritti=3
        )  # chiusa, stesso riempimento

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        toni = [item["outcome"] for item in block["strip"]["items"]]
        assert toni == ["open", "draw"]
        assert any(
            str(aperta.display_name) in item["title"]
            for item in block["strip"]["items"]
        )

    def test_una_gara_aperta_non_cade_fuori_dalla_finestra(self, app):
        """È l'unica su cui il direttore può ancora fare qualcosa: entra sempre."""
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(
            direttore,
            numero=1,  # la più vecchia per data: senza il presidio uscirebbe
            giorni_fa=40,
            status=GaraStatus.INSCRIPTION.value,
            iscritti=2,
        )
        for n in range(2, 12):
            _gara(direttore, numero=n, giorni_fa=30 - n, iscritti=n)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert "open" in [item["outcome"] for item in block["strip"]["items"]]

    def test_una_gara_cancellata_non_conta_piu(self, app):
        """`Gara` è soft-deleted e non ha filtro globale: va escluso a mano."""
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(direttore, numero=1, giorni_fa=5, iscritti=4)
        buttata = _gara(direttore, numero=2, giorni_fa=4, iscritti=4)
        buttata.soft_delete()
        db.session.commit()

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["primary"]["value"] == "1"
        assert len(block["strip"]["items"]) == 1


class TestIlRiempimentoDiceIlVero:
    def test_una_gara_senza_massimo_non_e_quasi_piena(self, app):
        """Senza un tetto la domanda «quanto è piena» non ha risposta.

        Accorpandola al tono intermedio la legenda scriveva «quasi piena» su
        una gara che non ha nessun limite a cui avvicinarsi.
        """
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(direttore, numero=1, giorni_fa=5, max_participants=None, iscritti=9)

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert [i["outcome"] for i in block["strip"]["items"]] == ["uncapped"]
        assert [i["text"] for i in block["strip"]["items"]] == ["9"]
        etichette = [k["label"] for k in block["strip"]["legend"]]
        assert not any("piena" in e for e in etichette)

    def test_i_posti_occupati_non_superano_i_posti(self, app):
        """Ritirati e lista d'attesa non occupano un posto.

        Contandoli, una gara con la lista piena arrivava a «112% posti
        occupati» e zero liberi: una percentuale che non può esistere.
        """
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore, numero=1, giorni_fa=5, max_participants=4, iscritti=4)

        db.session.add(
            Inscription(user_id=_user().id, gara_id=gara.id, is_waitlist=True)
        )
        db.session.add(
            Inscription(user_id=_user().id, gara_id=gara.id, is_withdrawn=True)
        )
        db.session.commit()

        block = ActivityFeedbackService.for_player(direttore.id, user=direttore)
        assert block is not None
        assert block["secondary"]["center"] == "100%"
        assert [i["text"] for i in block["strip"]["items"]] == ["4/4"]
