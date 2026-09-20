"""Gli esercizi con una componente estratta dall'app (fase 5c, #452).

Due pezzi: la **specifica** — che cosa estrae l'app, e con che scala si conta un
colpo — e l'**esecuzione**, che è quella colpo per colpo con una consegna al
posto del bersaglio.

La regola che tiene tutto insieme: la consegna del colpo che sta per essere
giocato si **persiste**. Se si riestraesse a ogni lettura, ricaricare la pagina
sarebbe un modo di cambiare la consegna finché non piace.
"""

from __future__ import annotations

import random
import uuid

import pytest

from models.challenge.draw_spec import (
    build_spec,
    dump_spec,
    outcomes_to_text,
    parse_draw_spec,
    parse_outcomes_text,
    parse_sources_text,
    sources_to_text,
)
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeShot
from models.challenge.recording import RecordingMode
from models.challenge.shot_service import ShotRunService
from models.exceptions import ConflictError, ValidationError
from models.user.models import User
from models.user.role_enum import UserRole

SORGENTI = [
    {"label": "sponde", "options": ["1 sponda", "2 sponde", "3 o più sponde"]},
    {"label": "bilia", "options": ["bilia 1", "bilia 7"]},
]
ESITI = [
    {"label": "Mancata", "points": 0, "hint": "non l'hai toccata"},
    {"label": "Colpita, senza sponda", "points": 1},
    {"label": "Colpita regolare", "points": 2},
    {"label": "Imbucata", "points": 4},
    {"label": "Colpita, e difesa riuscita", "points": 8},
]


class TestLaSpecifica:
    def test_si_scrive_e_si_rilegge(self):
        spec = parse_draw_spec(dump_spec(build_spec(SORGENTI, ESITI)))
        assert spec is not None
        assert [s.label for s in spec.sources] == ["sponde", "bilia"]
        assert spec.max_points == 8
        assert spec.outcomes[0].hint == "non l'hai toccata"

    def test_la_consegna_e_gia_a_parole(self):
        """Un generatore che stampa «37» lascia la decodifica al giocatore."""
        spec = build_spec(SORGENTI, ESITI)
        consegna = spec.draw(random.Random(1))
        sponde, bilia = consegna.split(", ")
        assert sponde in SORGENTI[0]["options"]
        assert bilia in SORGENTI[1]["options"]

    def test_le_sorgenti_sono_indipendenti(self):
        """Con due liste da 3 e 2 voci escono sei consegne diverse, tutte."""
        spec = build_spec(SORGENTI, ESITI)
        rng = random.Random(7)
        viste = {spec.draw(rng) for _ in range(400)}
        assert len(viste) == 6

    @pytest.mark.parametrize(
        "sorgenti,esiti",
        [
            ([], ESITI),  # nessuna lista
            ([{"label": "x", "options": ["una"]}], ESITI),  # una voce sola
            ([{"label": "", "options": ["a", "b"]}], ESITI),  # lista senza nome
            (SORGENTI, ESITI[:1]),  # un esito solo
            (SORGENTI, [{"label": "a", "points": 0}, {"label": "b", "points": 0}]),
            (SORGENTI, [{"label": "a", "points": "tre"}, {"label": "b", "points": 1}]),
            (SORGENTI, [{"label": "a", "points": -1}, {"label": "b", "points": 1}]),
        ],
    )
    def test_le_specifiche_storte_si_rifiutano(self, sorgenti, esiti):
        with pytest.raises(ValidationError):
            build_spec(sorgenti, esiti)

    def test_una_specifica_illeggibile_vale_come_assente(self):
        assert parse_draw_spec("{non json") is None
        assert parse_draw_spec(None) is None

    def test_l_esito_fuori_scala_si_rifiuta(self):
        """Mai il primo per ripiego: sarebbe un punteggio inventato."""
        spec = build_spec(SORGENTI, ESITI)
        for fuori in (-1, 5, "x", None):
            with pytest.raises(ValidationError):
                spec.outcome_at(fuori)


class TestComeSiScriveNelModulo:
    def test_una_lista_per_riga(self):
        liste = parse_sources_text(
            "sponde: 1 sponda | 2 sponde | 3 o più sponde\nbilia: bilia 1 | bilia 7"
        )
        assert liste == SORGENTI[0:1] + [
            {"label": "bilia", "options": ["bilia 1", "bilia 7"]}
        ]

    def test_un_esito_per_riga(self):
        esiti = parse_outcomes_text("Mancata = 0\nImbucata = 4")
        assert esiti == [
            {"label": "Mancata", "points": 0},
            {"label": "Imbucata", "points": 4},
        ]

    def test_il_giro_completo_torna_al_testo(self):
        spec = build_spec(SORGENTI, ESITI)
        rifatta = build_spec(
            parse_sources_text(sources_to_text(spec)),
            parse_outcomes_text(outcomes_to_text(spec)),
        )
        assert [s.options for s in rifatta.sources] == [s.options for s in spec.sources]
        assert [o.points for o in rifatta.outcomes] == [o.points for o in spec.outcomes]

    @pytest.mark.parametrize("riga", ["sponde", "sponde:", ": una | due"])
    def test_una_lista_scritta_male_si_rifiuta(self, riga):
        with pytest.raises(ValidationError):
            build_spec(parse_sources_text(riga), ESITI)

    @pytest.mark.parametrize("riga", ["Imbucata", "Imbucata = molti", "= 4"])
    def test_un_esito_scritto_male_si_rifiuta(self, riga):
        with pytest.raises(ValidationError):
            build_spec(SORGENTI, parse_outcomes_text(riga))


def _utente(db_session):
    u = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _esercizio(db_session, colpi=3):
    c = Challenge(
        title=f"Kicking {uuid.uuid4().hex[:5]}",
        description="x",
        image_path="t.png",
        pass_fail_only=False,
        recording_mode=RecordingMode.DRAW.value,
        shots_count=colpi,
        max_score=colpi * 8,
        draw_spec=dump_spec(build_spec(SORGENTI, ESITI)),
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


class TestEseguire:
    def test_si_comincia_estraendo(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        run = ShotRunService.draw_next(u.id, c.id)
        assert run.attempt is not None
        assert run.attempt.pending_prompt
        assert run.shots == []

    def test_la_consegna_non_cambia_a_ogni_lettura(self, db_session):
        """Riestraendo, ricaricare la pagina sarebbe un modo di rifare il tiro."""
        u, c = _utente(db_session), _esercizio(db_session)
        prima = ShotRunService.draw_next(u.id, c.id).attempt
        assert prima is not None
        consegna = prima.pending_prompt

        dopo = ShotRunService.current(u.id, c.id).attempt

        assert dopo is not None and dopo.pending_prompt == consegna

    def test_estrarre_due_volte_non_cambia_la_consegna(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        prima = ShotRunService.draw_next(u.id, c.id).attempt
        assert prima is not None
        consegna = prima.pending_prompt

        dopo = ShotRunService.draw_next(u.id, c.id).attempt

        assert dopo is not None and dopo.pending_prompt == consegna

    def test_il_colpo_prende_i_punti_dall_esito(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.draw_next(u.id, c.id)

        run = ShotRunService.record_outcome(u.id, c.id, outcome_index=3)

        colpo = run.shots[0]
        assert (colpo.points, colpo.outcome_label) == (4, "Imbucata")
        assert colpo.made is None  # qui «imbucata» è una voce fra tante
        assert colpo.prompt  # la consegna resta scritta sul colpo

    def test_dopo_il_colpo_la_consegna_e_gia_quella_dopo(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.draw_next(u.id, c.id)
        prima = ShotRunService.current(u.id, c.id).attempt
        assert prima is not None
        consegna = prima.pending_prompt

        run = ShotRunService.record_outcome(u.id, c.id, outcome_index=0)

        assert run.attempt is not None
        assert run.attempt.pending_prompt
        assert run.shots[0].prompt == consegna

    def test_all_ultimo_colpo_non_si_estrae_piu(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=1)
        ShotRunService.draw_next(u.id, c.id)

        run = ShotRunService.record_outcome(u.id, c.id, outcome_index=2)

        assert run.is_full is True
        assert run.attempt is not None and run.attempt.pending_prompt is None

    def test_senza_consegna_non_si_registra(self, db_session):
        """Prima si sa che cosa fare, poi si tira: mai il contrario."""
        u, c = _utente(db_session), _esercizio(db_session)
        with pytest.raises(ConflictError):
            ShotRunService.record_outcome(u.id, c.id, outcome_index=1)

    def test_l_annulla_rimette_la_consegna_di_quel_colpo(self, db_session):
        """Annullare non è un modo di riestrarre finché la consegna piace."""
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.draw_next(u.id, c.id)
        consegna = ShotRunService.current(u.id, c.id).attempt.pending_prompt
        ShotRunService.record_outcome(u.id, c.id, outcome_index=1)

        run = ShotRunService.undo_last(u.id, c.id)

        assert run.attempt is not None
        assert run.attempt.pending_prompt == consegna
        assert run.shots == []

    def test_chiudere_somma_i_colpi(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=2)
        for esito in (4, 2):  # 8 + 2
            ShotRunService.draw_next(u.id, c.id)
            ShotRunService.record_outcome(u.id, c.id, outcome_index=esito)

        chiusa = ShotRunService.close(u.id, c.id)

        assert (chiusa.completed, chiusa.score) == (True, 10)
        assert ChallengeShot.query.count() == 2

    def test_il_totale_a_mano_si_rifiuta(self, db_session):
        from models.challenge.services import ChallengeService

        u, c = _utente(db_session), _esercizio(db_session)
        with pytest.raises(ValidationError):
            ChallengeService.record_attempt(user_id=u.id, challenge_id=c.id, score=5)

    def test_il_panno_non_c_entra(self, db_session):
        """Qui non si tocca nessun punto: l'esito è una voce della scala."""
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.draw_next(u.id, c.id)
        with pytest.raises(ValidationError):
            ShotRunService.record_shot(u.id, c.id, made=True, x=600, y=200)

    def test_ricominciare_butta_anche_la_consegna(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.draw_next(u.id, c.id)

        ShotRunService.restart(u.id, c.id)

        assert ChallengeAttempt.query.count() == 0


class TestFuoriDallAllenamento:
    """Decisione del 2026-09-20: in esami e gare gli esercizi con estrazione non
    entrano. Due candidati riceverebbero consegne diverse, quindi prove non
    confrontabili — e un esame certifica, una gara fa classifica. La strada per
    ammetterli passa da un seme fissato, ed è un lavoro suo (#452, punto 5).
    """

    def test_un_esame_non_lo_accetta(self, db_session):
        from models.challenge.recording import refuse_if_drawn

        c = _esercizio(db_session)
        with pytest.raises(ValidationError):
            refuse_if_drawn(c)

    def test_gli_altri_modi_passano(self, db_session):
        from models.challenge.recording import refuse_if_drawn

        c = _esercizio(db_session)
        c.recording_mode = RecordingMode.SHOTS.value
        refuse_if_drawn(c)  # non solleva
        c.recording_mode = RecordingMode.TOTAL.value
        refuse_if_drawn(c)

    def test_la_x_non_lo_offre(self, db_session):
        """Il punteggio della X è una differenza triangoli in classifica."""
        from models.challenge.services import ChallengeService

        con_estrazione = _esercizio(db_session)
        normale = Challenge(
            title=f"Spot {uuid.uuid4().hex[:5]}",
            description="x",
            image_path="t.png",
            pass_fail_only=False,
            max_score=10,
            is_active=True,
        )
        db_session.add(normale)
        db_session.flush()

        offribili = {c.id for c in ChallengeService.get_challenges_for_x_choice()}

        assert normale.id in offribili
        assert con_estrazione.id not in offribili
