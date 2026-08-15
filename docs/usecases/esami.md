Gli esami sono sequenze ordinate di drill, certificate **di persona** da un
esaminatore. Il ruolo di esaminatore è concedibile e ortogonale: chi lo riceve
resta player, e continua a iscriversi alle gare e a sostenere esami altrui.

Vedi ADR-041 (ruoli concedibili) e ADR-042 (esame certificato).

## Use case 1 — Bootstrap: il primo esaminatore, e il suo primo esame

- Non esiste ancora nessun esaminatore nel sistema.
- L'admin apre la lista utenti, sceglie un player esperto e lo **promuove a
  esaminatore**, con lo stesso gesto con cui promuove a direttore di gara
  _(variante: promuove un direttore di gara)_.
- Il player riceve la notifica e il toast di sblocco 🔓; compare la voce "Esami".
- L'esaminatore compone l'esame "Fondamentali — livello 1" con tre drill: uno
  numerico con punteggio massimo 10, uno superato/non superato, uno numerico con
  massimo 15.
- Riordina i drill spostando il secondo in prima posizione.
- Prova ad aggiungere altri esaminatori all'esame: **non può**, è l'unico
  titolare del ruolo, e la schermata glielo dice invece di mostrargli un elenco
  vuoto.
- Dichiara le proprie **disponibilità**: sala "Biliardo Centrale", martedì e
  giovedì, 18:00–22:00 — dalla stessa schermata delle disponibilità per i match.
- L'esame compare come attivo; le statistiche mostrano 0 esami sostenuti.
- _(variante)_ L'admin promuove un secondo player a esaminatore; ora il creatore
  dell'esame **può aggiungerlo** come co-esaminatore.

## Use case 2 — Tentativo in autonomia: allenamento, non certificazione

- Un player ha completato 3 drill e ha **sbloccato** gli esami.
- Apre "Fondamentali — livello 1", vede i drill che lo compongono, il punteggio
  massimo di ciascuno e **chi sono gli esaminatori** che lo somministrano.
- Sceglie **"Prova da solo"**.
- Registra 8/10 sul primo drill, supera il pass/fail, registra 7/15 sul terzo
  _(variante: abbandona a metà e riprende più tardi lo stesso tentativo)_.
- Chiude il tentativo. Nel profilo compare fra gli esami sostenuti, **senza il
  badge "certificato da …"** che portano invece gli esami fatti davanti a un
  esaminatore.
- Scattano gli XP di allenamento e la streak settimanale dei drill, **non** gli
  achievement di certificazione.

## Use case 3 — Richiesta a più esaminatori, accordo su data e ora, certificazione

- Premessa: l'esame ha due esaminatori, il secondo aggiunto dal creatore.
- Il player apre l'esame e sceglie **"Chiedi un appuntamento"**.
- Vede i due esaminatori e sceglie di chiedere **a entrambi** _(variante 1:
  sceglie un solo esaminatore; variante 2: l'esame ha un solo esaminatore e la
  scelta non si pone)_.
- Propone: giovedì alle 20:00 al "Biliardo Centrale". Parte una richiesta con
  **due destinatari** e una scadenza.
- Entrambi gli esaminatori ricevono la notifica.
- Il primo **contropropone**: giovedì alle 21:30, stessa sala. Da questo momento
  la trattativa è **fra lui e il player**: il secondo esaminatore resta in
  attesa e potrà solo accettare l'ultima proposta o lasciar scadere, non
  inserirsi nello scambio.
- Il player **rilancia**: giovedì alle 21:00. Lo scambio prosegue finché uno
  accetta _(variante: nessuno accetta e la richiesta scade)_.
- L'esaminatore **accetta**. In quel momento:
  - la richiesta si chiude per il **secondo** esaminatore, che riceve la
    notifica "presa in carico da un altro esaminatore";
  - il player riceve la conferma con data, ora e sala;
  - nasce l'**appuntamento**, visibile a entrambi.
- Giovedì, davanti al tavolo, l'esaminatore apre la sessione. **Il player deve
  accettare l'inizio**: finché non lo fa, non si può registrare nulla _(variante:
  il player non si presenta e l'esaminatore interrompe la sessione senza esito)_.
- L'esaminatore inserisce i punteggi drill per drill mentre il player esegue.
- Alla fine **certifica: superato** _(variante: non superato)_. Nessun voto,
  nessuna nota.
- Il player riceve la notifica; nel profilo l'esame compare **marcato come
  certificato**, con il nome di chi l'ha certificato, la data e la sala.
- Solo ora scattano gli XP di certificazione e i relativi achievement.

## Use case 4 — Delega: la richiesta di ruolo va a più esaminatori

- Un player ha completato 20 drill: ha **sbloccato** la richiesta del ruolo.
- **Dalle pagine dei drill** (non dal profilo) compare "Diventa Esaminatore".
- Vede l'elenco degli esaminatori esistenti e sceglie di chiedere **a tutti**
  _(variante 1: sceglie solo due esaminatori; variante 2: non esiste ancora
  nessun esaminatore e la richiesta può andare solo ad admin)_.
- Gli esaminatori interpellati ricevono la richiesta con i dati di attività del
  richiedente.
- **Il primo che approva concede il ruolo**; per gli altri la richiesta si chiude
  e ne ricevono notifica _(variante: la processa l'admin dalla propria coda)_.
- Il nuovo esaminatore riceve il toast di sblocco e vede comparire l'area di
  gestione esami.
- L'admin apre l'elenco dei titolari e vede la **catena**: chi ha concesso a chi
  e quando.
- L'admin **revoca** il ruolo al primo esaminatore: quello perde le voci di menu,
  ma gli esami che ha composto e **le certificazioni che ha rilasciato restano
  valide**.

## Use case 5 — Percorso di sblocco e override di debug

- Un player appena registrato accede: la voce "Esami" **non compare**.
- Nella dashboard gamification, fra le funzioni bloccate, vede "Esami" con
  "Completa altri 3 drill per sbloccare" e la barra di avanzamento a 0/3.
- Completa i drill: alla soglia riceve il toast di sblocco e la voce compare.
- _(variante debug)_ Lo sviluppatore, invece di completare i drill, attiva
  `gamification_override` su quell'utente dalla scheda admin: la voce compare
  subito.
- _(variante debug)_ Con `DEBUG_MODE=true`, dalla barra di debug usa "Diventa
  esaminatore": si auto-concede il grant e accede all'area esaminatore. La barra
  di debug mostra lo stato dei **due gate separati** (esaminatore sì/no,
  override sì/no), così si vede quale dei due sta bloccando la schermata.
- In produzione l'auto-concessione **non esiste**: 404, non 403.

## Use case 6 — Esame non superato, ripetizione e confini di permesso

- Un esaminatore certifica un esame come **non superato**.
- Il player lo vede nel profilo come tentativo certificato e non superato, e può
  **richiedere di ripeterlo** aprendo una nuova richiesta.
- Un esaminatore prova a chiedere un esame **che somministra lui**: rifiutato,
  già alla creazione della richiesta.
- Un esaminatore prova a **modificare un esame composto da un altro**: rifiutato,
  salvo che sia il creatore, un co-esaminatore di quell'esame, o admin.
- Un player prova ad avviare una sessione certificata **senza appuntamento
  accettato**: rifiutato.
- Un esaminatore prova a registrare punteggi **prima che il player abbia
  accettato l'inizio**: rifiutato — e non solo nella UI: anche via POST diretta.
- Un esaminatore che **non ha ancora sbloccato** `take_exam` apre comunque il
  catalogo e i propri esami — il ruolo e la progressione sono gate ortogonali —
  ma **non può sostenere** un esame.

## Use case 7 — Il profilo come storico dell'allenamento

- Un player apre il proprio profilo e trova la sezione **"Allenamento"**.
- Vede l'**elenco dei drill sostenuti**, ciascuno con il **miglior punteggio**
  ottenuto e il numero di tentativi _(variante: un drill superato/non superato
  mostra "Superato" invece del punteggio)_.
- Apre un drill e vede **tutti i suoi tentativi** in ordine cronologico, con
  l'**andamento nel tempo** _(variante: un solo tentativo → nessun andamento da
  mostrare)_.
- Sotto, l'**elenco degli esami sostenuti**: quelli certificati portano il badge
  **"certificato da …"** con data e sala, quelli in autonomia no.
- I drill svolti **dentro una gara** compaiono nello stesso elenco, indicando la
  gara di provenienza; quelli svolti dal catalogo indicano "Dal catalogo".
- Un altro utente che visita il profilo vede la stessa sezione, filtrata dalle
  impostazioni privacy già esistenti — e il default è **non mostrare**.

Estende UC7 di `UC01.md` («il player accede al suo profilo e vede lo storico di
tutti i match e di tutte le challenge fatte»), che prima di questo lavoro non era
soddisfatto: lo storico era **sempre vuoto**, per la somma di tre difetti
descritti in ADR-042.
