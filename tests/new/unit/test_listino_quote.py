"""Il listino delle quote per categoria (ADR-079).

Il listino è **solo informazione**: «Serie A 30 € · B e C 20 € · Amatori 15 €».
Le voci sono categorie della competizione — del campionato, condivise da tutte
le sue serate, oppure della gara singola — con una quota accanto. Scrivere una
voce crea la categoria; toglierla dal listino non la cancella, perché può
essere già assegnata a qualcuno.

Due proprietà da non perdere:

- senza listino la gara mostra la quota unica di sempre (`gara.entry_fee`);
- una categoria usata **senza handicap** non tocca l'ELO (ADR-049): il
  listino non deve far cambiare comportamento a nessuna partita.
"""

from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from models import Campionato, Categoria, Gara, Inscription, Match, User
from models.categoria.listino import (
    ListinoService,
    VoceListino,
    gruppi,
    leggi_dal_modulo,
    listino_di,
)
from models.exceptions import NotFoundError, ValidationError
from models.rating.eligibility import RatingEligibility
from models.storia.etichette import etichetta, valore
from models.storia.models import SettingsChange
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _gara(db_session, suffix, *, campionato=None, has_handicap=False):
    gara = Gara(
        campionato_id=campionato.id if campionato else None,
        number=1,
        name=f"Gara listino {suffix}",
        date=date.today() + timedelta(days=7),
        discipline="palla_8",
        distance=3,
        rounds_count=3,
        matchmaking_strategy="round_robin",
        has_handicap=has_handicap,
        entry_fee=10.0,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _campionato(db_session, nome="Lunedì al 74"):
    camp = Campionato(name=nome)
    db_session.add(camp)
    db_session.flush()
    return camp


def _voci(*coppie):
    return [VoceListino(nome=n, quota=q) for n, q in coppie]


LOCANDINA = (("Serie A", 30), ("Serie B", 20), ("Serie C", 20), ("Amatori", 15))


class TestLaColonna:
    def test_la_quota_della_categoria_e_facoltativa(self, db_session):
        gara = _gara(db_session, "col")
        categoria = Categoria(name="B", gara_id=gara.id)
        db_session.add(categoria)
        db_session.flush()
        assert categoria.entry_fee is None


class TestSalvareIlListino:
    def test_sulla_gara_singola_le_voci_diventano_categorie_della_gara(
        self, db_session
    ):
        gara = _gara(db_session, "singola")
        ListinoService.salva(gara_id=gara.id, voci=_voci(*LOCANDINA))

        categorie = Categoria.query.filter_by(gara_id=gara.id).all()
        assert {c.name: c.entry_fee for c in categorie} == {
            "Serie A": 30,
            "Serie B": 20,
            "Serie C": 20,
            "Amatori": 15,
        }
        assert all(c.campionato_id is None for c in categorie)

    def test_nel_campionato_valgono_per_tutte_le_serate(self, db_session):
        camp = _campionato(db_session)
        lunedi1 = _gara(db_session, "l1", campionato=camp)
        lunedi2 = _gara(db_session, "l2", campionato=camp)
        ListinoService.salva(campionato_id=camp.id, voci=_voci(*LOCANDINA))

        assert Categoria.query.filter_by(campionato_id=camp.id).count() == 4
        assert [c.name for c in listino_di(lunedi1)] == [
            c.name for c in listino_di(lunedi2)
        ]
        assert [c.name for c in listino_di(camp)] == [
            c.name for c in listino_di(lunedi1)
        ]

    def test_ordine_dalla_quota_piu_alta_poi_alfabetico(self, db_session):
        """Stabile e leggibile: chi paga di più in cima, a parità l'alfabeto."""
        gara = _gara(db_session, "ordine")
        ListinoService.salva(
            gara_id=gara.id,
            voci=_voci(
                ("Amatori", 15), ("Serie C", 20), ("Serie A", 30), ("Serie B", 20)
            ),
        )
        assert [c.name for c in listino_di(gara)] == [
            "Serie A",
            "Serie B",
            "Serie C",
            "Amatori",
        ]

    def test_le_quote_uguali_si_raggruppano(self, db_session):
        gara = _gara(db_session, "gruppi")
        ListinoService.salva(gara_id=gara.id, voci=_voci(*LOCANDINA))
        assert [(g.quota, list(g.nomi)) for g in gruppi(listino_di(gara))] == [
            (30, ["Serie A"]),
            (20, ["Serie B", "Serie C"]),
            (15, ["Amatori"]),
        ]

    def test_una_categoria_gia_esistente_si_ritrova_per_nome(self, db_session):
        """La «B» scritta accanto a un iscritto è la stessa «b» del listino."""
        gara = _gara(db_session, "esistente")
        b = Categoria(name="B", gara_id=gara.id)
        db_session.add(b)
        db_session.flush()

        ListinoService.salva(gara_id=gara.id, voci=_voci((" b ", 20)))

        assert Categoria.query.filter_by(gara_id=gara.id).count() == 1
        assert db_session.get(Categoria, b.id).entry_fee == 20

    def test_rinominare_una_voce_per_id(self, db_session):
        gara = _gara(db_session, "rinomina")
        ListinoService.salva(gara_id=gara.id, voci=_voci(("Serie B", 20)))
        b = Categoria.query.filter_by(gara_id=gara.id).one()

        ListinoService.salva(
            gara_id=gara.id,
            voci=[VoceListino(nome="Serie B-C", quota=18, categoria_id=b.id)],
        )
        b = db_session.get(Categoria, b.id)
        assert (b.name, b.entry_fee) == ("Serie B-C", 18)
        assert Categoria.query.filter_by(gara_id=gara.id).count() == 1

    def test_togliere_una_voce_non_cancella_la_categoria(self, db_session):
        """Può essere già assegnata: esce dal listino e resta dov'è."""
        gara = _gara(db_session, "togli")
        ListinoService.salva(gara_id=gara.id, voci=_voci(*LOCANDINA))
        ListinoService.salva(gara_id=gara.id, voci=_voci(("Serie A", 30)))

        assert [c.name for c in listino_di(gara)] == ["Serie A"]
        assert Categoria.query.filter_by(gara_id=gara.id).count() == 4
        amatori = Categoria.query.filter_by(gara_id=gara.id, name="Amatori").one()
        assert amatori.entry_fee is None

    def test_la_voce_senza_quota_crea_la_categoria_fuori_listino(self, db_session):
        gara = _gara(db_session, "senzaquota")
        ListinoService.salva(gara_id=gara.id, voci=_voci(("Ospiti", None)))
        assert Categoria.query.filter_by(gara_id=gara.id, name="Ospiti").count() == 1
        assert listino_di(gara) == []

    def test_una_categoria_disattivata_torna_attiva_se_la_si_rimette(self, db_session):
        gara = _gara(db_session, "riattiva")
        b = Categoria(name="B", gara_id=gara.id, is_active=False)
        db_session.add(b)
        db_session.flush()
        ListinoService.salva(gara_id=gara.id, voci=_voci(("B", 20)))
        assert db_session.get(Categoria, b.id).is_active is True

    def test_la_quota_negativa_e_rifiutata(self, db_session):
        gara = _gara(db_session, "negativa")
        with pytest.raises(ValidationError):
            ListinoService.salva(gara_id=gara.id, voci=_voci(("A", -5)))

    def test_due_voci_con_lo_stesso_nome_sono_rifiutate(self, db_session):
        gara = _gara(db_session, "doppia")
        with pytest.raises(ValidationError):
            ListinoService.salva(gara_id=gara.id, voci=_voci(("B", 20), (" b", 25)))

    def test_l_id_di_un_altra_competizione_e_rifiutato(self, db_session):
        mia = _gara(db_session, "mia")
        altrui = _gara(db_session, "altrui")
        ListinoService.salva(gara_id=altrui.id, voci=_voci(("A", 30)))
        estranea = Categoria.query.filter_by(gara_id=altrui.id).one()
        with pytest.raises(NotFoundError):
            ListinoService.salva(
                gara_id=mia.id,
                voci=[VoceListino(nome="A", quota=1, categoria_id=estranea.id)],
            )


class TestStoriaDelleModifiche:
    def test_il_cambio_di_quota_resta_nella_storia_della_gara(self, db_session):
        gara = _gara(db_session, "storia")
        ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 30)))
        ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 25)))

        voci = SettingsChange.query.filter_by(gara_id=gara.id).all()
        righe = [r for v in voci for r in v.fields if r.field == "listino"]
        assert righe, "il cambio di quota deve restare scritto"
        ultima = righe[-1]
        assert valore("listino", ultima.old_value) == "A 30 €"
        assert valore("listino", ultima.new_value) == "A 25 €"
        assert etichetta("listino") != "listino"

    def test_nella_storia_del_campionato_se_il_listino_e_suo(self, db_session):
        camp = _campionato(db_session, "Camp storia listino")
        ListinoService.salva(campionato_id=camp.id, voci=_voci(("A", 30)))
        assert SettingsChange.query.filter_by(campionato_id=camp.id).count() == 1

    def test_salvare_lo_stesso_listino_non_scrive_niente(self, db_session):
        gara = _gara(db_session, "invariato")
        ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 30)))
        prima = SettingsChange.query.filter_by(gara_id=gara.id).count()
        cambiato = ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 30.0)))
        assert cambiato is False
        assert SettingsChange.query.filter_by(gara_id=gara.id).count() == prima

    def test_alla_creazione_non_si_scrive_la_storia(self, db_session):
        gara = _gara(db_session, "creazione")
        ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 30)), nella_storia=False)
        assert SettingsChange.query.filter_by(gara_id=gara.id).count() == 0

    def test_la_quota_di_una_voce_cambiata_dal_foglio_delle_categorie(self, db_session):
        gara = _gara(db_session, "foglio")
        ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 30)))
        a = Categoria.query.filter_by(gara_id=gara.id).one()
        ListinoService.imposta_quota(a.id, 35)
        assert db_session.get(Categoria, a.id).entry_fee == 35
        assert SettingsChange.query.filter_by(gara_id=gara.id).count() == 2


class TestLetturaDelModulo:
    def test_senza_il_marcatore_il_modulo_non_porta_il_listino(self):
        """Un modulo che non mostra l'editor non deve svuotare il listino."""
        assert leggi_dal_modulo(MultiDict({"name": "x"})) is None

    def test_righe_vuote_saltate_e_virgola_decimale(self):
        form = MultiDict(
            [
                ("listino_presente", "1"),
                ("listino_id", ""),
                ("listino_nome", "Serie A"),
                ("listino_quota", "30"),
                ("listino_id", "7"),
                ("listino_nome", "Amatori"),
                ("listino_quota", "12,5"),
                ("listino_id", ""),
                ("listino_nome", "  "),
                ("listino_quota", ""),
            ]
        )
        assert leggi_dal_modulo(form) == [
            VoceListino(nome="Serie A", quota=30.0, categoria_id=None),
            VoceListino(nome="Amatori", quota=12.5, categoria_id=7),
        ]

    def test_una_quota_che_non_e_un_numero_e_rifiutata(self):
        form = MultiDict(
            [
                ("listino_presente", "1"),
                ("listino_id", ""),
                ("listino_nome", "A"),
                ("listino_quota", "trenta"),
            ]
        )
        with pytest.raises(ValidationError):
            leggi_dal_modulo(form)

    def test_il_listino_svuotato_e_una_lista_vuota(self):
        assert leggi_dal_modulo(MultiDict({"listino_presente": "1"})) == []


class TestCategorieSenzaHandicap:
    def test_il_listino_accende_le_categorie_anche_senza_handicap(self, db_session):
        gara = _gara(db_session, "accende")
        assert gara.usa_categorie is False
        ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 30)))
        assert gara.usa_categorie is True

    def test_con_handicap_le_categorie_ci_sono_comunque(self, db_session):
        gara = _gara(db_session, "hcp", has_handicap=True)
        assert gara.usa_categorie is True

    def test_categorie_diverse_senza_handicap_non_toccano_l_elo(self, db_session):
        """ADR-049: la categoria pesa sull'ELO solo con l'handicap attivo."""
        gara = _gara(db_session, "elo")
        ListinoService.salva(gara_id=gara.id, voci=_voci(("A", 30), ("C", 15)))
        a = Categoria.query.filter_by(gara_id=gara.id, name="A").one()
        c = Categoria.query.filter_by(gara_id=gara.id, name="C").one()

        giocatori = []
        for i, categoria in enumerate((a, c)):
            u = User(
                username=f"lst_elo_{i}",
                email=f"lst_elo_{i}@example.com",
                role=UserRole.PLAYER.value,
            )
            u.set_password("pw")
            db_session.add(u)
            db_session.flush()
            db_session.add(
                Inscription(gara_id=gara.id, user_id=u.id, categoria_id=categoria.id)
            )
            giocatori.append(u)
        partita = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
        )
        db_session.add(partita)
        db_session.flush()

        # Le regole fissate restano quelle di una gara senza handicap.
        assert partita.has_handicap is False
        assert RatingEligibility.exclusion_reason(partita, is_walkover=False) is None


class TestVetrina:
    def test_la_vetrina_mostra_il_listino_al_posto_della_quota(self, app, db_session):
        from models.competition.showcase_view import costruisci_vetrina

        gara = _gara(db_session, "vetrina")
        with app.test_request_context():
            prima = {r.etichetta: r.valore for r in costruisci_vetrina(gara).righe}
            assert prima.get("Quota") == "10 €"

            ListinoService.salva(gara_id=gara.id, voci=_voci(*LOCANDINA))
            dopo = {r.etichetta: r.valore for r in costruisci_vetrina(gara).righe}
        assert "Quota" not in dopo
        assert dopo["Quote"] == "Serie A 30 € · Serie B, Serie C 20 € · Amatori 15 €"
