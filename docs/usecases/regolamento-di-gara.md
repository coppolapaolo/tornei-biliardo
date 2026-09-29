# Regolamento di gara: modifiche tracciate invece che impedite

Specifica nata dall'intervista del 2026-09-29 e rivista lo stesso giorno dopo
una verifica sul codice e sulla documentazione. Parte da tre fonti:

- il caso della **finale dei playoff** che, nata già con gli iscritti, non si
  poteva più modificare (né la sala né chi spacca);
- la issue **#549**: modificare una gara a iscrizioni aperte, con notifica e
  conferma degli iscritti;
- la issue **#265** (29/08/2026): «rilassare `can_be_modified` con la modifica
  tracciata». Da lì vengono il segno in classifica e la correzione del peso a
  gara finita; altre scelte di quella issue sono state riconsiderate e
  decise diversamente, come scritto sotto.

## Il principio

Il direttore può correggere quasi tutto, quasi sempre. In cambio ogni
correzione resta **scritta e visibile a tutti**: chi, quando, cosa (prima →
dopo) e, se lo scrive, perché. Serve a gestire gli imprevisti della serata
senza stratagemmi, e a dare una base concreta a eventuali contestazioni.

Tre cose non cambiano mai:

1. **come si è già giocato**: una partita giocata resta con le regole con cui è
   stata giocata;
2. **la struttura della gara dopo l'avvio** (strategia, numero di turni,
   sistema di classifica): si cambia solo annullando l'avvio;
3. **i criteri di qualificazione ai playoff dopo l'invio degli inviti**.

## 1. Quando vale un cambio di regole

Le regole di gioco (distanza, «al N» o «esattamente N», disciplina, set, chi
apre, chi spacca, handicap e categorie, gestione dei dispari, anti-reincontro)
si possono cambiare in ogni momento prima della fine della gara.

- **Prima dell'avvio**: il cambio vale per tutta la gara.
- **A gara avviata**: il cambio si salva subito e vale **dal turno successivo**.
  Il turno in corso e quelli già giocati restano con le regole che avevano.
  La pagina lo dice prima di salvare: «Vale dal turno 4».
- In tutti i formati tranne la casuale il turno successivo si avvia solo
  quando il precedente è chiuso (`verifica_turno_chiuso`); nel tabellone le
  partite dei due lati giocate insieme sono lo **stesso** turno. Il «turno» è
  quindi quello che la gara conosce già (`round_number`), uguale per tutti i
  formati.
- **Strategia casuale**: tutti i turni nascono all'avvio e si giocano senza
  ordine. Dopo l'avvio **le regole di gioco sono bloccate**; restano
  modificabili solo le cose pratiche (sala, orario, tavoli, quota).
- **Formati a tabellone**: le impostazioni che il tabellone impone (dispari,
  ritiro, spareggio, «al N», anti-reincontro) restano non modificabili come
  oggi.

Impostazioni particolari:

| Impostazione | A gara avviata |
|---|---|
| Cosa succede a chi si ritira | vale per i ritiri successivi al cambio |
| Spareggio | modificabile finché lo spareggio non è cominciato |
| Numero di turni | **bloccato**, in tutti i formati (nell'Amalfi cambierebbe gli abbinamenti dei turni rimanenti) |
| Strategia, sistema di classifica | bloccati: si cambiano solo con «Annulla l'avvio», finché nessuna partita ha un risultato |
| Capienza | si può alzare a iscrizioni aperte; chi è in lista d'attesa entra, in ordine |

### Correzioni a gara finita

A gara finita **come si è giocato** non si tocca. Si può invece correggere
**quanto conta la gara** nel campionato:

- il **peso** della gara;
- i **punti per posizione** del campionato.

La classifica si ricalcola, con la traccia e il segno descritti al punto 5.

## 2. Campionato: valori proposti, non ereditati

Il campionato **propone** i valori di partenza delle sue gare; ogni gara poi
decide per sé. Una regola sola per tutti i valori.

- Quando il direttore cambia un valore del campionato, l'app elenca le gare
  **non ancora avviate**, ciascuna con una casella. Sono già spuntate quelle
  che avevano il vecchio valore del campionato; non spuntate quelle con un
  valore proprio. Esempio: la quota passa da 10 a 12 €; la gara 7 (10 €) è
  spuntata, la gara 9 (15 €) no.
- Ogni gara aggiornata così ha la sua voce nella storia («modificato dal
  campionato») e la sua notifica ai propri iscritti.
- Le gare in corso o finite non compaiono: si modificano dalla loro pagina.
- **Chi apre, chi spacca e handicap**, che oggi seguono il campionato in
  diretta, passano allo stesso sistema: al passaggio ogni gara riceve il
  valore che segue adesso, e da lì si comporta come le altre.
- Il blocco attuale del campionato (niente modifiche appena una gara ha
  iscritti) viene tolto.
- **Disciplina e distanza** restano come oggi: la gara nuova le copia dalla
  precedente.

## 3. Playoff

- **Come si gioca la finale** (sala, data, distanza, disciplina, turni…): la
  configurazione propone, la finale decide, con lo stesso meccanismo del
  campionato. Se la finale esiste e non è avviata, l'app chiede se applicare
  il cambio anche a lei. La finale si modifica anche direttamente.
- **Chi si qualifica** (posizioni, posti, gare minime): **bloccato** dopo
  l'invio degli inviti, come oggi. Si chiude anche la strada che oggi cambia
  il minimo di gare senza controllo (`update_playoff_min_garas`).
- Gli strumenti a mano che esistono già (aggiungere un giocatore, toglierlo,
  rispondere al suo posto) restano, e ogni loro uso entra nella **storia dei
  playoff** con chi, quando e motivo facoltativo.
- **Correzione che sposta la classifica dopo gli inviti**: l'app prepara una
  proposta («ritirare l'invito a Bianchi, ora 10°; invitare Rossi, ora 7°»).
  Il direttore la accetta (l'app ritira e invia gli inviti, con le
  notifiche), la rifiuta, o sistema a mano. La scelta va nella storia. Dopo
  l'avvio della finale la proposta non compare più.

## 4. Storia delle modifiche

- Ogni **salvataggio** è una voce, con le sue righe campo per campo (prima →
  dopo). La storia non si accorpa mai: sala A → B → A restano due voci.
- Ogni voce porta: quando, **nome e ruolo** di chi ha modificato (direttore,
  co-direttore, amministratore), da dove (gara, campionato, playoff), motivo.
- Il **motivo è sempre facoltativo**; il campo è in evidenza con un
  suggerimento («Scrivi perché: servirà in caso di contestazioni»).
- Le voci non si cancellano e non si correggono: si aggiunge al massimo una
  nota successiva, datata e firmata.
- La storia **appartiene alla gara**: se la gara viene cancellata, la sua
  storia se ne va con lei.
- Entrano nella storia anche: «Annulla l'avvio», le riconferme date dal
  direttore per un giocatore, le proposte accettate o rifiutate.
- Nessuna storia per le modifiche precedenti all'introduzione; la pagina lo
  dice.
- **Due direttori che salvano insieme**: si applicano solo i campi che chi
  salva ha davvero cambiato; se uno di quei campi l'ha cambiato l'altro nel
  frattempo, il salvataggio si ferma e lo dice.

## 5. Dove si vede

### Regolamento di gara

Una pagina pubblica, visibile a tutti, raggiungibile dalla pagina della gara
e dalla vetrina, dove sostituisce il pulsante del link esterno.

1. **In vigore**: ogni impostazione, e se è stata cambiata da quale turno
   vale.
2. **Per turno**, solo se ci sono differenze fra turni: «Turni 1–3: al 5 ·
   dal turno 4: al 7 (cambiato il 29/09 alle 21:40)».
3. **Storia delle modifiche**, dalla più recente.
4. In fondo, se c'è, il pulsante **«Regolamento completo»** verso il documento
   esterno (il campo «Link esterno» di oggi).

Sulla pagina del campionato, lo stesso per i valori proposti dal campionato e
per i playoff, con la storia dei playoff.

### Segno in classifica

- Nell'**elenco delle gare** del campionato: «Gara 5 · ×2», con il vecchio
  «×1» barrato.
- **Sopra la classifica**, una riga ben visibile: «Classifica ricalcolata il
  12/10: peso della gara 5 da ×1 a ×2 — Mario Rossi». Toccandola si leggono
  i dettagli e il motivo. Lo stesso per i punti per posizione.
- Un segno su ogni riga di giocatore (dettaglio gara per gara) **non** si fa
  ora: richiederebbe di rifare il calcolo, che produce solo totali.

## 6. Notifiche accorpate

La storia è la verità; le **notifiche** si accorpano.

- La prima modifica apre una notifica in attesa per quella gara; le
  successive ci confluiscono. Si confronta lo stato di partenza con quello
  attuale: A → B → C diventa «A → C»; A → B → A non manda niente.
- Parte dopo **30 minuti** senza nuove modifiche (in pratica 30–90 minuti,
  perché il controllo gira ogni ora), **subito** se il direttore preme «Invia
  ora», **subito** se la gara comincia entro **3 ore**.
- Solo notifiche nell'app, come oggi; testi nella lingua e nel fuso di chi
  riceve (ADR-043, ADR-062).
- Competizione di prova: si comporta come le altre notifiche di prova, con il
  prefisso «Prova ·» (ADR-058).

## 7. Riconferma degli iscritti

Scatta solo per ciò che può cambiare la decisione di esserci:

| Modifica | Riconferma |
|---|---|
| data, o ora spostata di più di **1 ora** | sì |
| sala | sì |
| quota in aumento | sì |
| regole di gioco, formato | no, solo notifica |
| nome, tavoli, quota in diminuzione, piccoli spostamenti d'orario | no, solo storia |

- Su ogni iscrizione si conserva la **versione accettata** (data, ora, sala,
  quota). La riconferma serve solo se i valori attuali ne differiscono oltre
  soglia: più modifiche danno **una sola** richiesta; tornando al valore
  accettato, la richiesta sparisce.
- Chi non riconferma resta iscritto **«da riconfermare»**; nessun ritiro
  automatico. Decide il direttore, al più tardi all'avvio.
- Il direttore può **riconfermare al posto del giocatore**; va nella storia.
- Vale anche per chi ha accettato l'invito ai playoff. Per il campionato non
  c'è riconferma.
- Lo stato è **visibile come le iscrizioni**.
- Non è un voto sulla modifica, che resta decisione del direttore: chiede
  solo «ci sei ancora?». Per questo non contraddice il «niente consenso»
  della #265.

## 8. Date in un campionato

Le gare restano in ordine di data (ADR-016). Se una nuova data scavalca le
gare successive, l'app propone di spostarle dello stesso numero di giorni
(«Spostare anche le gare 8 e 9 di 10 giorni, al 27/10 e al 3/11?»). Il
direttore accetta (ogni gara spostata ha la sua voce e le sue notifiche),
rifiuta (e il cambio non si salva) o modifica a mano.

## Criteri di accettazione

- [ ] La finale dei playoff appena creata, con gli iscritti, permette di
      cambiare sala e chi spacca; la modifica compare nel Regolamento di gara.
- [ ] Amalfi al turno 3: la distanza portata da 5 a 7 lascia al 5 il turno 3
      (anche le partite non iniziate) e mette al 7 il turno 4.
- [ ] Una partita in corso non cambia chi spacca quando il direttore cambia
      la regola; la partita del turno dopo usa la regola nuova.
- [ ] Un ricalcolo del punteggio ELO usa le categorie che valevano quando la
      partita è stata giocata.
- [ ] Gara casuale avviata: distanza e chi spacca non si modificano; la sala sì.
- [ ] Il numero di turni non si modifica dopo l'avvio.
- [ ] Cambio della quota nel campionato: compaiono le gare non avviate, già
      spuntate quelle che avevano la quota vecchia.
- [ ] Peso della gara 5 corretto a campionato finito: la classifica si
      ricalcola, «×2» con «×1» barrato nell'elenco gare, riga di ricalcolo
      sopra la classifica.
- [ ] Correzione dopo gli inviti che cambia chi rientra nei posti: il
      direttore vede la proposta e può accettarla, rifiutarla o fare a mano.
- [ ] Sala A → B → C in 10 minuti: due voci nella storia, **una** notifica
      «A → C», **una** richiesta di riconferma. A → B → A: nessuna notifica.
- [ ] Chi non riconferma resta iscritto «da riconfermare»; il direttore può
      riconfermare per lui, e la storia lo dice.
- [ ] Gara 7 spostata dopo la gara 8: compare la proposta di spostare le
      successive.
- [ ] La promessa del modulo («gli iscritti ricevono una notifica») è vera.

## Verifica sul codice (2026-09-29)

Cosa esiste, cosa va costruito, cosa va cambiato. Riferimenti a file e righe
al momento della verifica.

**Blocchi da sostituire con regole campo per campo**

- `Gara.can_be_modified()` (`models/competition/models.py:841`: SETUP e
  nessun iscritto), controllato nella route (`crud.py:322`), nel servizio
  (`services.py:312`) e in nove template.
- `Campionato.can_be_modified()` (`models/campionato/models.py:178`),
  controllato in `edit_campionato` e `update_campionato`.
- `RoundConfiguration`: solo in SETUP, controllo **nella route**
  (`rounds.py:1024`, `:1106`), da spostare in un servizio.
- `PlayoffService.update_configuration`: tutto bloccato dopo gli inviti; va
  diviso fra criteri (bloccati) e valori della finale.
- Categorie: modificabili solo prima dell'avvio (`categoria/service.py:99`).

**Regole che la partita rilegge dalla gara** (oggi un cambio arriverebbe
anche alle partite giocate o in corso). Ogni partita deve portarsi dietro le
sue regole dalla creazione (`round_creation.py:84-115`):

| Regola | Oggi | Serve |
|---|---|---|
| Distanza | copiata (`match_distance`), salvo il caso «al 1» | togliere l'eccezione |
| «Al N» / «esattamente N», set «al N» | copiata solo se diversa dalla gara | copiarla sempre, e riempire le righe vecchie |
| Triangoli per set | letti dalla gara (`distance.py:174`, `match_service.py:603`) | colonna nuova sulla partita |
| Disciplina | copiata solo con un cambio per turno | copiarla sempre, e riempire le righe vecchie |
| Chi apre, chi spacca | lette dalla gara a ogni triangolo (`base_match.py:174`) | colonne nuove sulla partita, come sulle sfide individuali |
| Handicap | colonna sulla partita mai scritta | scriverla alla creazione, e riempire le righe vecchie |
| Categorie dei giocatori | lette dall'iscrizione a ogni ricalcolo ELO (`rating/eligibility.py`) | fissarle sulla partita (anche per il trio) |
| X con prova | letta dalla gara (`match/models.py:319`) | segno sulla partita |
| Ritiro | applicato al momento del ritiro | niente |
| Spareggio | letto a fine gara | controllo «spareggio non cominciato» |

**Da costruire**

- La storia delle modifiche: oggi non c'è nulla di simile (`AuditMixin` non è
  usato da nessun modello). Le scritture passano da molti servizi (gara:
  `update_gara`, tavoli, date d'iscrizione, vetrina, categorie, direttori,
  cambi per turno; campionato: `update_campionato`, `_propaga_sistema`;
  playoff: `PlayoffService` e `update_playoff_min_garas`): ognuno deve
  scrivere la sua voce, con chi agisce.
- Il modulo di modifica rimanda **tutti** i campi e riempie di valori
  predefiniti quelli assenti (`form_parser.py`); `Gara` non ha una colonna di
  ultima modifica. Serve sapere quali campi sono stati davvero cambiati.
- Le proposte (campionato → gare, configurazione → finale, date successive,
  inviti dopo una correzione): pagine di conferma nuove.
- Riconferma: colonne nuove su `Inscription` e `PlayoffQualification`.
- Notifiche accorpate: un tipo nuovo di notifica, una tabella per quelle in
  attesa, un lavoro orario (accanto a `send_match_reminders.py`, oppure un
  nuovo scheduled task). Il lavoro gira fuori da una richiesta e deve
  includere le competizioni di prova esplicitamente, altrimenti le salta.
- Segno in classifica: il valore vecchio arriva dalla storia; la classifica
  (`statistics_service.classifica_generale`) si ricalcola già in diretta.
- Regolamento di gara: route e pagina nuove, con voce `anonimo` in
  `ENDPOINT_ROLES`. Il link esterno oggi compare solo nelle vetrine.
- Capienza alzata: oggi non ripesca dalla lista d'attesa.
- Migration: colonne nuove sulla partita e riempimento delle righe esistenti
  con le regole effettive di oggi; chi apre/chi spacca/handicap delle gare
  ereditati dal campionato scritti sulla gara.

**Problemi trovati per strada**, da sistemare comunque:

- il modulo di modifica promette notifiche che nessuno manda
  (`_gara_edit_form.html:19`, `:41`);
- `/aiuto` (`creare_un_campionato.yaml:228`) dice che i punti per posizione
  si cambiano dopo la partenza, ma il codice lo impedisce;
- l'aggiunta a mano ai playoff non registra chi l'ha fatta
  sull'iscrizione (`_iscrivi_alla_gara` non passa `inscribed_by_id`);
- diverse route dei playoff non controllano che la configurazione appartenga
  al campionato dell'indirizzo.

## Documenti da emendare

- `SPECIFICHE.md`: riga 21 («se una gara è in itinere non è possibile
  modificarla»), riga 294 (sistema di classifica del campionato), riga 458
  (valori precompilati: resta vero, si aggiunge la proposta alle gare
  esistenti), sezione Playoff; nota datata per ciascuna.
- ADR nuovo, ed emendamenti a: ADR-027 (cambi per turno solo prima
  dell'avvio), ADR-053 e la riga di `CLAUDE.md` sul blocco dei playoff,
  ADR-056 («a gara cominciata i campi si affossano»; le regole ora si fissano
  sulla partita).
- `/aiuto`: `opzioni_della_gara`, `creare_una_gara`, `gestire_le_iscrizioni`,
  `turni_su_misura`, `formati_di_gioco`, `abbinamenti`, `playoff`,
  `creare_un_campionato`, `far_conoscere_la_gara` (il link al regolamento).
- `ROADMAP.md`: la #265 passa fra le cose in corso.

## Parole

- Ai giocatori si mandano **notifiche**, non avvisi.
- Per l'Amalfi non c'è sorteggio: si **avvia** il primo turno. Il gesto per
  cambiare la struttura è **«Annulla l'avvio»**, che esiste già.
- «Regolamento di gara» riunisce la pagina nuova e il link esterno al
  regolamento, che oggi si chiama allo stesso modo.
