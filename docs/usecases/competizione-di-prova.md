# Specifiche: Competizione di prova

*Intervista del 2026-09-04. Documento di specifica: descrive cosa deve fare la
funzione e perché, non come è scritta. Le regole numeriche (limite di prove,
scadenza) vanno riportate in `docs/reference/SPECIFICHE.md` e in
`tests/new/unit/test_specifiche_conformita.py` al momento dell'implementazione.*

## Problema

Un direttore appena promosso deve capire come funzionano le schermate di
gestione, dalla creazione della gara alla classifica finale, prima di condurre
una serata vera. Oggi può solo leggere la guida o fare esperimenti su gare
reali, che coinvolgono giocatori veri, mandano notifiche, muovono ELO e XP e
compaiono negli elenchi pubblici. Le azioni di simulazione esistono già ma solo
in modalità debug (`routes/main.py`, route `/debug/*`), quindi non in
produzione.

Lo stesso bisogno lo ha il direttore esperto che vuole provare un formato mai
usato (doppio KO, playoff, turni su misura) senza rischiare la serata.

## User story

Come **direttore di gara**, voglio creare una gara o un campionato **di
prova**, popolarli con giocatori fittizi e simulare le azioni dei giocatori, in
modo da imparare le schermate di gestione senza toccare dati reali e senza che
nessun altro veda la prova.

## Principi di progetto

1. **La prova è la stessa competizione con un flag.** Stesse route, stessi
   template, stessi servizi. Una funzione nuova nella parte generale compare
   nella prova senza lavoro aggiuntivo. Non esiste una seconda interfaccia.
2. **Invisibile per default.** Le competizioni di prova e i giocatori fittizi
   sono esclusi da ogni query salvo opt-in esplicito, con lo stesso meccanismo
   del soft delete (`models/soft_delete/filter.py`, `with_loader_criteria`).
   Una lista nuova che dimentica il filtro **non mostra** la prova, invece di
   mostrarla per errore. È la filosofia deny-by-default dell'ADR-028.
3. **La simulazione è sottile.** Ogni azione simulata chiama lo stesso servizio
   della route del giocatore, con l'id del giocatore fittizio. Non reimplementa
   nulla: se il servizio cambia firma, la simulazione fallisce forte invece di
   divergere in silenzio.
4. **Ciò che atterra sui fittizi non conta, ciò che atterra sul direttore sì.**
   ELO e XP dei fittizi possono anche muoversi (nessuno li vede), ma per
   pulizia il motore di rating li esclude. Statistiche, badge, XP e missioni
   del direttore non si muovono mai per una prova.

## Decisioni prese nell'intervista

| Tema | Decisione |
|---|---|
| Chi può creare una prova | Ogni direttore, sempre. L'admin la vede per assistenza |
| Limite | Al massimo **3 prove attive** per direttore (gare singole e campionati sommati) |
| Giocatori fittizi | **Creati per ogni prova**, muoiono con lei. Rating iniziali fissi e diversi fra loro, esclusi dal motore ELO |
| Come si popolano | Nella fase iscrizioni, tre pulsanti: **Iscrivi il minimo**, **Iscrivi fino al massimo**, **Iscrivine uno in più** |
| Chi si iscrive | **Solo fittizi.** Nessun utente reale, nemmeno il direttore |
| Simulazione risultati | Tre pulsanti: **Simula una partita**, **Simula il turno**, **Simula tutta la gara**. Il segnapunti vero resta usabile a mano |
| Playoff | Il direttore accetta o rifiuta l'invito **per ciascun fittizio**; in più un pulsante **Accetta tutti i rimanenti** |
| Visibilità | Direttore, co-direttori che aggiunge, admin. Nessun altro |
| Scadenza | **14 giorni** dalla creazione, avviso in app 3 giorni prima. Poi cancellazione automatica |
| Cancellazione | **Fisica**, di tutto: gare, partite, iscrizioni, qualificazioni, notifiche, giocatori fittizi |
| Campionato di prova | Dal **wizard vero** con tutte le opzioni e la spunta «prova» |
| Aiuto contestuale | Acceso dentro la prova, con **interruttore** nel banner per spegnerlo |
| Notifiche | Al direttore **in app**, etichettate «prova». **Mai** email né push |
| Statistiche e gamification | **Escluse ovunque** per il direttore |
| Punto d'ingresso | **Spunta «Competizione di prova»** nei moduli di creazione della gara singola e del campionato |
| Link pubblico e vetrina | **Disattivati**, con la spiegazione «in una gara vera qui trovi il link da condividere» |

## Criteri di accettazione

- [ ] AC1. Un direttore crea una gara singola o un campionato con la spunta
  «Competizione di prova». La competizione nasce con il flag, la scadenza a 14
  giorni e nessun giocatore.
- [ ] AC2. Con 3 prove attive la spunta è disabilitata con la nota «hai già tre
  prove: eliminane una per crearne un'altra». Il server rifiuta comunque la
  quarta (`ConflictError`).
- [ ] AC3. In una prova a iscrizioni aperte i tre pulsanti creano giocatori
  fittizi e li iscrivono: «il minimo» porta gli iscritti a
  `min_participants`, «fino al massimo» a `max_participants`, «uno in più»
  ne aggiunge uno. Ogni pulsante è disabilitato quando non ha effetto.
- [ ] AC4. Nessun utente reale può iscriversi a una prova: la prova non compare
  negli elenchi delle gare aperte, non ha link pubblico, e l'iscrizione manuale
  del direttore accetta solo fittizi.
- [ ] AC5. In una prova avviata, «Simula una partita», «Simula il turno» e
  «Simula tutta la gara» producono risultati validi per la distanza effettiva
  del turno (ADR-027) e portano la gara nello stato che avrebbe con giocatori
  veri. Il segnapunti e le altre azioni del direttore restano usabili.
- [ ] AC6. In un campionato di prova con playoff, la pagina degli inviti offre
  per ogni fittizio «Accetta» e «Rifiuta», più «Accetta tutti i rimanenti». Un
  rifiuto fa scattare la ricerca del sostituto (SPECIFICHE.md, «primo degli
  esclusi»).
- [ ] AC7. Ogni schermata di una prova mostra un banner persistente con:
  etichetta «Competizione di prova», data di scadenza, interruttore
  dell'aiuto, pulsante «Elimina la prova».
- [ ] AC8. «Elimina la prova» funziona in qualunque stato, dopo conferma, e
  non lascia righe orfane: gare, partite, rack, iscrizioni, qualificazioni,
  notifiche, eventi live e utenti fittizi spariscono.
- [ ] AC9. Un job giornaliero elimina le prove scadute con la stessa procedura.
  Tre giorni prima il direttore riceve una notifica in app.
- [ ] AC10. Le competizioni di prova e i giocatori fittizi non compaiono in:
  elenchi pubblici, home ospite, pagina della sala, «gare vicino a te»,
  ricerca giocatori, classifiche ELO, esami, disponibilità, profili altrui,
  segnalazioni. Presidiato da un test di enumerazione.
- [ ] AC11. Nessuna partita di prova muove un rating (`RatingExclusion.PROVA`)
  e nessun evento di prova assegna XP, badge o missioni a nessuno.
- [ ] AC12. Le notifiche generate da una prova arrivano al direttore in app
  con il prefisso «Prova»; i canali email e push le scartano.
- [ ] AC13. Il contatore «gare organizzate» e ogni altra statistica del
  direttore ignorano le prove.
- [ ] AC14. Con l'aiuto acceso, ogni elemento con `data-help` mostra una «?»
  con il testo di `hints.yaml` e il link alla guida; alla prima visita di una
  schermata compare la presentazione (`tours`). L'interruttore spegne tutto.
- [ ] AC15. Un test statico verifica che ogni `anchor` di `hints.yaml` compaia
  come `data-help` in un template della sua schermata, e viceversa.
- [ ] AC16. Tutte le stringhe nuove sono tradotte (skill `translate`).

## User journey

### Gara singola di prova

1. Il direttore è in home e tocca **Nuova Gara**.
2. Compila il modulo vero. In fondo spunta **Competizione di prova**. La data
   proposta è nei prossimi giorni, come per una gara vera.
3. Salva. Arriva sulla pagina della gara con il banner della prova in alto. La
   presentazione della schermata compare una volta; le «?» restano.
4. Apre le iscrizioni come farebbe davvero. Compaiono i tre pulsanti dei
   fittizi. Tocca **Iscrivi il minimo**: in elenco appaiono i giocatori. Tocca
   **Iscrivine uno in più** per vedere il caso dispari.
5. Configura tavoli e categorie con le schermate vere.
6. Chiude le iscrizioni, avvia il primo turno. Vede il sorteggio e la X.
7. Segna a mano una partita col segnapunti, poi tocca **Simula il turno**.
   Vede la classifica del turno aggiornarsi.
8. Usa **Simula tutta la gara**. Vede la classifica finale e le azioni di
   chiusura.
9. Riceve in app la notifica «Prova · La gara X è terminata».
10. Tocca **Elimina la prova** nel banner, conferma, torna in home.

### Campionato di prova con playoff

1. **Nuovo Campionato**, wizard vero, spunta «Competizione di prova».
2. Nel passo delle gare, le date proposte sono nei prossimi giorni e in ordine.
   Se il direttore le mette in disordine vede l'errore vero dell'ADR-016.
3. Per ogni gara: iscrizioni con i tre pulsanti, avvio, simulazione. Fra una
   gara e l'altra guarda la classifica di campionato crescere.
4. Alla fine delle gare regolari avvia il playoff. Nella pagina degli inviti
   accetta i primi, rifiuta uno, e tocca **Accetta tutti i rimanenti**. Vede
   comparire il sostituto.
5. Simula la finale. Vede la classifica finale nella modalità scelta
   (ADR-053).
6. Elimina la prova.

### Scadenza

1. All'undicesimo giorno il direttore riceve «Prova · La tua prova "X" scade
   fra 3 giorni». Il banner mostra la data.
2. Al quattordicesimo giorno il job giornaliero la elimina. Se il direttore
   apre un link salvato trova il 404 con il messaggio «questa prova è scaduta».

## Casi limite

| Scenario | Comportamento atteso |
|---|---|
| Direttore al limite di 3 prove | Spunta disabilitata con nota; il server rifiuta comunque |
| Spunta «prova» su una gara dentro un campionato vero | La spunta non compare: una gara eredita il flag dal campionato, in entrambi i sensi |
| Gara vera dentro un campionato di prova | Impossibile: ogni gara del campionato è di prova |
| «Iscrivi fino al massimo» senza `max_participants` | Pulsante disabilitato con nota «imposta un massimo» |
| «Iscrivi il minimo» con iscritti già oltre il minimo | Disabilitato |
| Ritiro di un fittizio | Funziona con la schermata vera del direttore; il fittizio resta iscritto come ritirato |
| Simulazione su un turno senza partite attive | Messaggio «nessuna partita da simulare» |
| Simulazione mentre una partita è aperta sul segnapunti | La simulazione la chiude col punteggio simulato; il segnapunti mostra il risultato |
| Pareggio in «esattamente N rack» con N pari | La simulazione può produrlo, come nella realtà; la classifica lo gestisce |
| Direttore perde il ruolo (RoleGrant revocato) | Le prove restano fino alla scadenza, poi spariscono. Non le vede più |
| Account del direttore anonimizzato | Le sue prove vengono eliminate insieme all'anonimizzazione |
| Co-direttore rimosso | Non vede più la prova |
| Fusione di account (`UserMergeService`) | I fittizi non sono mai né sorgente né destinatario; il servizio li rifiuta |
| Eliminazione mentre un altro co-direttore ha la pagina aperta | Il prossimo clic dà 404 «prova eliminata» |
| Job di scadenza fallisce su una prova | Le altre vengono eliminate; l'errore va nel riepilogo di `daily_jobs.py` |
| Due richieste concorrenti di «Iscrivi il minimo» | Il vincolo `uq_inscription_gara_user` e il conteggio nel servizio impediscono di superare il minimo |
| Fittizio cercato nella ricerca giocatori o nell'iscrizione manuale di una gara vera | Non compare: il filtro esclude `is_fittizio` |
| Ricalcolo ELO di massa (`recalc_elo.py`) | Salta le partite di prova con `RatingExclusion.PROVA` |
| Prova con handicap e categorie | Funziona come nella realtà: il direttore assegna le categorie ai fittizi |
| Aiuto contestuale su una schermata senza hint | Nessuna «?», nessuna presentazione; in sviluppo un avviso in console |
| Ancora `data-help` senza hint corrispondente | In sviluppo avviso in console; il test statico lo blocca in CI |

## Impatto tecnico

### Dati

- `Campionato.is_prova`, `Gara.is_prova` (boolean, default `False`, indice).
  La gara eredita il valore dal campionato alla creazione, come la regola di
  apertura (ADR-056).
- `Campionato.prova_expires_at`, `Gara.prova_expires_at` (solo sulla radice:
  il campionato, o la gara singola). Impostato a `utc_now() + 14 giorni`.
- `User.is_fittizio` (boolean, default `False`, indice) e
  `User.prova_gara_id` / `User.prova_campionato_id` (nullable, **senza**
  chiave esterna: chiuderebbe un ciclo con `gara.director_id`): a quale prova
  appartiene. Lo username è il nome verosimile («Maria Rossi», con ordinale
  se già preso), perché è il nome con cui si gioca; email sintetica su
  dominio riservato `.invalid`, password non impostabile, onboarding già
  completato, rating iniziale da una tabella fissa di 16 nomi e rating
  diversi fra 1400 e 1600 (per un seeding leggibile).
- Migration datata, idempotente, con i timestamp di `BaseModel` già presenti
  (nessuna tabella nuova).
- Nessun backfill: le competizioni esistenti non sono prove.

### Invisibilità

- Estensione di `models/soft_delete/filter.py` (o modulo gemello
  `models/prova/filter.py`) che registra `with_loader_criteria` per `Gara`,
  `Campionato` e `User` sul flag di prova, con opzione di esecuzione
  `include_prova=True` per l'opt-in.
- L'opt-in viene acceso **una volta sola**, nei decoratori
  `gara_manager_required` / `campionato_manager_required` e per l'admin: tutte
  le route del direttore vedono le prove, tutte le altre no. La home del
  direttore fa opt-in esplicito nella sola sezione «Le tue prove».
- Trappola nota: il criterio vale solo per le entità presenti nella query
  (`models/dashboard/section_builders.py`, righe 162 e 219). Per questo serve
  il test di enumerazione di AC10, sul modello di
  `tests/new/integration/test_endpoint_allowlist.py`.

### Servizi

- `models/prova/service.py`: `create_fittizi(radice, n)`,
  `inscrivi_minimo/massimo/uno(gara_id)`, `elimina_prova(radice)`,
  `prove_attive(direttore_id)`, `verifica_limite(direttore_id)`.
- `models/prova/simulation_service.py`: `simula_partita`, `simula_turno`,
  `simula_gara`, `rispondi_invito(qualification_id, accetta)`,
  `accetta_tutti_gli_inviti(campionato_id)`. Le tre azioni sui risultati
  nascono dal trasloco delle funzioni `_debug_*` di `routes/main.py`, che
  restano come chiamanti del servizio (una sola implementazione).
- `RatingExclusion.PROVA` in `models/rating/eligibility.py`: la partita di una
  gara di prova non muove i rating. Un solo punto, come per il resto.
- Gamification: un guard unico nel punto in cui i handler vengono registrati
  scarta gli eventi la cui competizione è di prova. Niente `if` nei singoli
  handler.
- Notifiche: `NotificationFactory` marca le notifiche originate da una prova
  (prefisso «Prova ·» nel titolo) e i canali email e push le scartano.
- Statistiche del direttore: le query di «gare organizzate» e i badge
  correlati filtrano `is_prova`.
- `UserMergeService` e `user.anonymize()` rifiutano i fittizi; l'anonimizzazione
  di un direttore elimina prima le sue prove.
- Eliminazione fisica: ordine figli → radice, con `PRAGMA foreign_keys=ON`
  rispettato. Unica funzione, usata dal pulsante e dal job.
- `scripts/daily_jobs.py`: job `prove_scadute` (notifica a 3 giorni,
  eliminazione a 0).

### Route e interfaccia

- Nuove route sotto `admin.competition` e `admin.campionato`, tutte con
  `gara_manager_required` / `campionato_manager_required`, tutte in
  `ENDPOINT_ROLES` con `{"director"}` (ADR-028).
- Spunta nei moduli `gara_create_standalone.html` e
  `campionato_wizard_step1.html`, gestita da `GaraFormParser` /
  `CampionatoFormParser`.
- Banner di prova in un componente incluso da `gara_detail`,
  `campionato_detail` e dalle schermate figlie (partita, tabellone, vetrina,
  playoff). Vetrina con sezione link pubblico disattivata.
- Pulsanti dei fittizi nella fase iscrizioni; pulsanti di simulazione nella
  fase di gioco; risposte agli inviti nella pagina del playoff. Tutti nel
  design system 7c (skill `ui-7c`).
- Sezione «Le tue prove» in home, con badge e contatore su 3.

### Aiuto contestuale

- Componente client `static/js/help-hints.js`: legge l'endpoint corrente
  iniettato nella pagina, chiama `/aiuto/api/schermata/<endpoint>`, aggancia
  una «?» a ogni `[data-help]` e mostra la presentazione alla prima visita
  (memoria in `localStorage`). L'interruttore del banner lo attiva o spegne
  (`localStorage`, per browser).
- Il componente **non conosce il flag di prova**: è una «modalità aiuto» che
  il banner accende. Domani la accenderà anche altro.
- Instrumentazione dei template con `data-help` per gli hint esistenti delle
  schermate del direttore, e nuovi hint per campionato, playoff e per i
  pulsanti di simulazione stessi (skill `help-docs`).
- Test statico bidirezionale anchor ↔ `data-help` (AC15), nello stile di
  `test_drill_exam_manual_findings.py`.

### Guida

- Nuova pagina `help_content/it/pages/fare_una_prova.yaml`, con schermate
  catturate su `seed_demo.py` esteso con una prova.
- Aggiornamento di `chi_fa_cosa.yaml` e `diventare_direttore.yaml`.

### Test

- Unit: limite di 3, scadenza, creazione fittizi, esclusione rating, guard
  gamification, eliminazione senza orfani.
- Integrazione: journey della gara singola e del campionato con playoff (sul
  modello di `test_stagione_e2e_*`), enumerazione degli elenchi pubblici
  (AC10), fittizi invisibili nella ricerca, notifiche senza email.
- Statico: anchor ↔ `data-help`; `ENDPOINT_ROLES` per le route nuove.
- Conformità: righe nuove in SPECIFICHE.md riportate in
  `test_specifiche_conformita.py`.

## Sequenza di consegna

1. **Fondamenta**: flag, scadenza, fittizi, filtro di invisibilità, limite,
   eliminazione, job. Gara singola di prova con i tre pulsanti delle
   iscrizioni. Esclusioni rating, gamification, notifiche, statistiche.
2. **Simulazione**: trasloco delle azioni di debug nel servizio, tre pulsanti
   in pagina gara.
3. **Campionato di prova**: spunta nel wizard, ereditarietà del flag, risposte
   agli inviti al playoff.
4. **Aiuto contestuale**: componente, ancore nei template, hint mancanti,
   pagina della guida, test statico. Indipendente dai primi tre, può viaggiare
   in parallelo purché le ancore precedano i nuovi hint.

Ogni tappa è una PR `feat:` e va in produzione da sola.

## Decisioni successive all'intervista (2026-09-04)

- **Stato delle partite simulate: entrambi.** Il direttore deve imparare sia
  la chiusura dai giocatori sia la propria. «Simula una partita» e «Simula il
  turno» chiudono una parte delle partite con la doppia conferma
  (`CONFIRMED_BY_BOTH`) e lasciano le altre con il risultato segnato da un solo
  giocatore, in attesa che il direttore le validi. La scelta è deterministica
  sull'id della partita (pari/dispari), come fa `seed_demo.py`. «Simula tutta
  la gara» chiude tutto, perché il direttore ha chiesto di arrivare in fondo.
- **Nomi dei fittizi: verosimili e generici**, del tipo Maria Rossi, Mario
  Bianchi. Tabella fissa di 16 coppie nome-cognome fra i più comuni in Italia,
  scritta nel codice e distinta dai nomi del seed dimostrativo. Il badge
  «prova» li distingue dai giocatori veri.
- **Non esiste un elenco iscritti di campionato** distinto dalle gare: i tre
  pulsanti agiscono solo sulle gare.

## Domande aperte

- [ ] **Aiuto contestuale fuori dalla prova**: chi lo accende nelle
  competizioni vere, e quando le «?» si dissolvono? Fuori scopo qui;
  la modalità aiuto nasce spegnibile proprio per rimandare questa decisione.
- [ ] **ADR**: il filtro di invisibilità per default e l'eliminazione fisica
  dei fittizi sono decisioni con conseguenze durature. Da scrivere con la
  skill `adr` all'inizio della tappa 1.
