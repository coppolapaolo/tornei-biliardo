"""Nome e cognome: facoltativi, modificabili dal profilo, via con la persona.

Lo username è un soprannome. Il direttore che deve iscrivere «marco» quando
esistono anche `marco_b` e `marcob` non ha modo di sapere quale sia quello
giusto, e l'email — che glielo direbbe — non si mostra a nessuno (issue #156).
"""

from __future__ import annotations

import pytest

from models.user.profile_service import UserProfileService


@pytest.fixture
def utente(db_session):
    from models.user.models import User

    user = User(
        username="marco_b",
        email="marco.b@example.com",
        role="player",
    )
    user.set_password("password-di-prova")
    db_session.add(user)
    db_session.commit()
    return user


class TestNomeCompleto:
    def test_senza_anagrafica_non_c_e_nome_completo(self, utente):
        """`None`, non stringa vuota: il template scrive `full_name or username`."""
        assert utente.full_name is None

    def test_nome_e_cognome_si_compongono(self, db_session, utente):
        utente.first_name = "Marco"
        utente.last_name = "Bianchi"
        db_session.commit()

        assert utente.full_name == "Marco Bianchi"

    def test_solo_il_nome_basta(self, db_session, utente):
        utente.first_name = "Marco"
        db_session.commit()

        assert utente.full_name == "Marco"

    def test_spazi_soli_non_sono_un_nome(self, db_session, utente):
        utente.first_name = "   "
        db_session.commit()

        assert utente.full_name is None


class TestModificaDalProfilo:
    def test_il_profilo_puo_scrivere_nome_e_cognome(self, db_session, utente):
        """Erano fuori da `allowed_fields`: il form li mandava e nessuno li salvava."""
        UserProfileService.update_user(
            utente.id, first_name="Marco", last_name="Bianchi"
        )

        assert utente.full_name == "Marco Bianchi"

    def test_svuotarli_e_una_cancellazione_voluta(self, db_session, utente):
        """Diversamente da username ed email, qui il vuoto è legittimo."""
        UserProfileService.update_user(
            utente.id, first_name="Marco", last_name="Bianchi"
        )
        UserProfileService.update_user(utente.id, first_name="", last_name="")

        assert utente.full_name is None


class TestAnonimizzazione:
    def test_l_anagrafica_se_ne_va_con_la_persona(self, db_session, utente):
        """È il dato più identificante che l'applicazione conservi."""
        utente.first_name = "Marco"
        utente.last_name = "Bianchi"
        db_session.commit()

        utente.anonymize()
        db_session.commit()

        assert utente.first_name is None
        assert utente.last_name is None
        assert utente.full_name is None
