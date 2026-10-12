"""Cosa entra in un preset, e come se ne esce (ADR-082).

Il preset contiene **solo la configurazione**: la whitelist è positiva e sta
qui, in un posto solo. Per la gara è derivata dai campi del suo modulo
(`GaraFormParser.CAMPI_DEL_MODULO`), meno quelli che dicono *quale* gara e
non *come* si gioca: nome, date, sala, tavoli, note, peso nel campionato. Per
il campionato da `CampionatoFormParser.CAMPI_DEL_MODULO`, meno nome e sala.
Iscritti, token e link pubblici non sono campi del modulo, quindi non ci
arrivano nemmeno.

Il payload si scrive con i nomi delle colonne della gara, non con quelli dei
campi HTML: i primi cambiano molto più di rado. Chi applica il preset traduce
in valori del modulo (`valori_per_il_modulo`), e al salvataggio della gara il
modulo passa dal parser di sempre: un preset non scavalca nessun controllo.

**I playoff** (dal 2026-10-12, decisione dell'utente): il preset di campionato
porta anche le configurazioni dei playoff, come elenco (zero, una o più),
con una whitelist positiva sua (`CAMPI_DEL_PLAYOFF`): criteri di
qualificazione, modalità di classifica finale, peso, formula e regole della
finale. Restano fuori tutto ciò che dice *quale* finale e a che punto è:
id, campionato, gara creata, stato, date, sala, qualificati e inviti.

**Robustezza nel tempo.** Ogni preset porta lo `schema_version` con cui è
stato scritto, e si legge con tolleranza (`leggi`): un campo che la whitelist
di oggi non conosce più si scarta e si segnala, un campo che manca resta al
valore che il modulo propone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from models.preset.models import TipoPreset

#: La forma del payload scritta oggi. Si alza quando un campo cambia
#: significato (non quando se ne aggiunge uno: quello lo copre la lettura
#: tollerante), e `leggi` impara a convertire dalla versione precedente.
#:
#: 2 (2026-10-12): il preset di campionato porta anche i playoff (``playoff``).
#: Un preset della versione 1 non li aveva: si legge come «nessuna
#: configurazione», non come un errore.
SCHEMA_VERSION = 2

#: I campi del modulo della gara che non entrano mai in un preset: dicono
#: quale serata è, non come si gioca. Il peso vale dentro *quel* campionato.
ESCLUSI_DALLA_GARA = frozenset(
    {
        "name",
        "location",
        "date",
        "time",
        "available_tables",
        "description",
        "weight",
    }
)

#: I campi del modulo del campionato che non entrano mai in un preset: il
#: nome, e la sede, che dice dove si gioca e non come.
ESCLUSI_DAL_CAMPIONATO = frozenset({"name", "default_venue_id"})

#: Le tre catene del campionato: in colonna JSON, nell'editor separate da
#: virgole (`_catena_per_l_editor`), come quelle della gara.
CATENE_DEL_CAMPIONATO = (
    "default_catena_turno",
    "default_catena_gara",
    "catena_generale",
)

#: Il livello dell'editor di ciascuna catena del campionato.
_LIVELLO_DELLA_CATENA = {
    "default_catena_turno": "turno",
    "default_catena_gara": "gara",
    "catena_generale": "campionato",
}

#: Il listino viaggia accanto ai campi: all'uso crea le categorie della gara.
LISTINO = "listino"

#: Le configurazioni dei playoff viaggiano accanto ai campi del campionato.
PLAYOFF = "playoff"

#: I campi di `PlayoffConfiguration` che sono **configurazione**: whitelist
#: positiva, nell'ordine in cui si leggono. Fuori, per scelta: id, campionato,
#: gara creata, stato (`is_active`), date (`scheduled_date`,
#: `response_deadline`), sala (`location`, come per gara e campionato), il
#: tipo storico e i criteri JSON di una volta (`playoff_type`,
#: `qualification_criteria`, `auto_generate`: nessun modulo li sceglie), e
#: qualificati e inviti, che non sono colonne.
CAMPI_DEL_PLAYOFF = (
    "name",
    "description",
    # Chi si qualifica (`CRITERI_DI_QUALIFICAZIONE`).
    "positions_from",
    "positions_to",
    "max_participants",
    "min_garas_played",
    # Come entra nella classifica finale.
    "final_ranking_mode",
    "playoff_weight",
    # Come si gioca la finale.
    "discipline",
    "distance",
    "rounds_count",
    "strategy_type",
    "odd_number_policy",
    "classification_system",
    "entry_fee",
)

#: I campi interi di una configurazione dei playoff.
_INTERI_DEL_PLAYOFF = frozenset(
    {
        "positions_from",
        "positions_to",
        "max_participants",
        "min_garas_played",
        "playoff_weight",
        "distance",
        "rounds_count",
    }
)

#: Quante configurazioni dei playoff il wizard sa esprimere: Elite e Academy.
POSTI_DEL_WIZARD = 2

#: I campi che dentro un campionato valgono «come il campionato» quando sono
#: NULL, con la colonna del campionato da cui si leggono. Nel preset si
#: scrivono espliciti: applicato altrove, deve dire cosa si giocava davvero.
_EREDITATI_DAL_CAMPIONATO = {
    "has_handicap": "has_handicap",
    "start_rule": "default_start_rule",
    "break_rule": "default_break_rule",
    "time_limit_minutes": "default_time_limit_minutes",
    "max_groups": "default_max_groups",
    "group_seeding": "default_group_seeding",
    "final_phase_mode": "default_final_phase_mode",
    "qualifiers_per_group": "default_qualifiers_per_group",
}


def campi_ammessi(kind: str) -> Tuple[str, ...]:
    """La whitelist di un tipo di preset, nell'ordine del modulo.

    L'ordine conta per chi la applica: la strategia prima dei gironi, il
    sistema di classifica prima dei punti e delle catene.
    """
    if kind == TipoPreset.GARA.value:
        from routes.admin.competition.form_parser import GaraFormParser

        return tuple(
            campo
            for campo in GaraFormParser.CAMPI_DEL_MODULO
            if campo not in ESCLUSI_DALLA_GARA
        )
    if kind == TipoPreset.CAMPIONATO.value:
        from routes.admin.campionato_form_parser import CampionatoFormParser

        return tuple(
            campo
            for campo in CampionatoFormParser.CAMPI_DEL_MODULO
            if campo not in ESCLUSI_DAL_CAMPIONATO
        )
    return ()


def _semplice(valore: Any) -> Any:
    """Un valore che il JSON sa scrivere: gli enum diventano il loro valore."""
    if isinstance(valore, Enum):
        return valore.value
    if valore is None or isinstance(valore, (bool, int, float, str)):
        return valore
    return str(valore)


def _voce_di_listino(voce: Any) -> Optional[Dict[str, Any]]:
    """Una riga del listino come la tiene il preset: nome e quota, senza id.

    Gli id delle categorie appartengono alla gara da cui si è salvato: nel
    preset non vogliono dire niente.
    """
    if isinstance(voce, Mapping):
        nome, quota = voce.get("nome"), voce.get("quota")
    else:
        nome, quota = getattr(voce, "nome", None), getattr(voce, "quota", None)
    nome = str(nome or "").strip()[:50]
    if not nome:
        return None
    try:
        quota = None if quota in (None, "") else round(float(quota), 2)
    except (TypeError, ValueError):
        quota = None
    if quota is not None and quota < 0:
        quota = None
    return {"nome": nome, "quota": quota}


def _configurazione_del_playoff(voce: Any) -> Optional[Dict[str, Any]]:
    """Una configurazione dei playoff come la tiene il preset: solo i campi
    della whitelist, coi numeri come numeri. None se non è leggibile."""
    if not isinstance(voce, Mapping):
        return None
    esito: Dict[str, Any] = {}
    for campo in CAMPI_DEL_PLAYOFF:
        if campo not in voce:
            continue
        valore = _semplice(voce[campo])
        if valore is not None and campo in _INTERI_DEL_PLAYOFF:
            try:
                valore = int(valore)
            except (TypeError, ValueError):
                continue
        elif valore is not None and campo == "entry_fee":
            try:
                valore = round(float(valore), 2)
            except (TypeError, ValueError):
                continue
        esito[campo] = valore
    return esito


def componi(
    kind: str,
    campi: Mapping[str, Any],
    listino: Optional[Iterable[Any]] = None,
    playoff: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Il payload da salvare: solo i campi della whitelist, il listino e, per
    il campionato, i playoff.

    Tutto ciò che non è ammesso resta fuori in silenzio: chi compone parte da
    un modulo intero, e nome o data in un preset non devono entrare mai.
    Il preset di campionato scrive **sempre** l'elenco dei playoff, anche
    vuoto: dice che il campionato non ne aveva.
    """
    ammessi = set(campi_ammessi(kind))
    dati: Dict[str, Any] = {
        "campi": {
            campo: _semplice(valore)
            for campo, valore in campi.items()
            if campo in ammessi
        }
    }
    voci = [v for v in (_voce_di_listino(x) for x in (listino or [])) if v]
    if voci:
        dati[LISTINO] = voci
    if kind == TipoPreset.CAMPIONATO.value:
        dati[PLAYOFF] = [
            c
            for c in (_configurazione_del_playoff(x) for x in (playoff or []))
            if c is not None
        ]
    return dati


def esplicita(campi: Dict[str, Any], campionato: Any) -> Dict[str, Any]:
    """Al posto di «come il campionato», il valore che il campionato dava.

    Un preset salvato dentro un campionato e applicato a una gara singola, o a
    un altro campionato, deve dire cosa si giocava, non da dove arrivava.
    Fuori da un campionato l'handicap NULL vale «no».
    """
    esito = dict(campi)
    for campo, colonna in _EREDITATI_DAL_CAMPIONATO.items():
        if campo not in esito or esito[campo] is not None:
            continue
        if campionato is not None and getattr(campionato, colonna, None) is not None:
            esito[campo] = _semplice(getattr(campionato, colonna))
        elif campo == "has_handicap":
            esito[campo] = False
    if esito.get("has_handicap") is not None:
        esito["has_handicap"] = bool(esito["has_handicap"])
    return esito


def dalla_gara(gara: Any) -> Dict[str, Any]:
    """I campi del preset letti da una gara che esiste già.

    Le catene sono quelle che valgono (anche quando la gara non ne ha una
    sua), come le mostra il modulo di modifica.
    """
    from routes.admin.competition.form_parser import GaraFormParser

    campi: Dict[str, Any] = {}
    for campo in campi_ammessi(TipoPreset.GARA.value):
        if campo in ("catena_turno", "catena_gara"):
            campi[campo] = GaraFormParser._catena_mostrata(gara, campo)
        else:
            campi[campo] = _semplice(getattr(gara, campo, None))
    return esplicita(campi, getattr(gara, "campionato", None))


def listino_della_gara(gara: Any) -> List[Dict[str, Any]]:
    """Il listino di una gara singola, come lo tiene il preset.

    Dentro un campionato il listino è del campionato, non della gara: un
    preset di gara non se lo porta via.
    """
    if getattr(gara, "campionato_id", None):
        return []
    from models.categoria.listino import listino_di

    voci = (
        _voce_di_listino({"nome": c.name, "quota": c.entry_fee})
        for c in listino_di(gara)
    )
    return [v for v in voci if v]


def dal_campionato(campionato: Any) -> Dict[str, Any]:
    """I campi del preset letti da un campionato che esiste già.

    Le catene sono quelle che valgono, anche quando il campionato non ne ha
    scelta una: le stesse che mostra il modulo di modifica.
    """
    import json

    from models.classification.editor_catena import editor_del_campionato

    campi: Dict[str, Any] = {}
    for campo in campi_ammessi(TipoPreset.CAMPIONATO.value):
        if campo in CATENE_DEL_CAMPIONATO:
            voci = editor_del_campionato(_LIVELLO_DELLA_CATENA[campo], campionato)
            campi[campo] = json.dumps(voci["voci"])
        else:
            campi[campo] = _semplice(getattr(campionato, campo, None))
    return campi


def playoff_del_campionato(campionato: Any) -> List[Dict[str, Any]]:
    """Le configurazioni dei playoff attive di un campionato, come le tiene il
    preset: nell'ordine dei posti in classifica, poi di creazione."""
    from models.playoff.models import PlayoffConfiguration

    configurazioni = (
        PlayoffConfiguration.query.filter_by(
            campionato_id=campionato.id, is_active=True
        )
        .order_by(
            PlayoffConfiguration.positions_from.is_(None),
            PlayoffConfiguration.positions_from,
            PlayoffConfiguration.id,
        )
        .all()
    )
    esito = []
    for config in configurazioni:
        voce = _configurazione_del_playoff(
            {campo: getattr(config, campo, None) for campo in CAMPI_DEL_PLAYOFF}
        )
        if voce is not None:
            esito.append(voce)
    return esito


def listino_del_campionato(campionato: Any) -> List[Dict[str, Any]]:
    """Il listino di un campionato, come lo tiene il preset."""
    from models.categoria.listino import listino_di

    voci = (
        _voce_di_listino({"nome": c.name, "quota": c.entry_fee})
        for c in listino_di(campionato)
    )
    return [v for v in voci if v]


@dataclass
class Lettura:
    """Cosa resta di un preset letto oggi: campi, listino, e cosa si è perso."""

    campi: Dict[str, Any] = field(default_factory=dict)
    listino: List[Dict[str, Any]] = field(default_factory=list)
    #: I campi che la whitelist di oggi non conosce più: la pagina li dice.
    scartati: List[str] = field(default_factory=list)
    #: Le configurazioni dei playoff (solo campionato): vuoto = nessuna.
    playoff: List[Dict[str, Any]] = field(default_factory=list)


def leggi(kind: str, dati: Mapping[str, Any], schema_version: int = 1) -> Lettura:
    """Il preset come lo capisce l'app di oggi, con tolleranza.

    Un campo sconosciuto, o non più ammesso, si scarta e finisce in
    ``scartati``. Un campo che manca non si inventa: resta al valore che il
    modulo propone. ``schema_version`` dice da che forma si parte: un preset
    di campionato della versione 1 non aveva i playoff, e si legge come
    «nessuna configurazione» (lo stesso vale per un elenco illeggibile).
    """
    ammessi = campi_ammessi(kind)
    grezzi = dati.get("campi") if isinstance(dati, Mapping) else None
    if not isinstance(grezzi, Mapping):
        grezzi = {}
    lettura = Lettura()
    for campo in ammessi:
        if campo in grezzi:
            lettura.campi[campo] = _semplice(grezzi[campo])
    lettura.scartati = sorted(c for c in grezzi if c not in ammessi)
    voci = dati.get(LISTINO) if isinstance(dati, Mapping) else None
    if isinstance(voci, list):
        lettura.listino = [v for v in (_voce_di_listino(x) for x in voci) if v]
    if kind == TipoPreset.CAMPIONATO.value and schema_version >= 2:
        grezzi_playoff = dati.get(PLAYOFF) if isinstance(dati, Mapping) else None
        if isinstance(grezzi_playoff, list):
            sconosciuti = set()
            for voce in grezzi_playoff:
                config = _configurazione_del_playoff(voce)
                if config is None:
                    continue
                lettura.playoff.append(config)
                sconosciuti.update(c for c in voce if c not in CAMPI_DEL_PLAYOFF)
            lettura.scartati += sorted(f"{PLAYOFF}.{c}" for c in sconosciuti)
    return lettura


def valori_dei_playoff(playoff: List[Mapping[str, Any]]) -> List[Tuple[str, Any]]:
    """I playoff del preset nei campi del passo 1 del wizard: Elite e Academy.

    Il wizard ne sa esprimere due, una dopo l'altra in classifica: la prima
    configurazione del preset va su Elite, la seconda su Academy. Le altre il
    passo 1 non le crea (lo dice `nota_dei_playoff`). Il numero di posti è
    quello della configurazione; tutto il resto (criteri, peso, formula…) il
    passo 2 lo rilegge dal preset scelto (`configurazioni_dal_wizard`).
    """
    coppie: List[Tuple[str, Any]] = []
    for indice, slot in enumerate(("elite", "academy")):
        config = playoff[indice] if indice < len(playoff) else None
        coppie.append((f"playoff_{slot}_enabled", config is not None))
        if config is not None and config.get("max_participants"):
            coppie.append(
                (f"playoff_{slot}_participants", int(config["max_participants"]))
            )
    return coppie


def nome_predefinito_del_playoff(indice: int) -> str:
    """Il nome che il wizard dà alla configurazione al posto ``indice``."""
    from flask_babel import gettext as _

    return _("Playoff Elite") if indice == 0 else _("Playoff Academy")


def configurazioni_dal_wizard(passo_1: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Le configurazioni dei playoff che il wizard crea, dal passo 1.

    Accese e posti vengono dai campi del passo 1, come sempre: Elite dal
    primo posto, Academy subito dopo. Se il passo 1 è partito da un preset
    (``playoff_dal_preset``), la configurazione dello stesso posto porta con
    sé nome, criteri, peso e regole della finale; posti e posizioni restano
    quelli che il direttore ha lasciato nel modulo. Le configurazioni del
    preset oltre la seconda non si creano: il wizard non le sa mostrare.

    Una funzione sola per la creazione (`wizard_create`) e per «Salva come
    preset» dal passo 2: il preset tiene ciò che il campionato riceverebbe.
    """
    dal_preset = [
        c
        for c in (
            _configurazione_del_playoff(x)
            for x in (passo_1.get("playoff_dal_preset") or [])
        )
        if c is not None
    ]
    esito: List[Dict[str, Any]] = []
    prossimo = 1
    for indice, slot in enumerate(("elite", "academy")):
        if not passo_1.get(f"playoff_{slot}_enabled"):
            # Academy esiste solo dopo Elite: senza Elite non c'è il posto.
            break
        posti = int(passo_1.get(f"playoff_{slot}_participants") or 6)
        config: Dict[str, Any] = {}
        if indice < len(dal_preset):
            config.update(dal_preset[indice])
        config["name"] = config.get("name") or nome_predefinito_del_playoff(indice)
        config["max_participants"] = posti
        config["positions_from"] = prossimo
        config["positions_to"] = prossimo + posti - 1
        prossimo += posti
        esito.append(config)
    return esito


def valori_per_il_modulo(
    campi: Mapping[str, Any], kind: str = TipoPreset.GARA.value
) -> List[Tuple[str, Any]]:
    """I campi del preset tradotti nei campi HTML del modulo.

    Coppie (nome del campo, valore), nell'ordine della whitelist. Dove il
    modulo chiede una cosa con due campi (il menu «come i gironi / senza
    limite / un limite diverso» più i minuti) le coppie sono due. Le caselle
    ricevono un booleano; il resto una stringa o un numero, vuoto per NULL.
    """
    if kind == TipoPreset.CAMPIONATO.value:
        return _valori_del_campionato(campi)
    coppie: List[Tuple[str, Any]] = []
    for campo, valore in campi.items():
        if _regola_della_fase(coppie, campo, valore):
            continue
        if campo == "is_race_to":
            coppie.append(("exact_number", not valore))
        elif campo == "has_handicap":
            coppie.append(
                (campo, "" if valore is None else ("true" if valore else "false"))
            )
        elif campo == "time_limit_minutes":
            coppie.append((campo, valore if valore else ""))
        elif campo in ("catena_turno", "catena_gara"):
            coppie.append((campo, _catena_per_l_editor(valore)))
        else:
            coppie.append((campo, "" if valore is None else valore))
    return coppie


def _regola_della_fase(coppie: List[Tuple[str, Any]], campo: str, valore: Any) -> bool:
    """Limite e distanza della fase finale: un menu più un numero.

    Gli stessi campi nella gara e, col prefisso ``default_``, nel campionato.
    True se il campo era uno di questi (e le coppie sono state aggiunte).
    """
    from models.matchmaking.fase_finale import DistanzaDellaFase, LimiteDellaFaseFinale

    radice = campo[len("default_") :] if campo.startswith("default_") else campo
    if radice in ("final_phase_time_limit_minutes", "final_time_limit_minutes"):
        modo = campo[: -len("_minutes")]
        coppie.append((modo, LimiteDellaFaseFinale.del_valore(valore).value))
        coppie.append((campo, valore if valore and valore > 0 else ""))
        return True
    if radice in ("final_phase_distance", "final_distance"):
        coppie.append((f"{campo}_mode", DistanzaDellaFase.del_valore(valore).value))
        coppie.append((campo, valore or ""))
        return True
    return False


def _valori_del_campionato(campi: Mapping[str, Any]) -> List[Tuple[str, Any]]:
    """I campi del preset tradotti nei campi HTML del modulo del campionato.

    Qui l'handicap è una casella (nella gara un menu a tre voci), e i punti
    per posizione sono sei caselle, una per soglia: una tabella mancante le
    riporta al default, come il modulo le propone.
    """
    from models.classification.position_points import (
        DEFAULT_POSITION_POINTS,
        parse_points_table,
    )

    coppie: List[Tuple[str, Any]] = []
    for campo, valore in campi.items():
        if _regola_della_fase(coppie, campo, valore):
            continue
        if campo in CATENE_DEL_CAMPIONATO:
            coppie.append((campo, _catena_per_l_editor(valore)))
        elif campo == "default_time_limit_minutes":
            coppie.append((campo, valore if valore else ""))
        elif campo == "position_points":
            testo = valore if isinstance(valore, str) else None
            tabella = parse_points_table(testo) or {}
            for soglia, default in DEFAULT_POSITION_POINTS:
                coppie.append(
                    (f"position_points_{soglia}", tabella.get(soglia, default))
                )
        else:
            coppie.append((campo, "" if valore is None else valore))
    return coppie


def _catena_per_l_editor(valore: Any) -> str:
    """La catena come la scrive l'editor: le voci separate da virgole.

    Sulla gara la catena si salva in JSON (`testo_della_catena`), ma il campo
    nascosto dell'editor la vuole separata da virgole: è la forma che
    `catena_spareggi.js` rilegge.
    """
    import json

    testo = str(valore or "").strip()
    if testo.startswith("["):
        try:
            voci = json.loads(testo)
        except ValueError:
            return ""
        return ",".join(str(v) for v in voci) if isinstance(voci, list) else ""
    return testo


def nomi_dei_playoff(playoff: List[Mapping[str, Any]]) -> List[str]:
    """I nomi delle configurazioni dei playoff, per dirle in pagina."""
    return [
        str(c.get("name") or nome_predefinito_del_playoff(i))
        for i, c in enumerate(playoff)
    ]


def per_il_modulo(
    lettura: Lettura, kind: str = TipoPreset.GARA.value
) -> Dict[str, Any]:
    """Ciò che riceve il JavaScript del modulo: valori, listino, scartati.

    Per il campionato anche i campi dei playoff del passo 1 (`valori`: dove il
    modulo non li ha, il JavaScript li salta) e i loro nomi (`playoff`).
    """
    valori = valori_per_il_modulo(lettura.campi, kind)
    dati: Dict[str, Any] = {
        "valori": [],
        "listino": lettura.listino,
        "scartati": lettura.scartati,
    }
    if kind == TipoPreset.CAMPIONATO.value:
        valori = valori + valori_dei_playoff(lettura.playoff)
        dati["playoff"] = nomi_dei_playoff(lettura.playoff)
    dati["valori"] = [list(coppia) for coppia in valori]
    return dati
