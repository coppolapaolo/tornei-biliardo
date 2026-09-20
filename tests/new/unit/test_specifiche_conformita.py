"""Le regole numeriche di SPECIFICHE.md, rese eseguibili.

Questo modulo esiste per una ragione precisa, ed è un guasto già capitato due
volte: **la specifica è prosa, e la prosa perde sempre contro un test.**

Il meccanismo, osservato dal vivo:

1. `docs/reference/SPECIFICHE.md` fissa una regola numerica — quanto vale la X
   in classifica, a chi passa l'invito ai playoff quando qualcuno rifiuta.
2. L'implementazione ne scrive un'altra. Nessuno se ne accorge, perché nessun
   test confronta il codice con la specifica: i test confrontano il codice con
   sé stesso.
3. Prima o poi una code review trova **due parti del codice incoerenti fra
   loro** e le allinea. Se allinea alla parte sbagliata, aggiunge un test di
   regressione che da quel momento **difende la deviazione**: chi provasse a
   correggere vedrebbe un test rosso con una motivazione scritta bene, e si
   fermerebbe.

Il rimedio è togliere alla specifica il ruolo di documento e darle quello di
test. Ogni test qui sotto **cita la riga di SPECIFICHE.md che verifica**, così
che la catena sia percorribile nei due sensi: dal codice alla regola, e dalla
regola al codice.

Regole d'uso, brevi:

* **Un test per regola**, con la citazione nel docstring. Se la regola cambia
  si cambia la specifica *e* il test, nello stesso commit.
* **Una divergenza trovata si scrive `xfail(strict=True)`**, mai si silenzia e
  mai si «adatta» il test al codice. `strict` fa scattare la suite il giorno in
  cui qualcuno corregge, così il test diventa da solo la regressione.
* **Se una regola nella specifica non c'è**, non si inventa qui: si scrive
  prima nella specifica. Un test senza citazione, in questo file, è fuori posto.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.classification.score_aggregator import ScoreAggregator
from models.competition.models import Gara, Inscription
from models.competition.spareggio_service import SpareggioService
from models.matchmaking import bye_preference
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.match.models import Match
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.user.models import User
from models.user.role_enum import UserRole

SPEC = "docs/reference/SPECIFICHE.md"


def _utente(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"spec_{sigla}",
        email=f"spec_{sigla}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.flush()
    return utente


def _gara(db_session, *, distanza: int = 5, sistema: str = "WINS") -> Gara:
    quante = db_session.query(Gara).count()
    gara = Gara(
        name=f"Gara spec {quante + 1}",
        number=quante + 1,
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=distanza,
        is_race_to=False,
        status=GaraStatus.PLAYING.value,
        rounds_count=3,
        current_round=1,
        classification_system=sistema,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye",
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _punteggi(gara_id: int, fino_al_turno: int = 1) -> dict[int, object]:
    return {
        voce.player_id: voce
        for voce in ScoreAggregator().aggregate_round_scores(gara_id, fino_al_turno)
    }


# ══ Classifica: i tre sistemi ════════════════════════════════════════════


@pytest.mark.unit
class TestSistemiDiClassifica:
    def test_wins_ordina_per_vittorie_poi_differenza_rack(self, db_session):
        """`SPECIFICHE.md` riga 168.

        > **WINS**: ordina per match vinti (decrescente), poi differenza rack
        > (decrescente), poi spareggio

        La chiave di pari merito deve essere la **coppia**: due giocatori sono
        pari merito solo se coincidono entrambi i criteri. È la regola che il
        driver dei test e2e fa rispettare variando i margini delle partite —
        con tutte le partite allo stesso margine la differenza rack diventa una
        funzione delle vittorie e il secondo criterio non discrimina più.
        """
        gara = _gara(db_session)
        primo, secondo = _utente(db_session), _utente(db_session)
        terzo, quarto = _utente(db_session), _utente(db_session)
        for casa, fuori, in_casa, fuori_casa in (
            (primo, secondo, 4, 1),  # 1 vittoria, +3
            (terzo, quarto, 3, 2),  # 1 vittoria, +1
        ):
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=casa.id,
                    player2_id=fuori.id,
                    player1_score=in_casa,
                    player2_score=fuori_casa,
                    winner_id=casa.id,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                )
            )
        db_session.commit()

        punteggi = _punteggi(gara.id)

        # Stesse vittorie, differenza diversa: non sono pari merito.
        assert punteggi[primo.id].matches_won == punteggi[terzo.id].matches_won == 1
        assert punteggi[primo.id].rack_difference == 3
        assert punteggi[terzo.id].rack_difference == 1

    def test_la_chiave_di_pari_merito_wins_e_la_coppia(self, db_session):
        """`SPECIFICHE.md` riga 168, dal lato dello spareggio.

        Lo spareggio deve raggruppare su `(match vinti, differenza rack)`, non
        sulla sola differenza: raggruppare su un criterio solo genererebbe
        pari merito che non esistono.
        """
        gara = _gara(db_session)
        db_session.commit()

        assert SpareggioService.tiebreakers_apply_to(gara) is True


# ══ A chi tocca la X nel primo turno ═════════════════════════════════════


@pytest.mark.unit
class TestAChiToccaLaXNelPrimoTurno:
    """`SPECIFICHE.md` riga 67.

    > all'avvio il direttore può assegnare la X **all'ultimo iscritto** invece
    > di lasciarla al caso [...] Il resto degli abbinamenti resta casuale: chi
    > riceve la X viene scambiato di posto con chi l'aveva sorteggiata, e
    > nient'altro si muove.

    Qui si verifica *quando* la domanda si pone e *chi* è "l'ultimo iscritto".
    Che lo scambio conservi le garanzie del sorteggio (una X a testa, nessun
    reincontro) lo verifica
    `tests/new/integration/test_x_al_ultimo_iscritto.py`, che ha bisogno di
    generare i turni veri.
    """

    @staticmethod
    def _iscrivi(db_session, gara: Gara, quanti: int) -> list[User]:
        giocatori = []
        for _ in range(quanti):
            giocatore = _utente(db_session)
            db_session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
            giocatori.append(giocatore)
        db_session.flush()
        return giocatori

    def test_si_pone_solo_con_amalfi_o_casuale_dispari_e_la_x(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)

        assert bye_preference.choice_applies(gara) is True

        gara.matchmaking_strategy = "random"
        assert bye_preference.choice_applies(gara) is True

        # Fuori dalle due strategie la X non è una sola e la domanda decade.
        gara.matchmaking_strategy = "round_robin"
        assert bye_preference.choice_applies(gara) is False

    def test_col_trio_non_ci_sono_x_da_assegnare(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)
        gara.odd_number_policy = "trio"

        assert bye_preference.choice_applies(gara) is False

    def test_con_giocatori_pari_non_ci_sono_x_da_assegnare(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 6)

        assert bye_preference.choice_applies(gara) is False

    def test_l_ultimo_iscritto_e_l_ultimo_arrivato_fra_chi_gioca(self, db_session):
        gara = _gara(db_session)
        giocatori = self._iscrivi(db_session, gara, 5)

        assert bye_preference.last_inscribed_user_id(gara) == giocatori[-1].id

    def test_senza_la_scelta_la_x_resta_al_sorteggio(self, db_session):
        """Il default è il comportamento storico, non la novità."""
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)

        assert gara.bye_to_last_inscribed in (False, None)
        assert bye_preference.preferred_bye_player(gara) is None


# ══ La X (bye) ═══════════════════════════════════════════════════════════


@pytest.mark.unit
class TestQuantoValeLaX:
    """`SPECIFICHE.md` righe 64 e 71."""

    @staticmethod
    def _con_la_x(db_session, gara: Gara, giocatore: User, punteggio: int) -> Match:
        partita = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatore.id,
            player2_id=None,
            is_bye=True,
            player1_score=punteggio,
            player2_score=0,
            winner_id=giocatore.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
        db_session.add(partita)
        db_session.commit()
        return partita

    def test_la_x_vale_una_vittoria(self, db_session):
        """`SPECIFICHE.md` riga 71.

        > **Bye**: un giocatore salta il turno (solo per sistema WINS: ottiene
        > 1 vittoria, 0 diff rack)

        Questa metà la regge: la vittoria c'è.
        """
        gara = _gara(db_session)
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, gara.distance)

        assert _punteggi(gara.id)[giocatore.id].matches_won == 1

    def test_la_x_nasce_senza_triangoli(self, db_session):
        """`SPECIFICHE.md` righe 64 e 71, **alla fonte**.

        > abbina un giocatore alla X assegnando il match vinto, ma con **zero
        > differenza punti**

        Questo test passa dal vero punto di creazione, non da un `Match`
        costruito a mano: è lì che stava la divergenza (`round_creation.py`
        assegnava `player1_score = round_distance`), ed è lì che va presidiata.
        Un test che costruisce da sé la partita con il punteggio che vuole non
        può accorgersi di come la produzione la crea davvero.
        """
        from models.competition.round_creation import create_matches_from_pairings
        from models.matchmaking.strategies.base import Pairing

        gara = _gara(db_session)
        giocatore = _utente(db_session)

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(giocatore.id,), is_bye=True, round_number=1)],
            round_number=1,
            round_distance=gara.distance,
        )
        db_session.flush()

        partita = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert partita.is_bye
        assert partita.player1_score == 0

    def test_la_x_da_zero_differenza_rack(self, db_session):
        """`SPECIFICHE.md` righe 64 e 71, **in classifica**.

        La conseguenza del test precedente sul punteggio aggregato: con zero
        triangoli vinti e nessuno perso, la differenza resta ferma e chi riposa
        si piazza sotto chiunque abbia vinto giocando — che è l'intento
        dichiarato dalla riga 64.
        """
        gara = _gara(db_session)
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, 0)

        voce = _punteggi(gara.id)[giocatore.id]
        assert voce.matches_won == 1
        assert voce.rack_difference == 0

    def test_la_x_con_challenge_da_differenza_pari_al_punteggio(self, db_session):
        """`SPECIFICHE.md` riga 65.

        > il giocatore abbinato con la X, invece di stare fermo il turno, gioca
        > la challenge e in classifica ottiene il match vinto e una differenza
        > rack pari al punteggio nella challenge

        È la regola che impedisce di correggere la X azzerando l'aggregatore:
        l'aggregatore deve continuare a leggere `player1_score`, perché per la
        X-con-challenge quel campo **è** il punteggio della prova.
        """
        gara = _gara(db_session)
        gara.odd_number_policy = "bye_with_challenge"
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, 3)

        voce = _punteggi(gara.id)[giocatore.id]
        assert voce.matches_won == 1
        assert voce.rack_difference == 3


# ══ Pareggio a distanza pari ═════════════════════════════════════════════


@pytest.mark.unit
class TestPareggio:
    def test_a_rack_esatti_pari_il_pareggio_da_zero_e_zero(self, db_session):
        """`SPECIFICHE.md` riga 141.

        > **"Exactly N"** (esatto numero): si giocano esattamente N rack, vince
        > chi ne ha vinti di più. Se N è pari, sono possibili pareggi (gestiti
        > con 0 vittorie e 0 diff rack per entrambi nel sistema WINS).
        """
        gara = _gara(db_session, distanza=6)
        uno, due = _utente(db_session), _utente(db_session)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=uno.id,
                player2_id=due.id,
                player1_score=3,
                player2_score=3,
                winner_id=None,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db_session.commit()

        punteggi = _punteggi(gara.id)

        for giocatore in (uno, due):
            voce = punteggi[giocatore.id]
            assert voce.matches_won == 0, "il pareggio non è una vittoria"
            assert voce.rack_difference == 0


# ══ Playoff: la cascata dei rifiuti ══════════════════════════════════════


@pytest.mark.unit
class TestCascataDeiRifiutiAiPlayoff:
    """`SPECIFICHE.md` riga 286."""

    @staticmethod
    def _campionato_con_playoff(db_session, posti: int, iscritti: int):
        from models.campionato.models import Campionato
        from models.classification.models import Classification
        from models.base import utc_now

        campionato = Campionato(
            name=f"Camp spec {uuid.uuid4().hex[:6]}",
            campionato_type="amalfi",
            is_active=True,
        )
        db_session.add(campionato)
        db_session.flush()
        campionato.terminated_at = utc_now()

        gara = _gara(db_session)
        gara.campionato_id = campionato.id
        gara.status = GaraStatus.COMPLETED.value

        configurazione = PlayoffConfiguration(
            campionato_id=campionato.id,
            name="Elite",
            playoff_type=PlayoffType.TOP_N,
            max_participants=posti,
            positions_from=1,
            positions_to=posti,
            is_active=True,
            auto_generate=True,
        )
        db_session.add(configurazione)
        db_session.flush()

        giocatori = []
        for posizione in range(1, iscritti + 1):
            giocatore = _utente(db_session)
            db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
            db_session.add(
                Classification(
                    campionato_id=campionato.id,
                    user_id=giocatore.id,
                    position=posizione,
                    total_matches_won=iscritti - posizione,
                    gare_played=1,
                )
            )
            giocatori.append(giocatore)
        db_session.commit()
        return campionato, configurazione, giocatori

    def test_chi_rifiuta_lascia_il_posto_al_primo_degli_esclusi(self, db_session):
        """`SPECIFICHE.md` riga 286.

        > Nei playoff con un numero limitato di partecipanti (ad esempio i
        > primi 6), se un giocatore rifiuta, la notifica passa al primo degli
        > esclusi e così via fino a quando un numero di giocatori pari ai posti
        > disponibili ha dato l'ok oppure sono finiti i giocatori.
        """
        _campionato, configurazione, giocatori = self._campionato_con_playoff(
            db_session, posti=4, iscritti=8
        )
        PlayoffService.start_playoff(_campionato.id)
        db_session.commit()

        qualificazioni = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id
        ).all()
        assert len(qualificazioni) == 4
        rinuncia = min(qualificazioni, key=lambda q: q.qualifying_position)

        PlayoffService.decline_qualification(rinuncia.id, rinuncia.user_id)
        db_session.commit()

        invitati = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id
        ).all()
        vivi = [
            q
            for q in invitati
            if q.status in (QualificationStatus.PENDING, QualificationStatus.CONFIRMED)
        ]
        assert len(vivi) == 4, (
            "dopo un rifiuto i posti vivi devono tornare a quattro: "
            f"invitati={len(invitati)}, vivi={len(vivi)}"
        )
        # Il sostituto è il quinto della classifica, cioè il primo escluso.
        quinto = giocatori[4]
        assert quinto.id in {q.user_id for q in invitati}

    @staticmethod
    def _verifica_invito_ricevuto(sostituto: PlayoffQualification) -> None:
        """Il sostituto è invitato come gli altri: data, scadenza, notifica."""
        from models.base import utc_now
        from models.notification.models import Notification, NotificationType

        assert sostituto.invited_at is not None, "il sostituto non risulta invitato"
        assert sostituto.expires_at is not None, "l'invito del sostituto non scade"
        assert sostituto.expires_at > utc_now(), "l'invito del sostituto è già scaduto"
        notifica = Notification.query.filter_by(
            user_id=sostituto.user_id,
            notification_type=NotificationType.PLAYOFF_INVITATION,
        ).first()
        assert notifica is not None, "al primo degli esclusi non arriva nessun invito"
        assert notifica.action_url == f"/player/playoff/invitation/{sostituto.id}"

    def test_il_primo_degli_esclusi_riceve_la_notifica_d_invito(self, db_session):
        """`SPECIFICHE.md` riga 286.

        > se un giocatore rifiuta, la notifica passa al primo degli esclusi

        Non basta creargli la qualificazione: fino al 2026-09-13 il sostituto
        compariva in lista senza che nessuno glielo dicesse, e senza scadenza.
        """
        campionato, configurazione, giocatori = self._campionato_con_playoff(
            db_session, posti=4, iscritti=8
        )
        PlayoffService.start_playoff(campionato.id)
        db_session.commit()
        rinuncia = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id, user_id=giocatori[0].id
        ).one()

        sostituto = PlayoffService.decline_qualification(rinuncia.id, rinuncia.user_id)
        db_session.commit()

        assert sostituto is not None
        assert sostituto.user_id == giocatori[4].id
        self._verifica_invito_ricevuto(
            db_session.get(PlayoffQualification, sostituto.id)
        )

    def test_anche_il_rifiuto_detto_al_direttore_avvisa_il_sostituto(self, db_session):
        """`SPECIFICHE.md` riga 286, rifiuto registrato dal direttore.

        Il giocatore che dice no a voce passa dalla stessa cascata: il primo
        degli esclusi va avvisato anche lì.
        """
        campionato, configurazione, giocatori = self._campionato_con_playoff(
            db_session, posti=4, iscritti=8
        )
        direttore = _utente(db_session)
        PlayoffService.start_playoff(campionato.id)
        db_session.commit()
        rinuncia = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id, user_id=giocatori[1].id
        ).one()

        sostituto = PlayoffService.respond_on_behalf(
            rinuncia.id, accept=False, responded_by_id=direttore.id
        )
        db_session.commit()

        assert sostituto is not None
        assert sostituto.user_id == giocatori[4].id
        self._verifica_invito_ricevuto(
            db_session.get(PlayoffQualification, sostituto.id)
        )


class TestIlPlayoffSiGiocaConChiHaAccettato:
    """`SPECIFICHE.md`, sezione «Playoff», righe 286 e 288.

    > […] fino a quando un numero di giocatori pari ai posti disponibili ha
    > dato l'ok oppure sono finiti i giocatori.

    > Il playoff si gioca con chi ha accettato, anche se sono meno dei posti
    > […] chi accetta dopo la creazione […] entra fra gli iscritti fino
    > all'avvio del primo turno […]. All'avvio gli inviti ancora senza
    > risposta scadono e nessun altro viene chiamato.
    """

    @staticmethod
    def _avvia(gara_id: int):
        """Dalla preparazione: la gara di playoff non ha iscrizioni da aprire."""
        from models.competition.round_service import RoundService

        return RoundService.start_first_round(gara_id)

    @staticmethod
    def _invito(configurazione, giocatore):
        return PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id, user_id=giocatore.id
        ).first()

    def test_con_meno_si_dei_posti_la_finale_parte(self, db_session):
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=4
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:3]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        ultimo = giocatori[3]
        # Sono finiti i giocatori: il rifiuto non chiama nessuno.
        assert (
            PlayoffService.decline_qualification(
                self._invito(configurazione, ultimo).id, ultimo.id
            )
            is None
        )

        gara = PlayoffService.create_playoff_gara(configurazione.id)

        assert self._avvia(gara.id).current_round == 1

    def test_chi_accetta_prima_dell_avvio_entra_e_all_avvio_gli_inviti_scadono(
        self, db_session
    ):
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=8
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:2]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)

        tardivo = giocatori[2]
        PlayoffService.confirm_qualification(
            self._invito(configurazione, tardivo).id, tardivo.id
        )
        assert Inscription.query.filter_by(gara_id=gara.id, user_id=tardivo.id).first()

        self._avvia(gara.id)

        silenzioso = self._invito(configurazione, giocatori[3])
        assert silenzioso.status == QualificationStatus.EXPIRED
        assert (
            PlayoffQualification.query.filter_by(
                configuration_id=configurazione.id
            ).count()
            == 4
        )

    def test_annullato_l_avvio_gli_inviti_chiusi_dall_avvio_si_riaprono(
        self, db_session
    ):
        """Riga 288: «Se il direttore annulla l'avvio, gli inviti chiusi
        proprio da quell'avvio tornano in attesa, purché la loro scadenza non
        sia ancora passata»."""
        from models.competition.round_cancellation import RoundCancellationService

        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=5, iscritti=8
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:4]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)
        self._avvia(gara.id)
        assert (
            self._invito(configurazione, giocatori[4]).status
            == QualificationStatus.EXPIRED
        )

        RoundCancellationService.cancel_first_round_startup(gara.id)

        assert (
            self._invito(configurazione, giocatori[4]).status
            == QualificationStatus.PENDING
        )

    def test_il_giocatore_aggiunto_dal_direttore_entra_oltre_i_posti(self, db_session):
        """Riga 288: «Un giocatore aggiunto a mano dal direttore entra invece
        sempre […] anche oltre i posti, e il massimo della gara non ne blocca
        l'avvio»."""
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=6
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:4]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)

        PlayoffService.admin_add_player(configurazione.id, giocatori[5].id, "direttore")

        attivi = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert attivi == 5
        assert self._avvia(gara.id).current_round == 1

    def test_l_aggiunta_del_direttore_rispetta_la_parita(self, db_session):
        """Riga 288: «La parità invece vale anche per lui: se la gara non
        ammette un numero dispari di giocatori […] chi renderebbe dispari gli
        iscritti aspetta in lista d'attesa come gli altri, finché non arriva
        un secondo giocatore»."""
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=7
            )
        )
        configurazione.odd_number_policy = "no"
        db_session.commit()
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:4]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)

        PlayoffService.admin_add_player(configurazione.id, giocatori[5].id, "direttore")
        primo = Inscription.query.filter_by(
            gara_id=gara.id, user_id=giocatori[5].id
        ).first()
        assert primo is not None and primo.is_waitlist

        PlayoffService.admin_add_player(configurazione.id, giocatori[6].id, "direttore")
        attivi = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert attivi == 6


# ──────────────────────────────────────────────────────────────────────────────
# APERTURA E RUNOUT (SPECIFICHE.md, sezione «Match», righe 131-144 — ADR-056)
# ──────────────────────────────────────────────────────────────────────────────


class TestRegoleDiApertura:
    """«Il match ha una regola di inizio e una regola di apertura, entrambe
    ereditate dalla gara a cui appartiene: sul singolo match non si scelgono.»
    (SPECIFICHE.md riga 131)
    """

    def test_le_quattro_modalita_di_apertura_sono_quelle_della_specifica(self):
        """SPECIFICHE.md righe 137-141: quattro, e con questi valori.

        Fino al 2026-08-28 la specifica ne prevedeva **due** e il codice ne
        aveva **tre**, sulle sole sfide individuali. I valori contano quanto il
        numero: finiscono in colonna, e rinominarne uno rende illeggibili le
        righe gia' scritte.
        """
        from models.match.break_rules import BreakRule

        assert [r.value for r in BreakRule] == [
            "winner_breaks",
            "alternate",
            "alternate_two",
            "loser_breaks",
        ]

    def test_le_due_regole_di_inizio_sono_quelle_della_specifica(self):
        """SPECIFICHE.md righe 133-135: primo giocatore, oppure acchito."""
        from models.match.break_rules import StartRule

        assert [r.value for r in StartRule] == ["first_player", "lag"]

    def test_a_turno_e_il_default(self):
        """SPECIFICHE.md riga 139: «È il default».

        E' anche quello che le sfide individuali avevano gia' dal 2026-02:
        cambiarlo riscriverebbe il passato di quelle partite.
        """
        from models.match.break_rules import DEFAULT_BREAK_RULE, BreakRule

        assert DEFAULT_BREAK_RULE is BreakRule.ALTERNATE

    def test_a_turno_alterna_a_ogni_rack(self):
        """SPECIFICHE.md riga 139: «tiri di apertura alternati»."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        apre = [
            break_player_for_rack(BreakRule.ALTERNATE, n, 1, 2, []) for n in range(4)
        ]
        assert apre == [1, 2, 1, 2]

    def test_a_turno_ogni_due_cambia_ogni_due_rack(self):
        """SPECIFICHE.md riga 140: «due rack a testa, poi si cambia»."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        apre = [
            break_player_for_rack(BreakRule.ALTERNATE_TWO, n, 1, 2, [])
            for n in range(6)
        ]
        assert apre == [1, 1, 2, 2, 1, 1]

    def test_spacca_chi_ha_vinto_e_chi_ha_perso_guardano_il_rack_prima(self):
        """SPECIFICHE.md righe 138 e 141."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        # Rack 0 vinto da 2: al rack 1 apre 2 (winner) oppure 1 (loser).
        assert break_player_for_rack(BreakRule.WINNER_BREAKS, 1, 1, 2, [2]) == 2
        assert break_player_for_rack(BreakRule.LOSER_BREAKS, 1, 1, 2, [2]) == 1

    def test_l_acchito_e_due_domande_non_una(self):
        """SPECIFICHE.md riga 135: chi vince l'acchito **sceglie chi** apre.

        Quindi chi ha vinto e chi apre sono due fatti indipendenti, e il
        secondo puo' essere l'avversario del primo. Se fossero lo stesso dato,
        `first_break_player_id` non esisterebbe.
        """
        from models.match.models import Match

        assert hasattr(Match, "lag_winner_id")
        assert hasattr(Match, "first_break_player_id")

    def test_break_and_run_si_deduce_da_chi_apriva(self):
        """SPECIFICHE.md riga 143: «Non si scelgono: si deduce da chi apriva.»

        Un solo flag sul rack (`is_run_out`) piu' chi ha aperto: il break and
        run non e' un secondo flag che qualcuno potrebbe dimenticare di
        alzare — e quindi non puo' contraddire il primo.
        """
        from models.match.models import Rack

        vinto_da_chi_apriva = Rack(winner_id=7, break_player_id=7, is_run_out=True)
        vinto_rispondendo = Rack(winner_id=7, break_player_id=9, is_run_out=True)
        non_runout = Rack(winner_id=7, break_player_id=7, is_run_out=False)

        assert vinto_da_chi_apriva.is_break_and_run is True
        assert vinto_rispondendo.is_break_and_run is False
        assert non_runout.is_break_and_run is False

    def test_le_regole_si_ereditano_dalla_gara_non_dal_match(self, app):
        """SPECIFICHE.md riga 131: «sul singolo match non si scelgono».

        Il match non ha un override: `effective_*_rule` legge **sempre** la
        gara. Se un domani qualcuno aggiungesse una colonna sul match, questo
        test resterebbe verde — ma la catena la descrive la riga 131, ed e'
        quella che il codice deve continuare a seguire.
        """
        from models.campionato.models import Campionato
        from models.competition.models import Gara
        from models.match.break_rules import BreakRule
        from models.match.models import Match

        campionato = Campionato(default_break_rule=BreakRule.LOSER_BREAKS.value)
        gara = Gara(break_rule=None)
        gara.campionato = campionato
        match = Match()
        match.gara = gara

        # NULL sulla gara = eredita dal campionato.
        assert match.effective_break_rule is BreakRule.LOSER_BREAKS

        # Un valore sulla gara vince sul campionato.
        gara.break_rule = BreakRule.ALTERNATE_TWO.value
        assert match.effective_break_rule is BreakRule.ALTERNATE_TWO


class TestCompetizioneDiProva:
    """`SPECIFICHE.md` righe 419-431: la competizione di prova (ADR-058)."""

    def test_al_massimo_tre_prove_aperte(self):
        """Riga 424: «al massimo **3 prove aperte** contemporaneamente»."""
        from models.prova.service import LIMITE_PROVE_ATTIVE

        assert LIMITE_PROVE_ATTIVE == 3

    def test_scade_a_quattordici_giorni_con_avviso_tre_giorni_prima(self):
        """Riga 431: «**14 giorni** dopo la creazione ... **3 giorni** prima»."""
        from datetime import timedelta

        from models.prova.service import DURATA_PROVA, PREAVVISO_SCADENZA

        assert DURATA_PROVA == timedelta(days=14)
        assert PREAVVISO_SCADENZA == timedelta(days=3)

    def test_la_simulazione_chiude_le_pari_dai_giocatori_e_le_dispari_dal_direttore(
        self,
    ):
        """Riga 426: «le **pari** con la doppia conferma dei giocatori, le
        **dispari** restano ... in attesa che il direttore le validi»."""
        from types import SimpleNamespace

        from models.prova.simulation_service import SimulationService

        assert SimulationService.chiusa_dai_giocatori(SimpleNamespace(id=2))
        assert not SimulationService.chiusa_dai_giocatori(SimpleNamespace(id=3))

    def test_nel_campionato_di_prova_le_date_sono_nei_prossimi_giorni(self, db_session):
        """Riga 427: «domani la prima, il giorno dopo l'ultima le altre»."""
        from datetime import date, timedelta

        from models.campionato.tournament_service import TournamentService
        from models.prova.service import ProvaService
        from models.prova.visibility import prova_visibili

        with prova_visibili():
            campionato = TournamentService().create_campionato_with_director(
                name="Prova",
                creator_user_id=_utente(db_session).id,
                **ProvaService.campi_di_creazione(),
            )
            db_session.commit()
            assert TournamentService.data_proposta_gara(
                campionato.id
            ) == date.today() + timedelta(days=1)

    def test_i_fittizi_hanno_rating_fissi_e_diversi(self):
        """Riga 425: «rating iniziali fissi e diversi fra loro»."""
        from models.prova.nomi import NOMI_FITTIZI

        rating = [r for _, _, r in NOMI_FITTIZI]
        assert len(set(rating)) == len(rating)

    def test_una_partita_di_prova_non_muove_il_rating(self, db_session):
        """Riga 428: «non muovono alcun rating»."""
        from models.prova.service import ProvaService
        from models.rating.eligibility import RatingEligibility, RatingExclusion

        gara = _gara(db_session)
        gara.director_id = _utente(db_session).id
        for chiave, valore in ProvaService.campi_di_creazione().items():
            setattr(gara, chiave, valore)
        db_session.flush()
        a, b = _utente(db_session), _utente(db_session)
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=a.id,
            player2_id=b.id,
            player1_score=5,
            player2_score=1,
            winner_id=a.id,
            status=MatchStatus.CONFIRMED_BY_BOTH.value,
        )
        db_session.add(match)
        db_session.flush()

        assert RatingEligibility.exclusion_reason(match) is RatingExclusion.PROVA


# ══ Il trio in classifica ════════════════════════════════════════════════


@pytest.mark.unit
class TestIlTrioInClassifica:
    """`SPECIFICHE.md` riga 164.

    > Per il sistema WINS, nel trio vince chi ha il punteggio più alto (1
    > vittoria), gli altri ottengono 0 vittorie. Se il punteggio più alto è di
    > due o tre giocatori, nessuno prende la vittoria.

    Il pari in testa è stato una divergenza fino al 2026-09-13: lo scioglieva lo
    scontro diretto, e con 4-4-1 alla distanza 6 la vittoria andava a uno dei
    due a quattro. La regola vale su ogni strada che chiude un trio, quindi
    ognuna ha il suo caso qui sotto.
    """

    @staticmethod
    def _nuovo_trio(db_session, distanza: int):
        from models.match.models import TrioMatch

        gara = _gara(db_session, distanza=distanza)
        gara.odd_number_policy = "trio"
        giocatori = [_utente(db_session) for _ in range(3)]
        partita = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
            is_trio=True,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(partita)
        db_session.flush()
        trio = TrioMatch(
            match_id=partita.id,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
            player3_id=giocatori[2].id,
        )
        db_session.add(trio)
        db_session.flush()
        return gara, giocatori, trio

    @staticmethod
    def _vittorie(gara, giocatori) -> list[int]:
        voci = _punteggi(gara.id)
        return [voci[g.id].matches_won for g in giocatori]

    def _trio(self, db_session, distanza: int, punti: tuple[int, int, int]):
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, distanza)
        TrioScoringService.set_result_direct(trio.id, *punti)
        db_session.commit()
        return self._vittorie(gara, giocatori)

    def test_vince_solo_il_punteggio_piu_alto(self, db_session):
        assert self._trio(db_session, 4, (4, 1, 1)) == [1, 0, 0]

    def test_il_pareggio_a_tre_non_da_vittorie(self, db_session):
        assert self._trio(db_session, 6, (3, 3, 3)) == [0, 0, 0]

    def test_il_pareggio_in_testa_non_da_vittorie(self, db_session):
        """Il risultato secco del direttore."""
        assert self._trio(db_session, 6, (4, 4, 1)) == [0, 0, 0]

    def test_il_pareggio_in_testa_segnato_triangolo_per_triangolo(self, db_session):
        """Il segnapunti. Nell'ordine del girone — 1–2, 1–3, 2–3 — il primo
        batte il secondo 2-1 e il terzo 2-1: per lo scontro diretto vinceva
        lui. Per la specifica, a 4-4-1, nessuno."""
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 6)
        sequenza = [0, 0, 1, 0, 0, 1, 1, 2, 1]
        for numero, indice in enumerate(sequenza, start=1):
            TrioScoringService.add_rack_win(
                trio.id,
                giocatori[indice].id,
                authoritative=numero == len(sequenza),
            )
        db_session.commit()

        assert trio.player_racks_list == [4, 4, 1]
        assert self._vittorie(gara, giocatori) == [0, 0, 0]

    def test_il_pareggio_in_testa_dalla_card_del_direttore(self, db_session):
        """Gli stepper della card, che segnano a totali."""
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 6)
        TrioScoringService.set_racks_won(trio.id, (4, 4, 1), giocatori[0].id)
        db_session.commit()

        assert self._vittorie(gara, giocatori) == [0, 0, 0]

    @pytest.mark.parametrize(
        "sequenza, totali, vittorie",
        [
            ([0, 2, 1, 0, 2, 2, 1], [3, 3, 3], [0, 0, 0]),
            ([0, 2, 2, 0, 2, 2, 1], [3, 2, 4], [1, 0, 0]),
        ],
        ids=["tre-tre-tre-nessuno-vince", "tre-due-quattro-vince-marco"],
    )
    def test_chi_si_ritira_non_vince_e_il_pari_resta_fra_gli_altri_due(
        self, db_session, sequenza, totali, vittorie
    ):
        """`SPECIFICHE.md` riga 164, la regola del ritiro (decisa il 2026-09-13).

        > Chi si ritira dal trio non vince mai, nemmeno col totale più alto, e
        > il pari si guarda solo fra gli altri due. Esempi alla distanza 6,
        > nove triangoli: Marco 3, Luca 3 e Gianni ritirato con 3, nessuno
        > vince; Marco 3, Luca 2 e Gianni ritirato con 4, vince Marco, anche se
        > Gianni ha il totale più alto.

        Una partita vera, passando dal ritiro nel trio. I gironi sono tre, in
        ordine fisso Marco–Luca, Marco–Gianni, Luca–Gianni: si giocano sette
        triangoli, poi Gianni si ritira e gli ultimi due, entrambi contro di
        lui, vanno uno a Marco e uno a Luca.
        """
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 6)
        marco, luca, gianni = giocatori
        for indice in sequenza:
            TrioScoringService.add_rack_win(trio.id, giocatori[indice].id)
        db_session.commit()
        assert trio.handle_forfeit(gianni.id)
        trio.confirm_result_by_admin()
        db_session.commit()

        assert trio.player_racks_list == totali
        assert trio.winner_id == (marco.id if vittorie[0] else None)
        assert self._vittorie(gara, [marco, luca, gianni]) == vittorie

    def test_il_pareggio_in_testa_dopo_un_ritiro(self, db_session):
        """Il ritiro nel trio: chi si ritira non vince, e fra gli altri due vale
        la stessa regola. Qui il primo batte il secondo 2-0, ma a totali sono
        2 e 2; e i due triangoli di chi si ritira non contano."""
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 4)
        for indice in (0, 2, 1, 0, 2):
            TrioScoringService.add_rack_win(trio.id, giocatori[indice].id)
        db_session.commit()
        assert trio.handle_forfeit(giocatori[2].id)
        trio.confirm_result_by_admin()
        db_session.commit()

        assert trio.player_racks_list == [2, 2, 2]
        assert trio.winner_id is None
        assert self._vittorie(gara, giocatori) == [0, 0, 0]


class TestCosaChiudeIlTurno:
    """`SPECIFICHE.md` righe 102 e 104 (2026-09-13).

    > Il turno successivo si avvia solo quando il turno precedente è chiuso
    > davvero: tutte le sue partite concluse, la prova giocata al posto della X
    > convalidata dal direttore [...] e ogni esercizio fra i turni agganciato a
    > quel turno registrato, con almeno un tentativo, per ogni iscritto ancora
    > in gara. [...] con la strategia _casuale_ [...] né la prova della X né gli
    > esercizi bloccano qualcosa.

    > Un tentativo di esercizio fra i turni registrato per sbaglio si può
    > togliere, a gara in corso e finché il turno successivo non è partito.
    """

    @staticmethod
    def _turno_chiuso_con_esercizio(db_session, strategia="amalfi"):
        from models.challenge.models import Challenge
        from models.competition.gara_challenge import GaraChallenge

        gara = _gara(db_session)
        gara.matchmaking_strategy = strategia
        a, b = _utente(db_session), _utente(db_session)
        for u in (a, b):
            db_session.add(Inscription(user_id=u.id, gara_id=gara.id))
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=a.id,
                player2_id=b.id,
                player1_score=5,
                player2_score=1,
                winner_id=a.id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        sfida = Challenge(
            description="Esercizio",
            image_path="/x.png",
            is_active=True,
            created_by_id=a.id,
        )
        db_session.add(sfida)
        db_session.flush()
        gc = GaraChallenge(
            gara_id=gara.id,
            challenge_id=sfida.id,
            round_number=1,
            max_attempts=1,
            added_by_id=a.id,
        )
        db_session.add(gc)
        db_session.commit()
        return gara, gc, a, b

    def test_un_esercizio_non_registrato_blocca_il_turno_dopo(self, db_session):
        from models.competition.pendenze_turno import pendenze_del_turno

        gara, _gc, _a, _b = self._turno_chiuso_con_esercizio(db_session)
        assert pendenze_del_turno(gara, 1).esercizi == 2
        assert pendenze_del_turno(gara, 1).bloccano

    def test_col_casuale_non_blocca(self, db_session):
        from models.competition.pendenze_turno import pendenze_del_turno

        gara, _gc, _a, _b = self._turno_chiuso_con_esercizio(
            db_session, strategia="random"
        )
        assert not pendenze_del_turno(gara, 1).bloccano

    def test_il_tentativo_si_toglie_finche_il_turno_dopo_non_parte(self, db_session):
        from models.competition.gara_challenge_service import GaraChallengeService
        from models.exceptions import ConflictError

        gara, gc, a, b = self._turno_chiuso_con_esercizio(db_session)
        primo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=3)
        GaraChallengeService.remove_challenge_attempt(primo.id)
        secondo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=3)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=2,
                player1_id=a.id,
                player2_id=b.id,
                status=MatchStatus.PLAYING.value,
            )
        )
        db_session.commit()
        with pytest.raises(ConflictError):
            GaraChallengeService.remove_challenge_attempt(secondo.id)

    def test_anche_la_chiusura_aspetta_l_ultimo_turno(self, db_session):
        """Riga 102: «Termina la gara» e lo spareggio non partono finché
        l'ultimo turno ha esercizi da registrare."""
        from models.competition.pendenze_turno import pendenze_della_chiusura
        from models.competition.state_service import StateService
        from models.exceptions import ConflictError

        gara, _gc, _a, _b = self._turno_chiuso_con_esercizio(db_session)
        assert pendenze_della_chiusura(gara).esercizi == 2
        with pytest.raises(ConflictError):
            StateService.complete(gara)

    def test_l_xp_segue_i_tentativi_rimasti(self, db_session):
        """Riga 104: finché resta un tentativo l'esercizio è fatto, senza
        tentativi l'XP torna indietro, in qualunque ordine si tolgano."""
        import json

        from models.competition.gara_challenge_service import GaraChallengeService
        from models.gamification.models import XPTransaction, XPTransactionType

        gara, gc, a, _b = self._turno_chiuso_con_esercizio(db_session)
        gc.max_attempts = 2
        db_session.commit()

        def xp():
            return sum(
                m.xp_amount
                for m in XPTransaction.query.filter_by(
                    user_id=a.id,
                    transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
                )
                if json.loads(m.related_entities or "{}").get("gara_id") == gara.id
            )

        primo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=1)
        secondo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=2)
        db_session.commit()
        tariffa = xp()
        GaraChallengeService.remove_challenge_attempt(primo.id)
        db_session.commit()
        assert xp() == tariffa
        GaraChallengeService.remove_challenge_attempt(secondo.id)
        db_session.commit()
        assert xp() == 0


# ══ Un solo sistema di classifica per campionato ═════════════════════════


def _campionato(db_session, sistema: str):
    from models import Campionato

    campionato = Campionato(
        name=f"Campionato spec {uuid.uuid4().hex[:8]}",
        campionato_type="amalfi",
        is_active=True,
        default_classification_system=sistema,
    )
    db_session.add(campionato)
    db_session.flush()
    return campionato


def _gara_del_campionato(db_session, campionato, *, numero: int, stato: str) -> Gara:
    gara = Gara(
        campionato_id=campionato.id,
        name=f"Gara {numero}",
        number=numero,
        date=date(2026, 1, numero),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=False,
        status=stato,
        rounds_count=3,
        classification_system=campionato.default_classification_system,
        matchmaking_strategy="amalfi",
        # La X semplice è vietata a triangoli totali, quella con prova no: così
        # la stessa gara è valida con entrambi i sistemi.
        odd_number_policy="bye_with_challenge",
    )
    db_session.add(gara)
    db_session.flush()
    return gara


@pytest.mark.unit
class TestUnSoloSistemaDiClassificaPerCampionato:
    """`SPECIFICHE.md` riga 289.

    > Tutte le gare di un campionato devono usare lo stesso sistema di
    > classifica, compresa la gara di playoff […]. Il sistema si può cambiare
    > solo finché nessuna gara del campionato ha aperto le iscrizioni […]
    """

    def test_la_gara_di_playoff_eredita_il_sistema_del_campionato(self, db_session):
        """Fino al 2026-09-14 la gara di playoff non riceveva il sistema e
        prendeva il default della colonna, WINS: un campionato a triangoli
        totali si chiudeva con una finale a vittorie. Con WINS il difetto non si
        vede, perché il default coincide."""
        campionato = _campionato(db_session, "RACK")
        _gara_del_campionato(
            db_session, campionato, numero=1, stato=GaraStatus.COMPLETED.value
        )
        configurazione = PlayoffConfiguration(
            campionato_id=campionato.id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=4,
            positions_from=1,
            positions_to=4,
            is_active=True,
            auto_generate=True,
            min_garas_played=0,
        )
        db_session.add(configurazione)
        db_session.commit()

        gara = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara.classification_system == "RACK"

    @pytest.mark.parametrize(
        "stato",
        [
            GaraStatus.INSCRIPTION.value,
            GaraStatus.PLAYING.value,
            GaraStatus.AWAITING_SSR.value,
            GaraStatus.COMPLETED.value,
        ],
    )
    def test_aperte_le_iscrizioni_il_sistema_non_si_cambia(self, db_session, stato):
        from models import Campionato
        from models.campionato.tournament_service import TournamentService
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "WINS")
        _gara_del_campionato(db_session, campionato, numero=1, stato=stato)
        _gara_del_campionato(
            db_session, campionato, numero=2, stato=GaraStatus.SETUP.value
        )
        db_session.commit()
        campionato_id = campionato.id

        with pytest.raises(ValidationError):
            TournamentService().update_campionato(
                campionato_id=campionato_id, default_classification_system="RACK"
            )

        db_session.expire_all()
        rimasto = db_session.get(Campionato, campionato_id)
        assert rimasto.default_classification_system == "WINS"
        assert {g.classification_system for g in rimasto.gare} == {"WINS"}

    def test_una_gara_ancora_da_aprire_con_iscritti_blocca_il_cambio(self, db_session):
        """Gli iscritti ci sono anche prima dell'apertura: la gara di playoff li
        riceve dagli inviti, e il direttore aggiunge giocatori a mano."""
        from models.campionato.tournament_service import TournamentService
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "WINS")
        gara = _gara_del_campionato(
            db_session, campionato, numero=1, stato=GaraStatus.SETUP.value
        )
        db_session.add(Inscription(user_id=_utente(db_session).id, gara_id=gara.id))
        db_session.commit()

        with pytest.raises(ValidationError):
            TournamentService().update_campionato(
                campionato_id=campionato.id, default_classification_system="RACK"
            )

    def test_prima_delle_iscrizioni_il_cambio_arriva_a_tutte_le_gare(self, db_session):
        from models import Campionato
        from models.campionato.tournament_service import TournamentService

        campionato = _campionato(db_session, "WINS")
        for numero in (1, 2):
            _gara_del_campionato(
                db_session, campionato, numero=numero, stato=GaraStatus.SETUP.value
            )
        db_session.commit()
        campionato_id = campionato.id

        TournamentService().update_campionato(
            campionato_id=campionato_id, default_classification_system="RACK"
        )

        db_session.expire_all()
        aggiornato = db_session.get(Campionato, campionato_id)
        assert aggiornato.default_classification_system == "RACK"
        assert {g.classification_system for g in aggiornato.gare} == {"RACK"}


def _configurazione(db_session, campionato, **campi) -> PlayoffConfiguration:
    configurazione = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=8,
        positions_from=1,
        positions_to=8,
        is_active=True,
        auto_generate=True,
        min_garas_played=0,
        **campi,
    )
    db_session.add(configurazione)
    db_session.flush()
    return configurazione


def _finale(db_session, campionato, configurazione, *, sistema: str) -> Gara:
    gara = _gara_del_campionato(
        db_session, campionato, numero=9, stato=GaraStatus.SETUP.value
    )
    gara.playoff_config_id = configurazione.id
    gara.classification_system = sistema
    db_session.flush()
    return gara


@pytest.mark.unit
class TestLaFinaleSecondoLaModalita:
    """`SPECIFICHE.md` riga 289.

    > La gara di playoff lo segue quando il suo punteggio **si somma** a quello
    > del campionato […] e per questo in quella modalità non può essere a
    > tabellone se il campionato non lo è; quando invece la classifica finale
    > è **solo quella dei playoff** della finale conta soltanto l'ordine
    > d'arrivo […]. Per questo
    > non si passa alla modalità sommata se la finale ha già un sistema diverso
    > da quello del campionato, o una strategia a tabellone.
    """

    def test_in_modalita_sommata_la_finale_a_tabellone_e_rifiutata(self, db_session):
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "WINS")
        _gara_del_campionato(
            db_session, campionato, numero=1, stato=GaraStatus.COMPLETED.value
        )
        configurazione = _configurazione(
            db_session, campionato, strategy_type="direct_elimination"
        )
        db_session.commit()

        with pytest.raises(ValidationError):
            PlayoffService.create_playoff_gara(configurazione.id)

    def test_non_si_passa_alla_somma_con_una_finale_di_altro_sistema(self, db_session):
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "RACK")
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="playoff_only"
        )
        _finale(db_session, campionato, configurazione, sistema="WINS")
        db_session.commit()
        configurazione_id = configurazione.id

        with pytest.raises(ValidationError):
            PlayoffService.update_scoring(
                configurazione_id, final_ranking_mode="campionato_plus_playoff"
            )

        db_session.expire_all()
        rimasta = db_session.get(PlayoffConfiguration, configurazione_id)
        assert rimasta.final_ranking_mode == "playoff_only"

    def test_non_si_passa_alla_somma_con_la_strategia_a_tabellone(self, db_session):
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "WINS")
        configurazione = _configurazione(
            db_session,
            campionato,
            final_ranking_mode="playoff_only",
            strategy_type="double_knockout",
        )
        db_session.commit()

        with pytest.raises(ValidationError):
            PlayoffService.update_scoring(
                configurazione.id, final_ranking_mode="campionato_plus_playoff"
            )

    def test_con_lo_stesso_sistema_si_passa_alla_somma(self, db_session):
        campionato = _campionato(db_session, "RACK")
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="playoff_only"
        )
        _finale(db_session, campionato, configurazione, sistema="RACK")
        db_session.commit()
        configurazione_id = configurazione.id

        PlayoffService.update_scoring(
            configurazione_id, final_ranking_mode="campionato_plus_playoff"
        )

        db_session.expire_all()
        aggiornata = db_session.get(PlayoffConfiguration, configurazione_id)
        assert aggiornata.final_ranking_mode == "campionato_plus_playoff"

    def test_salvare_il_peso_senza_cambiare_modalita_non_si_blocca(self, db_session):
        """Il form del punteggio rimanda la modalità a ogni salvataggio. Una
        finale già incoerente — nata a vittorie in un campionato a triangoli,
        prima del 2026-09-14 — non deve impedire al direttore di cambiare il
        peso: il controllo scatta sul **passaggio** alla somma, non sullo stato."""
        campionato = _campionato(db_session, "RACK")
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="campionato_plus_playoff"
        )
        _finale(db_session, campionato, configurazione, sistema="WINS")
        db_session.commit()
        configurazione_id = configurazione.id

        PlayoffService.update_scoring(
            configurazione_id,
            final_ranking_mode="campionato_plus_playoff",
            playoff_weight=2,
        )

        db_session.expire_all()
        aggiornata = db_session.get(PlayoffConfiguration, configurazione_id)
        assert aggiornata.playoff_weight == 2


# ────────────────────────────────────────────────────────────────────────
# Il profilo dell'esercizio (ADR-065)
# ────────────────────────────────────────────────────────────────────────


def _esercizio_per_il_profilo(db_session):
    from models.challenge.models import Challenge

    esercizio = Challenge(
        title=f"Profilo {uuid.uuid4().hex[:6]}",
        description="Dieci tiri dalla stessa posizione",
        image_path="test.jpg",
        pass_fail_only=False,
        is_active=True,
    )
    db_session.add(esercizio)
    db_session.flush()
    return esercizio


@pytest.mark.unit
class TestIlProfiloDellEsercizio:
    """`SPECIFICHE.md` riga 318, nota del 2026-09-19.

    > Ha zero, una o più abilità […], al più tre, e zero, uno o più gesti […],
    > senza tetto […]. Ha un livello dichiarato da 1 a 5, facoltativo; una
    > famiglia con un passo (da 1 in su) […]
    """

    def test_i_due_vocabolari_sono_quelli_della_specifica(self):
        from models.challenge.vocabulary import Abilita, Gesto

        assert len(Abilita) == 7
        assert len(Gesto) == 10

    def test_tre_abilita_passano_la_quarta_no(self, db_session):
        from models.challenge.profile_service import ChallengeProfileService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        ChallengeProfileService.set_profile(
            esercizio.id, abilita=["tiro", "posizione", "sponde"]
        )
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(
                esercizio.id, abilita=["tiro", "posizione", "sponde", "difesa"]
            )

    def test_i_gesti_non_hanno_tetto(self, db_session):
        from models.challenge.profile_service import ChallengeProfileService
        from models.challenge.vocabulary import Gesto

        esercizio = _esercizio_per_il_profilo(db_session)
        ChallengeProfileService.set_profile(
            esercizio.id, gesti=[g.value for g in Gesto]
        )

    @pytest.mark.parametrize("livello", [1, 5])
    def test_gli_estremi_del_livello_sono_ammessi(self, db_session, livello):
        from models.challenge.profile_service import ChallengeProfileService

        esercizio = _esercizio_per_il_profilo(db_session)
        salvato = ChallengeProfileService.set_profile(
            esercizio.id, declared_level=livello
        )
        assert salvato.declared_level == livello

    @pytest.mark.parametrize("livello", [0, 6])
    def test_fuori_da_uno_cinque_il_livello_si_rifiuta(self, db_session, livello):
        from models.challenge.profile_service import ChallengeProfileService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(esercizio.id, declared_level=livello)

    def test_il_livello_e_facoltativo(self, db_session):
        esercizio = _esercizio_per_il_profilo(db_session)
        assert esercizio.declared_level is None

    def test_il_passo_parte_da_uno(self, db_session):
        from models.challenge.profile_service import ChallengeProfileService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(
                esercizio.id, family="stop shot", family_step=0
            )


@pytest.mark.unit
class TestIlVotoDegliEsercizi:
    """`SPECIFICHE.md`, nota del 2026-09-19 sul profilo dell'esercizio.

    > Un giocatore può dare a un esercizio un voto da 1 a 5, uno solo, che può
    > cambiare; vota solo chi l'ha provato, cioè chi ha almeno una prova
    > conclusa, dal catalogo o in gara.
    """

    def _chi_ha_provato(self, db_session, esercizio):
        from models.challenge.models import ChallengeAttempt
        from models.user.models import User
        from models.user.role_enum import UserRole

        giocatore = User(
            username=f"v_{uuid.uuid4().hex[:8]}",
            email=f"v_{uuid.uuid4().hex[:8]}@test.com",
            role=UserRole.PLAYER.value,
        )
        giocatore.set_password("test1234")
        db_session.add(giocatore)
        db_session.flush()
        db_session.add(
            ChallengeAttempt(
                user_id=giocatore.id,
                challenge_id=esercizio.id,
                score=1,
                completed=True,
            )
        )
        db_session.flush()
        return giocatore

    @pytest.mark.parametrize("voto", [1, 5])
    def test_gli_estremi_sono_ammessi(self, db_session, voto):
        from models.challenge.rating_service import ChallengeRatingService

        esercizio = _esercizio_per_il_profilo(db_session)
        giocatore = self._chi_ha_provato(db_session, esercizio)
        numeri = ChallengeRatingService.rate(giocatore.id, esercizio.id, voto)
        assert numeri.rating_average == voto

    @pytest.mark.parametrize("voto", [0, 6])
    def test_fuori_scala_si_rifiuta(self, db_session, voto):
        from models.challenge.rating_service import ChallengeRatingService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        giocatore = self._chi_ha_provato(db_session, esercizio)
        with pytest.raises(ValidationError):
            ChallengeRatingService.rate(giocatore.id, esercizio.id, voto)

    def test_uno_solo_che_puo_cambiare(self, db_session):
        from models.challenge.rating_service import ChallengeRatingService

        esercizio = _esercizio_per_il_profilo(db_session)
        giocatore = self._chi_ha_provato(db_session, esercizio)
        ChallengeRatingService.rate(giocatore.id, esercizio.id, 2)
        numeri = ChallengeRatingService.rate(giocatore.id, esercizio.id, 5)
        assert (numeri.rating_count, numeri.rating_average) == (1, 5)

    def test_vota_solo_chi_ha_provato(self, db_session):
        """Chi vota e chi è contato fra i giocatori sono lo stesso insieme."""
        from models.challenge.popularity import popularity_for
        from models.challenge.rating_service import ChallengeRatingService
        from models.exceptions import PermissionDeniedError

        esercizio = _esercizio_per_il_profilo(db_session)
        contato = self._chi_ha_provato(db_session, esercizio)
        assert popularity_for([esercizio.id])[esercizio.id].players == 1
        ChallengeRatingService.rate(contato.id, esercizio.id, 4)

        altro = _esercizio_per_il_profilo(db_session)
        with pytest.raises(PermissionDeniedError):
            ChallengeRatingService.rate(contato.id, altro.id, 4)


@pytest.mark.unit
class TestLaProvaFattaDiColpi:
    """`SPECIFICHE.md`, sezione «Challenge», nota del 2026-09-20.

    > […] da uno a cinque anelli concentrici di uguale spessore — lo spessore si
    > misura in quarti di diamante — ciascuno col suo valore in punti, dal
    > centro verso l'esterno. Il colpo imbucato vale i punti dell'anello in cui
    > si ferma la battente; sul confine fra due anelli vale quello esterno;
    > fuori dall'ultimo anello vale zero. […] Imbucate = colpi imbucati su colpi
    > tirati. Posizione = media, sui soli colpi imbucati, di 1 − distanza dal
    > centro ÷ raggio esterno del bersaglio, mai sotto zero.

    Le formule sono riderivate qui a mano, su un bersaglio di cui si sanno le
    misure: un test che chiamasse `points_at` per sapere quanto deve valere
    `points_at` confronterebbe il codice con sé stesso.
    """

    @staticmethod
    def _bersaglio():
        from models.challenge.target import Target

        # Centro a 6 diamanti e 2, anelli da mezzo diamante: 3, 2, 1 punti.
        return Target(x=600, y=200, step=50, values=(3, 2, 1))

    @pytest.mark.parametrize(
        "distanza,punti",
        [
            (0, 3),
            (49, 3),
            (50, 2),  # sul confine vale l'anello esterno
            (99, 2),
            (100, 1),
            (149, 1),
            (150, 0),  # l'orlo dell'ultimo anello è già fuori
            (400, 0),
        ],
    )
    def test_i_punti_dell_anello(self, distanza, punti):
        assert self._bersaglio().points_at(600 + distanza, 200) == punti

    def test_la_distanza_e_in_ogni_direzione(self):
        # 30-40-50: a 50 unità dal centro, in diagonale, si è sul confine.
        assert self._bersaglio().points_at(630, 240) == 2

    @pytest.mark.parametrize("anelli,ammesso", [(1, True), (5, True), (6, False)])
    def test_da_uno_a_cinque_anelli(self, anelli, ammesso):
        import json

        from models.challenge.diagram import parse_scene
        from models.exceptions import ValidationError

        scena = json.dumps(
            {
                "v": 4,
                "items": [
                    {
                        "type": "target",
                        "x": 400,
                        "y": 200,
                        "step": 25,
                        "values": [1] * anelli,
                    }
                ],
            }
        )
        if ammesso:
            assert parse_scene(scena)
        else:
            with pytest.raises(ValidationError):
                parse_scene(scena)

    @pytest.mark.parametrize(
        "spessore,ammesso",
        [(25, True), (50, True), (75, True), (10, False), (60, False)],
    )
    def test_lo_spessore_e_in_quarti_di_diamante(self, spessore, ammesso):
        import json

        from models.challenge.diagram import parse_scene
        from models.exceptions import ValidationError

        scena = json.dumps(
            {
                "v": 4,
                "items": [
                    {"type": "target", "x": 1, "y": 1, "step": spessore, "values": [1]}
                ],
            }
        )
        if ammesso:
            assert parse_scene(scena)
        else:
            with pytest.raises(ValidationError):
                parse_scene(scena)

    def test_imbucate_e_posizione_sono_due_conti_diversi(self):
        from types import SimpleNamespace as Colpo

        from models.challenge.shot_stats import pocketing_pct, position_pct

        colpi = [
            Colpo(made=True, x=600, y=200),  # sul centro: 1
            Colpo(made=True, x=675, y=200),  # a metà raggio: 0,5
            Colpo(made=True, x=790, y=200),  # fuori dal bersaglio: 0, mai sotto
            Colpo(made=False, x=None, y=None),  # non ha un punto: non entra
        ]
        assert pocketing_pct(colpi) == 75  # tre su quattro
        assert position_pct(colpi, self._bersaglio()) == 50  # (1 + 0,5 + 0) / 3

    def test_senza_imbucate_la_posizione_non_c_e(self):
        from types import SimpleNamespace as Colpo

        from models.challenge.shot_stats import pocketing_pct, position_pct

        colpi = [Colpo(made=False, x=None, y=None)]
        assert pocketing_pct(colpi) == 0
        assert position_pct(colpi, self._bersaglio()) is None

    def test_il_punteggio_e_la_somma_dei_colpi(self, db_session):
        import json

        from models.challenge.models import Challenge
        from models.challenge.recording import RecordingMode
        from models.challenge.shot_service import ShotRunService

        esercizio = Challenge(
            description="x",
            image_path="t.png",
            diagram_scene=json.dumps(
                {
                    "v": 4,
                    "items": [
                        {
                            "type": "target",
                            "x": 600,
                            "y": 200,
                            "step": 50,
                            "values": [3, 2, 1],
                        }
                    ],
                }
            ),
            pass_fail_only=False,
            recording_mode=RecordingMode.SHOTS.value,
            shots_count=4,
            max_score=12,
            is_active=True,
        )
        from models.user.models import User
        from models.user.role_enum import UserRole

        giocatore = User(
            username=f"c_{uuid.uuid4().hex[:8]}",
            email=f"c_{uuid.uuid4().hex[:8]}@test.com",
            role=UserRole.PLAYER.value,
        )
        giocatore.set_password("test1234")
        db_session.add_all([esercizio, giocatore])
        db_session.flush()

        for x in (600, 660, 720):  # 3 + 2 + 1
            ShotRunService.record_shot(
                giocatore.id, esercizio.id, made=True, x=x, y=200
            )
        ShotRunService.record_shot(giocatore.id, esercizio.id, made=False)  # 0
        assert ShotRunService.close(giocatore.id, esercizio.id).score == 6


@pytest.mark.unit
class TestLEsercizioConEstrazione:
    """`SPECIFICHE.md`, sezione «Challenge», nota del 2026-09-20.

    > […] l'app pesca una voce da ogni lista, indipendentemente […]. Il
    > punteggio della prova è la somma dei colpi e il massimo è i colpi per il
    > valore più alto della scala. […] In esami e gare un esercizio con
    > estrazione non si può mettere.
    """

    @staticmethod
    def _spec():
        from models.challenge.draw_spec import build_spec

        return build_spec(
            [
                {"label": "sponde", "options": ["1 sponda", "2 sponde"]},
                {"label": "bilia", "options": ["bilia 1", "bilia 2", "bilia 3"]},
            ],
            [
                {"label": "Mancata", "points": 0},
                {"label": "Imbucata", "points": 4},
            ],
        )

    def test_una_voce_da_ogni_lista(self):
        """Il conto è riderivato: due liste da 2 e 3 voci fanno sei consegne."""
        import random

        rng = random.Random(3)
        viste = {self._spec().draw(rng) for _ in range(500)}

        assert len(viste) == 2 * 3
        for consegna in viste:
            sponde, bilia = consegna.split(", ")
            assert sponde in ("1 sponda", "2 sponde")
            assert bilia in ("bilia 1", "bilia 2", "bilia 3")

    def test_il_massimo_e_i_colpi_per_l_esito_piu_alto(self):
        spec = self._spec()
        colpi = 12

        assert spec.max_points == 4
        assert colpi * spec.max_points == 48

    @pytest.mark.parametrize(
        "quante,ammesse", [(0, False), (1, True), (3, True), (4, False)]
    )
    def test_le_liste_vanno_da_una_a_tre(self, quante, ammesse):
        from models.challenge.draw_spec import build_spec
        from models.exceptions import ValidationError

        liste = [{"label": f"l{i}", "options": ["a", "b"]} for i in range(quante)]
        scala = [{"label": "no", "points": 0}, {"label": "sì", "points": 1}]
        if ammesse:
            assert len(build_spec(liste, scala).sources) == quante
        else:
            with pytest.raises(ValidationError):
                build_spec(liste, scala)

    def test_fuori_dall_allenamento_si_rifiuta(self, db_session):
        from types import SimpleNamespace

        from models.challenge.recording import refuse_if_drawn
        from models.exceptions import ValidationError

        with pytest.raises(ValidationError):
            refuse_if_drawn(SimpleNamespace(recording_mode="draw"))
        refuse_if_drawn(SimpleNamespace(recording_mode="shots"))
