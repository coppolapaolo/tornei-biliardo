"""Quale Elo compare accanto a un giocatore sul tabellone, e quando non compare.

Tre regole, e ognuna ha un modo suo di rompersi in silenzio:

* **il pool lo decide la partita.** Le gare muovono l'Elo competitivo, le sfide
  individuali il globale. Scriverne uno al posto dell'altro non solleva niente:
  mostra un numero plausibile che quella partita non muoverà mai.
* **`show_elo` è opt-out.** È l'unica preferenza privacy accesa di suo, e la
  riga di impostazioni nasce solo al primo salvataggio: se `can_view_field`
  trattasse l'assenza della riga come «privato» — che è la regola per tutti gli
  altri campi — l'Elo sarebbe nascosto per la quasi totalità degli utenti, con
  la casella spuntata nella pagina privacy.
* **niente valore, niente numero.** Nel pool globale un giocatore senza partite
  chiuse non ha un rating: lì non si stampa 1200 di ripiego.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from models import db
from models.base import utc_now
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import MatchStatus
from models.individual_match.match_models import IndividualMatch
from models.user.models import User
from models.user.privacy_service import PrivacyService
from models.user.role_enum import UserRole
from utils.elo_visibility import elo_for_match, elo_pool_label, is_competitive_pool


def _user(elo: int | None = 1350) -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(
        username=f"u_{tag}",
        email=f"{tag}@example.test",
        role=UserRole.PLAYER.value,
        elo_rating=elo,
    )
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _elo_globale(user: User, valore: int) -> PlayerRating:
    rating = PlayerRating(
        user_id=user.id,
        rating_system=RatingSystem.ELO_GLOBAL,
        rating_value=float(valore),
    )
    db.session.add(rating)
    db.session.commit()
    return rating


def _sfida(uno: User, due: User) -> IndividualMatch:
    match = IndividualMatch(
        player1_id=uno.id,
        player2_id=due.id,
        scheduled_at=utc_now(),
        status=MatchStatus.IN_PROGRESS,
        discipline="palla_9",
        distance=5,
        player1_score=0,
        player2_score=0,
    )
    db.session.add(match)
    db.session.commit()
    return match


class _PartitaDiGara:
    """Il minimo che `elo_for_match` guarda di un match di gara."""

    def __init__(self, uno: User, due: User):
        self.gara_id = 7
        self.player1 = uno
        self.player2 = due


class TestQualePool:
    def test_la_gara_mostra_il_competitivo(self, app):
        uno, due = _user(elo=1420), _user()
        _elo_globale(uno, 1180)

        assert elo_for_match(_PartitaDiGara(uno, due), uno) == 1420

    def test_la_sfida_individuale_mostra_il_globale(self, app):
        uno, due = _user(elo=1420), _user()
        _elo_globale(uno, 1180)

        assert elo_for_match(_sfida(uno, due), uno) == 1180

    def test_una_sfida_individuale_non_ha_proprio_gara_id(self, app):
        """La discriminante è una colonna, non una convenzione di nomi."""
        uno, due = _user(), _user()
        assert is_competitive_pool(_sfida(uno, due)) is False
        assert is_competitive_pool(_PartitaDiGara(uno, due)) is True

    def test_le_due_etichette_sono_diverse(self, app):
        uno, due = _user(), _user()
        assert elo_pool_label(_PartitaDiGara(uno, due)) != elo_pool_label(
            _sfida(uno, due)
        )


class TestPrivacy:
    def test_senza_impostazioni_lelo_si_vede(self, app):
        """Il caso di quasi tutti: la pagina privacy non l'hanno mai aperta."""
        giocatore, avversario = _user(elo=1300), _user()

        assert PrivacyService.can_view_field(avversario.id, giocatore.id, "elo") is True
        assert (
            elo_for_match(_PartitaDiGara(giocatore, avversario), giocatore, avversario)
            == 1300
        )

    def test_nasce_acceso_anche_quando_la_riga_esiste(self, app):
        giocatore = _user()
        impostazioni = PrivacyService.get_privacy_settings(giocatore.id)
        assert impostazioni.show_elo is True

    def test_spegnerlo_lo_toglie_dal_tabellone(self, app):
        giocatore, avversario = _user(elo=1300), _user()
        PrivacyService.update_privacy_settings(user_id=giocatore.id, show_elo=False)

        assert (
            elo_for_match(_PartitaDiGara(giocatore, avversario), giocatore, avversario)
            is None
        )

    def test_il_diretto_interessato_lo_vede_lo_stesso(self, app):
        """Nascosto agli altri, non a sé: è il suo numero."""
        giocatore, avversario = _user(elo=1300), _user()
        PrivacyService.update_privacy_settings(user_id=giocatore.id, show_elo=False)

        assert (
            elo_for_match(_PartitaDiGara(giocatore, avversario), giocatore, giocatore)
            == 1300
        )

    def test_gli_altri_campi_restano_opt_in(self, app):
        """La regola generale non si muove: l'eccezione è una sola."""
        giocatore, altro = _user(), _user()

        for campo in ("email", "phone", "statistics", "recent_matches"):
            assert (
                PrivacyService.can_view_field(altro.id, giocatore.id, campo) is False
            ), campo

    def test_un_campo_inventato_resta_privato(self, app):
        giocatore, altro = _user(), _user()
        PrivacyService.get_privacy_settings(giocatore.id)

        assert PrivacyService.can_view_field(altro.id, giocatore.id, "boh") is False


class TestNienteNumeriDiRipiego:
    def test_senza_rating_globale_non_si_stampa_1200(self, app):
        uno, due = _user(elo=1400), _user()

        assert elo_for_match(_sfida(uno, due), uno) is None

    def test_la_x_a_tavolino_non_ha_un_elo(self, app):
        uno = _user()
        assert elo_for_match(_PartitaDiGara(uno, uno), None) is None


class TestIlTabelloneNonUsaIlToggle:
    def test_il_valore_sul_tabellone_non_e_marcato_elo_value(self):
        """`window.EloToggle` riscrive ogni `.elo-value` col pool salvato.

        Sul tabellone il pool lo decide il tipo di partita: marcarlo così
        vorrebbe dire che un clic altrove nella pagina ci scrive sopra l'altro
        numero, contraddicendo la riga sotto al nome senza che niente lo dica.
        """
        board = Path("templates/components/_match_scoreboard.html").read_text(
            encoding="utf-8"
        )
        assert "c7-board__elo" in board
        assert not re.search(r'class="[^"]*\belo-value\b', board)
