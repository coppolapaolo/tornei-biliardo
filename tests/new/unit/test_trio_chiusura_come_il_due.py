"""Il trio finisce come una partita a due: due stati finali, non uno.

Fino al 2026-08-21 il trio chiudeva sempre in `CLOSED_UNILATERALLY`, sia che
avessero confermato i tre giocatori sia che avesse firmato il direttore. La
partita a due invece i due casi li distingue da sempre (`CONFIRMED_BY_BOTH` per
l'accordo dei giocatori), e su quella distinzione poggia una regola concreta:
finche' la chiusura e' quella dei giocatori, l'ultimo triangolo si puo' ancora
annullare; dopo il sigillo del direttore no.

Il sintomo visibile era un riquadro che non compariva mai: il template del trio
chiedeva `match.validated_by_admin`, un attributo che su `Match` non esiste
(vive su `Rack`), perche' cercava di rileggere una distinzione che il modello
non scriveva da nessuna parte.

Qui si presidia il comportamento, non il nome: chi chiude, in quale stato si
finisce, e chi puo' ancora tornare indietro.
"""

from datetime import date

import pytest

from models.campionato.models import Campionato
from models.competition.models import Gara
from models.match.models import Match, TrioMatch
from models.match.trio_scoring_service import TrioScoringService
from models.status_enum import MatchStatus


def _crea_trio(db_session, isolated_players, distance: int = 3):
    """Un trio pronto a giocare, con la sua gara e il suo campionato."""
    campionato = Campionato(name=f"Campionato trio d{distance}")
    db_session.add(campionato)
    db_session.flush()

    gara = Gara(
        campionato_id=campionato.id,
        number=1,
        date=date.today(),
        distance=distance,
        discipline="9_ball",
    )
    db_session.add(gara)
    db_session.flush()

    p1, p2, p3 = isolated_players[0], isolated_players[1], isolated_players[2]
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        is_trio=True,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(match)
    db_session.flush()

    trio = TrioMatch(
        match_id=match.id,
        player1_id=p1.id,
        player2_id=p2.id,
        player3_id=p3.id,
    )
    db_session.add(trio)
    db_session.commit()
    return trio, match, [p1, p2, p3]


def _gioca_fino_alla_distanza(
    db_session, trio, players, added_by_id=None, authoritative=False
):
    """Distanza 3: tre triangoli. P0 ne vince due, P1 il terzo.

    Gli abbinamenti li decide `TrioConfig`: rack 1 = P0/P1, rack 2 = P0/P2,
    rack 3 = P1/P2. L'ultimo lo si segna con i parametri passati, perche' e'
    quello che fa scattare le firme implicite.
    """
    TrioScoringService.add_rack_win(trio.id, players[0].id)
    db_session.commit()
    TrioScoringService.add_rack_win(trio.id, players[0].id)
    db_session.commit()
    TrioScoringService.add_rack_win(
        trio.id,
        players[1].id,
        added_by_id=added_by_id,
        authoritative=authoritative,
    )
    db_session.commit()
    return db_session.get(TrioMatch, trio.id)


class TestQualeStatoFinale:
    def test_le_tre_conferme_chiudono_come_una_doppia_conferma(
        self, db_session, isolated_players
    ):
        """Tre giocatori d'accordo = i due della partita a due: CONFIRMED_BY_BOTH."""
        trio, match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(db_session, trio, players)
        assert trio.awaiting_confirmation

        for p in players:
            if not trio.is_completed:
                trio.confirm_result_by_player(p.id)
                db_session.commit()
                trio = db_session.get(TrioMatch, trio.id)

        assert trio.is_completed
        match = db_session.get(Match, match.id)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH.value, (
            "chiuso dai giocatori: deve restare annullabile finche' il "
            "direttore non valida"
        )

    def test_la_firma_del_direttore_mette_agli_atti(self, db_session, isolated_players):
        """Il direttore scavalca le conferme: CLOSED_UNILATERALLY, come sempre."""
        trio, match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(db_session, trio, players)

        trio.confirm_result_by_admin()
        db_session.commit()

        trio = db_session.get(TrioMatch, trio.id)
        assert trio.is_completed
        match = db_session.get(Match, match.id)
        assert match.status == MatchStatus.CLOSED_UNILATERALLY.value

    def test_entrambe_le_chiusure_contano_come_partita_giocata(
        self, db_session, isolated_players
    ):
        """Qualunque sia lo stato finale, a valle la partita e' finita.

        Turni, classifiche e tabellone passano tutti da `is_finished()`: se la
        distinzione appena introdotta rompesse quel conto, un trio chiuso dai
        giocatori smetterebbe di far avanzare il turno.
        """
        trio, match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(db_session, trio, players)
        for p in players:
            if not trio.is_completed:
                trio.confirm_result_by_player(p.id)
                db_session.commit()
                trio = db_session.get(TrioMatch, trio.id)

        match = db_session.get(Match, match.id)
        assert MatchStatus.is_finished(match.status)


class TestFirmeImplicite:
    def test_chi_vince_e_gia_daccordo(self, db_session, isolated_players):
        """Il vincitore non ha ragione di contestare il proprio risultato."""
        trio, _match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(db_session, trio, players)

        assert trio.winner_id is not None, "servono racks decisivi per il test"
        confermati = {
            players[0].id: trio.player1_confirmed,
            players[1].id: trio.player2_confirmed,
            players[2].id: trio.player3_confirmed,
        }
        assert confermati[trio.winner_id], "il vincitore deve essere gia' confermato"

    def test_chi_segna_lultimo_triangolo_e_gia_daccordo(
        self, db_session, isolated_players
    ):
        """Segnare la mano che chiude la partita e' gia' riconoscerla."""
        trio, _match, players = _crea_trio(db_session, isolated_players)
        # L'ultimo triangolo lo inserisce P2, che non lo vince e non vince il trio.
        trio = _gioca_fino_alla_distanza(
            db_session, trio, players, added_by_id=players[2].id
        )

        assert trio.player3_confirmed, "chi ha inserito deve essere gia' confermato"

    def test_chi_non_ha_ne_vinto_ne_segnato_deve_confermare(
        self, db_session, isolated_players
    ):
        """L'auto-accettazione non e' una chiusura d'ufficio: qualcuno resta."""
        trio, match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(
            db_session, trio, players, added_by_id=players[2].id
        )

        assert trio.awaiting_confirmation, "manca ancora una firma"
        assert not trio.is_completed
        match = db_session.get(Match, match.id)
        assert not MatchStatus.is_finished(match.status)

    def test_il_direttore_che_segna_chiude_da_solo(self, db_session, isolated_players):
        """Chi dirige scrive gia' il punteggio ufficiale: non si autovalida."""
        trio, match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(
            db_session, trio, players, added_by_id=players[0].id, authoritative=True
        )

        assert trio.is_completed, "con la firma di tutti non resta niente da chiedere"
        match = db_session.get(Match, match.id)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH.value, (
            "il gesto e' implicito, non irrevocabile: resta annullabile finche' "
            "il direttore non valida esplicitamente"
        )


class TestFinestraDiRipensamento:
    def test_dopo_le_conferme_si_puo_ancora_annullare(
        self, db_session, isolated_players
    ):
        """Quel che i giocatori hanno concordato, i giocatori possono disfarlo."""
        trio, match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(db_session, trio, players)
        for p in players:
            if not trio.is_completed:
                trio.confirm_result_by_player(p.id)
                db_session.commit()
                trio = db_session.get(TrioMatch, trio.id)

        rimosso = TrioScoringService.remove_last_rack(trio.id, players[0].id)
        db_session.commit()

        assert rimosso is not None
        trio = db_session.get(TrioMatch, trio.id)
        assert not trio.is_completed, "l'annullamento riapre la partita"

    def test_dopo_il_sigillo_del_direttore_il_server_rifiuta(
        self, db_session, isolated_players
    ):
        """Il guard sta sul server, non nel template.

        Prima del 2026-08-21 l'unica difesa era il pulsante nascosto: una POST
        diretta all'endpoint riapriva una partita gia' messa agli atti.
        """
        trio, _match, players = _crea_trio(db_session, isolated_players)
        trio = _gioca_fino_alla_distanza(db_session, trio, players)
        trio.confirm_result_by_admin()
        db_session.commit()

        with pytest.raises(ValueError, match="validato"):
            TrioScoringService.remove_last_rack(trio.id, players[0].id)
