# 🎱 Tornei Biliardo

> Piattaforma per organizzare **campionati, gare e allenamento** di biliardo
> americano: iscrizioni, abbinamenti, segnapunti, classifiche e statistiche.

**In produzione**: <https://www.torneibiliardo.it>

---

## Che cosa fa

Nasce per il lavoro reale di una sala: un direttore di gara apre un
campionato, i giocatori si iscrivono, l'app abbina i turni, raccoglie i
risultati dai tavoli e tiene le classifiche.

### Competizioni

- **Campionati multi-gara** con classifica generale aggregata e pesi per gara
- **Gare singole** oppure inserite in un campionato
- **Cinque formule di abbinamento**: Amalfi, girone all'italiana, eliminazione
  diretta, doppio KO, casuale
- **Playoff** con criteri di qualificazione, inviti e sostituzioni
- **Spareggi** Spot Shot Rally quando la classifica lascia dei pari merito
- **Iscrizioni** con lista d'attesa, categorie e handicap
- **Squadre** e separazione dei compagni nel sorteggio

### Al tavolo

- **Segnapunti** pensato per il telefono, con acchito, regola di apertura e
  runout marcati sul triangolo
- **Referto TPA** in stile Accu-Stats: il punteggio discende dal referto
- **Sfide individuali** fuori dalle gare
- **Schermo in sala**: la pagina pubblica da proiettare sulla TV, con i tavoli
  in corso e la classifica

### Intorno al gioco

- **Esami e allenamento**: esercizi a esito registrato, schede, esami certificati
- **Rating ELO** con regole per le competizioni a handicap
- **Gamification**: punti esperienza, traguardi, notifiche
- **Profili giocatore** con storico partite e statistiche
- **Vetrina pubblica** di gare e campionati, condivisibile
- **Guida in app** (`/aiuto`) con schermate generate dall'applicazione stessa

### Discipline

Palla 7 · Palla 8 · Palla 9 · Palla 10 · One Pocket · Straight Pool ·
Bank Pool · Rotation

---

## Avvio locale

```bash
git clone https://github.com/coppolapaolo/tornei-biliardo.git
cd tornei-biliardo

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt

python app.py
```

L'applicazione risponde su <http://localhost:5001>.

> Su macOS la porta 5000 è occupata da AirPlay Receiver e risponde 403: non è
> un guasto dell'app, è il motivo per cui si usa la 5001.

### Test e controlli

```bash
pytest tests/new/unit/ -n auto        # test unitari
pytest tests/new/integration/ -n 4    # integrazione (SQLite non regge -n auto)
pyright                               # type check, atteso a zero errori
black . && flake8                     # formattazione e stile
```

---

## Architettura

- **Python 3.11** con **Flask**; la CI prova su questa versione
- **SQLAlchemy** su **SQLite**, in sviluppo e in produzione (PythonAnywhere)
- Codice organizzato **per domini** (`models/campionato`, `models/match`,
  `models/playoff`, `models/tpa`, `models/exam`, …), non per livelli tecnici
- **Strategy pattern** per le formule di abbinamento e per le classifiche
- **networkx** per il matching sul grafo anti-reincontro
- Scritture sempre dentro un `@transactional`, con savepoint annidati
- Aggiornamenti dal vivo su tabella condivisa fra i worker, senza WebSocket
- Frontend **Bootstrap 5.3** con sopra il design system **7c**
  (`static/css/tokens-7c.css`, `theme-7c.css`)

---

## Lingue

Italiano (lingua di partenza) e inglese, entrambi completi. I testi passano da
`gettext`; le notifiche si compongono nella lingua di **chi le riceve**.

> ⚠️ Il ciclo di traduzione **non si esegue a comandi copiati a memoria**:
> `pybabel update` senza i flag giusti riempie le stringhe nuove con traduzioni
> prese a caso da altre voci. La procedura corretta è in
> [`CLAUDE.md`](CLAUDE.md) e nella skill `translate`.

---

## Documentazione

| Dove | Che cosa |
|---|---|
| [`docs/reference/SPECIFICHE.md`](docs/reference/SPECIFICHE.md) | I requisiti: si apre **prima** di toccare una regola di gioco |
| [`docs/adr/`](docs/adr/) | Le decisioni architetturali e il perché |
| [`docs/reference/`](docs/reference/) | Schema del database, autenticazione, convenzioni di nome e di interfaccia |
| [`docs/usecases/`](docs/usecases/) | I flussi di gara e i percorsi degli esami |
| [`CLAUDE.md`](CLAUDE.md) | Convenzioni operative, trappole note, come si lavora qui |

Lo stato di avanzamento vive nelle
[issue](https://github.com/coppolapaolo/tornei-biliardo/issues), non in questo
file: un elenco di funzionalità scritto qui invecchia senza che nessuno se ne
accorga.

---

## Contribuire

Segnalazioni e proposte passano dalle
[issue](https://github.com/coppolapaolo/tornei-biliardo/issues); per tutto il
resto, <info@torneibiliardo.it>. Per le pull request valgono due regole:

- il **titolo** segue [Conventional Commits](https://www.conventionalcommits.org)
  (`feat:`, `fix:`, `docs:`, …) perché da lì si calcola il numero di versione;
- i test e `pyright` devono essere verdi.

---

## Licenza

Distribuito sotto **GNU Affero General Public License v3.0** — vedi
[`LICENSE`](LICENSE).

L'AGPL estende alla rete l'obbligo della GPL: chi modifica questo software e lo
offre come servizio agli utenti deve rendere disponibile il codice modificato.

> **Eccezione.** Le immagini in
> [`docs/reference/inspiration/`](docs/reference/inspiration/) sono schermate di
> applicazioni di terzi, citate come riferimento progettuale. **Non sono coperte
> da questa licenza** e restano dei rispettivi titolari: vedi il
> [README della cartella](docs/reference/inspiration/README.md).
