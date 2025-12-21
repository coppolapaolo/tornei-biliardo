"""
Test di characterization per GaraService esistente.

Questi test documentano il comportamento attuale di GaraService prima
del refactoring, catturando la logica di business esistente per
garantire che il refactoring non introduca regressioni.

Organizzazione:
- Creazione e query gare
- Gestione stato (state machine)
- Gestione iscrizioni e date
- Sistema di matchmaking e turni
- Validazione e regole business
- Gestione direttori e permessi
"""

import pytest
from datetime import datetime, date, time, timedelta
from sqlalchemy.exc import IntegrityError

from models.base import db
from models.competition.services import (
    GaraService,
    InscriptionService,
)
from models.competition.state_service import StateService
from models.competition.models import Gara, Inscription
from models.user.models import User
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.exceptions import InvalidTransitionError


class TestGaraServiceCharacterization:
    """Test che caratterizzano il comportamento attuale di GaraService."""

    def setup_method(self, method):
        """Setup per ogni test."""
        # Crea utenti di test
        self.admin_user = User(
            username="admin_test", email="admin@test.com", role=UserRole.ADMIN.value
        )
        self.admin_user.set_password("password123")

        self.director_user = User(
            username="director_test",
            email="director@test.com",
            role=UserRole.DIRECTOR.value,
        )
        self.director_user.set_password("password123")

        self.player_user = User(
            username="player_test", email="player@test.com", role=UserRole.PLAYER.value
        )
        self.player_user.set_password("password123")

        db.session.add(self.admin_user)
        db.session.add(self.director_user)
        db.session.add(self.player_user)
        db.session.commit()

    def teardown_method(self, method):
        """Cleanup dopo ogni test."""
        # Rimuovi tutti i dati di test nell'ordine corretto per evitare FK constraints
        try:
            db.session.query(Inscription).delete()
            db.session.commit()

            db.session.query(Gara).delete()
            db.session.commit()

            # Rimuovi eventuali DirectorAssignment e Notification
            from models.user.models import DirectorAssignment

            db.session.query(DirectorAssignment).delete()
            db.session.commit()

            from models.notification.models import Notification

            db.session.query(Notification).delete()
            db.session.commit()

            db.session.query(User).delete()
            db.session.commit()
        except Exception:
            db.session.rollback()

    # ===== CREAZIONE E QUERY GARE =====

    def test_create_gara_standalone_characterization(self):
        """Caratterizza la creazione di gare standalone."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Caratteristiche esistenti
        assert gara.id is not None
        assert gara.number == 1
        assert gara.name == "Test Gara"
        assert gara.date == tomorrow
        assert gara.discipline == "palla 8"
        assert gara.distance == 5
        assert gara.campionato_id is None  # standalone
        assert gara.director_id == self.director_user.id
        assert gara.status == GaraStatus.SETUP.value
        assert gara.current_round == 0
        assert gara.rounds_count == 3  # default
        assert gara.min_participants == 2  # default
        assert gara.max_participants is None
        assert gara.entry_fee == 0.0  # default
        assert gara.matchmaking_strategy == "amalfi"  # default
        assert gara.withdraw_policy == "Exclude"  # default

    def test_create_gara_validation_characterization(self):
        """Caratterizza le validazioni nella creazione gara."""
        tomorrow = date.today() + timedelta(days=1)

        # Deve avere director_id o campionato_id
        with pytest.raises(
            ValueError, match="deve avere un campionato_id o un director_id"
        ):
            GaraService.create_gara(
                number=1, name="Test", date=tomorrow, discipline="palla 8", distance=5
            )

        # Data non può essere nel passato
        yesterday = date.today() - timedelta(days=1)
        with pytest.raises(
            ValueError, match="Data della gara non può essere nel passato"
        ):
            GaraService.create_gara(
                number=1,
                name="Test",
                date=yesterday,
                discipline="palla 8",
                distance=5,
                director_id=self.director_user.id,
            )

    def test_get_gara_by_id_characterization(self):
        """Caratterizza il recupero gare per ID."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Recupero esistente
        retrieved = GaraService.get_gara_by_id(gara.id)
        assert retrieved is not None
        assert retrieved.id == gara.id
        assert retrieved.name == "Test Gara"

        # ID non esistente
        non_existent = GaraService.get_gara_by_id(99999)
        assert non_existent is None

    def test_update_gara_characterization(self):
        """Caratterizza l'aggiornamento gare."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Original Name",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Aggiornamento riuscito quando no iscrizioni
        updated = GaraService.update_gara(gara.id, name="Updated Name", distance=7)
        assert updated.name == "Updated Name"
        assert updated.distance == 7

        # Con iscrizioni non si può modificare
        InscriptionService.inscribe_user(self.player_user.id, gara.id)

        with pytest.raises(ValueError, match="Impossibile modificare.*iscrizioni"):
            GaraService.update_gara(gara.id, name="Another Name")

    def test_delete_gara_characterization(self):
        """Caratterizza la cancellazione gare."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Cancellazione riuscita quando no iscrizioni
        GaraService.delete_gara(gara.id)
        assert GaraService.get_gara_by_id(gara.id) is None

        # Crea nuova gara per test con iscrizioni
        gara2 = GaraService.create_gara(
            number=2,
            name="Test Gara 2",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Con iscrizioni non si può cancellare
        InscriptionService.inscribe_user(self.player_user.id, gara2.id)

        with pytest.raises(ValueError, match="Impossibile cancellare.*iscrizioni"):
            GaraService.delete_gara(gara2.id)

    # ===== GESTIONE STATO (STATE MACHINE) =====

    def test_state_machine_transitions_characterization(self):
        """Caratterizza le transizioni della state machine."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Stato iniziale
        assert gara.status == GaraStatus.SETUP.value

        # setup -> inscription (richiede date)
        start_time = datetime.utcnow() + timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)

        # Rimuovi le date di iscrizione per testare la validazione
        # (create_gara le imposta automaticamente per prevenire errori di stato)
        gara.inscription_start = None
        gara.inscription_end = None
        db.session.add(gara)
        db.session.commit()

        with pytest.raises(
            InvalidTransitionError, match="Date di iscrizione non impostate"
        ):
            StateService.to_inscription(gara)

        # Con date funziona
        gara.inscription_start = start_time
        gara.inscription_end = end_time
        gara = StateService.to_inscription(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value

        # inscription -> setup
        gara = StateService.reopen_setup(gara)
        assert gara.status == GaraStatus.SETUP.value

        # setup -> inscription -> playing (richiede iscritti)
        gara = StateService.to_inscription(gara)

        with pytest.raises(InvalidTransitionError, match="Giocatori insufficienti"):
            StateService.start_playing(gara)

        # Con iscritti funziona (prima devo aprire le iscrizioni)
        start_time = datetime.utcnow() - timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)

        # Ripristino lo stato setup se necessario
        if gara.status != GaraStatus.SETUP.value:
            gara.status = GaraStatus.SETUP.value
            db.session.commit()

        gara.inscription_start = start_time
        gara.inscription_end = end_time
        db.session.commit()

        gara = StateService.to_inscription(gara)
        InscriptionService.inscribe_user(self.player_user.id, gara.id)
        InscriptionService.inscribe_user(self.director_user.id, gara.id)

        gara = StateService.start_playing(gara)
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # playing -> completed
        gara = StateService.complete(gara)
        assert gara.status == GaraStatus.COMPLETED.value

    def test_state_machine_validation_errors_characterization(self):
        """Caratterizza gli errori di validazione della state machine."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Transizioni non ammesse
        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            StateService.start_playing(gara)  # setup -> playing non ammesso

        gara.status = GaraStatus.PLAYING.value
        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            StateService.to_inscription(gara)  # playing -> inscription non ammesso

    # ===== GESTIONE ISCRIZIONI E DATE =====

    def test_open_inscriptions_characterization(self):
        """Caratterizza l'apertura iscrizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            time=time(18, 0),
        )

        # Date valide
        start_time = datetime.utcnow() + timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)

        updated_gara = InscriptionService.open_inscriptions(
            gara.id, start_time, end_time
        )

        assert updated_gara.status == GaraStatus.INSCRIPTION.value
        assert updated_gara.inscription_start == start_time
        assert updated_gara.inscription_end == end_time

        # Date invalide
        with pytest.raises(ValueError, match="inizio deve essere precedente"):
            InscriptionService.open_inscriptions(gara.id, end_time, start_time)

    def test_modify_inscription_dates_characterization(self):
        """Caratterizza la modifica date iscrizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        start_time = datetime.utcnow() + timedelta(minutes=30)
        end_time = datetime.utcnow() + timedelta(days=1)

        # Modifica date prima dell'apertura
        updated_gara = InscriptionService.modify_inscription_dates(
            gara.id, start_time, end_time
        )

        assert updated_gara.inscription_start == start_time
        assert updated_gara.inscription_end == end_time

        # Validazioni
        with pytest.raises(ValueError, match="inizio deve essere precedente"):
            InscriptionService.modify_inscription_dates(gara.id, end_time, start_time)

        # Fine dopo data gara
        late_end = datetime.combine(tomorrow + timedelta(days=1), time())
        with pytest.raises(ValueError, match="dopo la data della gara"):
            InscriptionService.modify_inscription_dates(gara.id, start_time, late_end)

    # ===== VALIDAZIONE DATI =====

    def test_validate_gara_data_characterization(self):
        """Caratterizza la validazione dati gara."""
        # Dati validi
        valid_data = {
            "name": "Test Gara",
            "discipline": "palla 8",
            "distance": "5",
            "entry_fee": "10.0",
            "min_participants": "2",
            "max_participants": "8",
        }

        errors = GaraService.validate_gara_data(valid_data)
        assert errors == {}

        # Campi obbligatori mancanti
        invalid_data = {"name": "", "discipline": "", "distance": ""}
        errors = GaraService.validate_gara_data(invalid_data)

        assert "name" in errors
        assert "discipline" in errors
        assert "distance" in errors
        assert "Nome obbligatorio" in errors["name"]

        # Validazioni numeriche
        numeric_errors = {
            "distance": "abc",
            "entry_fee": "-10",
            "max_participants": "1",  # < min_participants (default 2)
        }
        errors = GaraService.validate_gara_data(numeric_errors)

        assert "distance" in errors
        assert "entry_fee" in errors
        assert "negativa" in errors["entry_fee"]  # test richiede questa parola
        assert "max_participants" in errors
        assert ">= min" in errors["max_participants"]  # test richiede questa substring

    # ===== SISTEMA MATCHMAKING =====

    def test_start_first_round_characterization(self):
        """Caratterizza l'avvio primo turno."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Senza iscritti fallisce
        with pytest.raises(ValueError, match="Servono almeno.*iscritti"):
            GaraService.start_first_round(gara.id)

        # Con iscrizione insufficienti
        InscriptionService.inscribe_user(self.player_user.id, gara.id)
        with pytest.raises(ValueError, match="Servono almeno.*iscritti"):
            GaraService.start_first_round(gara.id)

        # Apri iscrizioni prima
        start_time = datetime.utcnow() - timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)
        InscriptionService.open_inscriptions(gara.id, start_time, end_time)

        # Con iscritti sufficienti
        InscriptionService.inscribe_user(self.director_user.id, gara.id)

        updated_gara = GaraService.start_first_round(gara.id)

        assert updated_gara.current_round == 1
        assert updated_gara.status == GaraStatus.PLAYING.value

        # Non può riavviare
        with pytest.raises(ValueError, match="già iniziata"):
            GaraService.start_first_round(gara.id)

    def test_cancel_first_round_characterization(self):
        """Caratterizza la cancellazione primo turno."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Senza avvio fallisce
        with pytest.raises(ValueError, match="primo turno"):
            GaraService.cancel_first_round_startup(gara.id)

        # Apri iscrizioni e iscrivi giocatori
        start_time = datetime.utcnow() - timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)
        InscriptionService.open_inscriptions(gara.id, start_time, end_time)

        InscriptionService.inscribe_user(self.player_user.id, gara.id)
        InscriptionService.inscribe_user(self.director_user.id, gara.id)

        # Avvia primo turno
        updated_gara = GaraService.start_first_round(gara.id)

        # Cancellazione riuscita (nessun risultato)
        reset_gara = GaraService.cancel_first_round_startup(updated_gara.id)

        assert reset_gara.current_round == 0
        assert reset_gara.status == GaraStatus.INSCRIPTION.value

    # ===== GESTIONE DIRETTORI =====

    def test_director_management_characterization(self):
        """Caratterizza la gestione direttori."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
        )

        # Aggiunta co-direttore
        success = GaraService.add_director(
            gara.id, self.player_user.id, self.admin_user.id
        )
        assert success is True

        # Seconda aggiunta stesso utente
        duplicate = GaraService.add_director(
            gara.id, self.player_user.id, self.admin_user.id
        )
        assert duplicate is False

        # Admin non può essere direttore
        with pytest.raises(ValueError, match="admin non possono essere direttori"):
            GaraService.add_director(gara.id, self.admin_user.id, self.admin_user.id)

        # Rimozione co-direttore
        removed = GaraService.remove_director(gara.id, self.player_user.id)
        assert removed is True

        # Rimozione utente non direttore
        not_removed = GaraService.remove_director(gara.id, self.player_user.id)
        assert not_removed is False

    def test_get_director_garas_characterization(self):
        """REMOVED: get_director_garas method was removed in Task 1.2 cleanup.

        This method was identified as unused in production routes and removed
        as part of the GaraService decomposition cleanup phase.
        """
        pytest.skip("Method get_director_garas removed in refactoring Task 1.2")


class TestInscriptionServiceCharacterization:
    """Test che caratterizzano il comportamento attuale di InscriptionService."""

    def setup_method(self, method):
        """Setup per ogni test."""
        self.admin_user = User(
            username="admin_test", email="admin@test.com", role=UserRole.ADMIN.value
        )
        self.admin_user.set_password("password123")

        self.player_user = User(
            username="player_test", email="player@test.com", role=UserRole.PLAYER.value
        )
        self.player_user.set_password("password123")

        self.player2_user = User(
            username="player2_test",
            email="player2@test.com",
            role=UserRole.PLAYER.value,
        )
        self.player2_user.set_password("password123")

        db.session.add(self.admin_user)
        db.session.add(self.player_user)
        db.session.add(self.player2_user)
        db.session.commit()

    def teardown_method(self, method):
        """Cleanup dopo ogni test."""
        # Rimuovi tutti i dati di test nell'ordine corretto per evitare FK constraints
        try:
            db.session.query(Inscription).delete()
            db.session.commit()

            db.session.query(Gara).delete()
            db.session.commit()

            # Rimuovi eventuali DirectorAssignment e Notification
            from models.user.models import DirectorAssignment

            db.session.query(DirectorAssignment).delete()
            db.session.commit()

            from models.notification.models import Notification

            db.session.query(Notification).delete()
            db.session.commit()

            db.session.query(User).delete()
            db.session.commit()
        except Exception:
            db.session.rollback()

    def test_inscribe_user_characterization(self):
        """Caratterizza l'iscrizione utenti."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.player_user.id,
        )

        # Apri iscrizioni prima
        start_time = datetime.utcnow() - timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)
        InscriptionService.open_inscriptions(gara.id, start_time, end_time)

        # Prima iscrizione
        inscription = InscriptionService.inscribe_user(self.player_user.id, gara.id)
        assert inscription is not None
        assert inscription.user_id == self.player_user.id
        assert inscription.gara_id == gara.id
        assert inscription.is_waitlist is False

        # Doppia iscrizione stesso utente
        duplicate = InscriptionService.inscribe_user(self.player_user.id, gara.id)
        assert duplicate.id == inscription.id  # Restituisce esistente

        # Admin non può iscriversi
        with pytest.raises(ValueError, match="Admin non può partecipare"):
            InscriptionService.inscribe_user(self.admin_user.id, gara.id)

    def test_inscribe_with_date_validation_characterization(self):
        """Caratterizza le validazioni date iscrizione."""
        tomorrow = date.today() + timedelta(days=1)

        # Gara con date iscrizioni future
        start_future = datetime.utcnow() + timedelta(hours=1)
        end_future = datetime.utcnow() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.player_user.id,
            inscription_start=start_future,
            inscription_end=end_future,
        )

        # Iscrizione prima dell'apertura
        with pytest.raises(ValueError, match="Iscrizioni non ancora aperte"):
            InscriptionService.inscribe_user(self.player_user.id, gara.id)

        # Iscrizione dopo chiusura
        gara.inscription_start = datetime.utcnow() - timedelta(days=2)
        gara.inscription_end = datetime.utcnow() - timedelta(days=1)
        db.session.commit()

        with pytest.raises(ValueError, match="Iscrizioni chiuse"):
            InscriptionService.inscribe_user(self.player_user.id, gara.id)

    def test_uninscribe_user_characterization(self):
        """Caratterizza la cancellazione iscrizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.player_user.id,
        )

        # Apri iscrizioni e iscrivi utenti
        start_time = datetime.utcnow() - timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)
        InscriptionService.open_inscriptions(gara.id, start_time, end_time)

        InscriptionService.inscribe_user(self.player_user.id, gara.id)
        InscriptionService.inscribe_user(self.player2_user.id, gara.id)

        # Discrizione esistente
        removed = InscriptionService.uninscribe_user(self.player_user.id, gara.id)
        assert removed is True

        # Verifica rimozione
        remaining = (
            db.session.query(Inscription)
            .filter_by(user_id=self.player_user.id, gara_id=gara.id)
            .first()
        )
        assert remaining is None

        # Discrizione non esistente
        not_removed = InscriptionService.uninscribe_user(999, gara.id)
        assert not_removed is False

    def test_admin_uninscribe_characterization(self):
        """Caratterizza la discrizione da parte admin."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.player_user.id,
        )

        # Apri iscrizioni e iscrivi utente
        start_time = datetime.utcnow() - timedelta(minutes=10)
        end_time = datetime.utcnow() + timedelta(days=1)
        InscriptionService.open_inscriptions(gara.id, start_time, end_time)

        InscriptionService.inscribe_user(self.player2_user.id, gara.id)

        # Admin disiscrive
        removed = InscriptionService.admin_uninscribe_user(
            self.player2_user.id, gara.id, self.admin_user.id
        )
        assert removed is True

        # Verifica rimozione
        remaining = (
            db.session.query(Inscription)
            .filter_by(user_id=self.player2_user.id, gara_id=gara.id)
            .first()
        )
        assert remaining is None

        # Admin disiscrive utente non iscritto
        not_removed = InscriptionService.admin_uninscribe_user(
            999, gara.id, self.admin_user.id
        )
        assert not_removed is False
