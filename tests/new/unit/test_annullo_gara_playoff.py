"""Annullare la gara di playoff riporta il playoff a «gara non ancora creata».

Segnalato il 2026-09-13 in sviluppo: «Annulla la gara» sulla gara di playoff
mostrava «Errore durante la cancellazione:» seguito dalla pagina di Werkzeug,
`FOREIGN KEY constraint failed` su `DELETE FROM gara`. La riga legacy
`PlayoffTournament` (tabella `playoff_campionato`) punta alla gara con una
chiave esterna senza `ON DELETE`, e `create_playoff_gara` la scrive sempre:
nessuna gara di playoff era mai cancellabile.

`SPECIFICHE.md` non dice che cosa succede annullando la gara di playoff. Dice
però, sezione «Playoff», che gli inviti partono **prima** della gara e che chi
accetta entra fra gli iscritti: gli inviti sono il fatto, la gara è ciò che ne
discende. Regola scelta, la meno distruttiva: la gara sparisce con le sue
iscrizioni, gli inviti restano come sono, e ricreando la gara i confermati
rientrano d'ufficio.
"""

from __future__ import annotations

from models.base import db
from models.competition.models import Gara
from models.competition.services import GaraService
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from tests.new.unit.test_avvio_playoff import _make_user
from tests.new.unit.test_playoff_con_meno_accettazioni import (
    _accetta,
    _iscritti,
    _playoff,
    _rifiuta,
)


def _torneo(cfg) -> PlayoffTournament:
    return PlayoffTournament.query.filter_by(configuration_id=cfg.id).one()


class TestAnnullareLaGaraDiPlayoff:
    def test_la_gara_sparisce_senza_violare_la_chiave_esterna(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4)
        _accetta(cfg, *giocatori)
        direttore = _make_user(db_session, role="director")
        gara_id = PlayoffService.create_playoff_gara(cfg.id).id
        assert _torneo(cfg).gara_id == gara_id

        GaraService.cancel_gara_with_notifications(gara_id, direttore.id)

        db.session.expire_all()
        assert db.session.get(Gara, gara_id) is None
        assert db.session.get(PlayoffConfiguration, cfg.id).gara is None
        torneo = _torneo(cfg)
        assert torneo.gara_id is None
        assert torneo.status == "setup"
        assert torneo.confirmed_participants == 0

    def test_gli_inviti_restano_come_sono(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4)
        _accetta(cfg, *giocatori[:3])
        direttore = _make_user(db_session, role="director")
        gara_id = PlayoffService.create_playoff_gara(cfg.id).id

        GaraService.cancel_gara_with_notifications(gara_id, direttore.id)

        db.session.expire_all()
        stati = {
            invito.user_id: invito.status
            for invito in PlayoffQualification.query.filter_by(configuration_id=cfg.id)
        }
        attesi = {g.id: QualificationStatus.CONFIRMED for g in giocatori[:3]}
        attesi[giocatori[3].id] = QualificationStatus.PENDING
        assert stati == attesi

    def test_ricreata_la_gara_i_confermati_rientrano(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4)
        _accetta(cfg, *giocatori)
        direttore = _make_user(db_session, role="director")
        prima = PlayoffService.create_playoff_gara(cfg.id).id
        GaraService.cancel_gara_with_notifications(prima, direttore.id)
        db.session.expire_all()

        seconda = PlayoffService.create_playoff_gara(cfg.id)

        # L'id può coincidere: SQLite riusa il rowid liberato dalla cancellazione.
        assert _iscritti(seconda.id) == {g.id for g in giocatori}
        torneo = _torneo(cfg)
        assert torneo.gara_id == seconda.id
        assert torneo.status == "registration"

    def test_cancellare_la_gara_di_playoff_ancora_vuota(self, db_session):
        """Nessun «sì»: la gara nasce in preparazione senza iscritti, e il
        pulsante «Elimina» della preparazione passa da `delete_gara`."""
        _c, cfg, giocatori = _playoff(db_session, posti=2)
        for giocatore in giocatori:
            _rifiuta(cfg, giocatore)
        gara_id = PlayoffService.create_playoff_gara(cfg.id).id

        GaraService.delete_gara(gara_id)

        db.session.expire_all()
        assert db.session.get(Gara, gara_id) is None
        assert _torneo(cfg).gara_id is None
