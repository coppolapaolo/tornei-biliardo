# ADR-043 L'orario è quello di chi legge, e il fuso si deduce senza chiederlo

**Data**: 2026-08-15
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

La piattaforma nasce internazionale — l'interfaccia è tradotta in inglese, non
solo scritta in italiano — ma ogni orario usciva in `Europe/Rome`, con il nome
del fuso **scritto a mano** dentro tre filtri di `utils/jinja.py`.

Per un giocatore fuori dall'Italia questo non è un difetto di presentazione: è
un dato falso. «21:00» è un orario perfettamente plausibile, quindi non c'è
niente che possa insospettire chi lo legge. Nessuna eccezione, nessun log, solo
un match a cui ci si presenta con un'ora di scarto.

Lo stato di partenza era anche **incoerente con sé stesso**, il che rendeva la
cosa difficile da vedere:

| meccanismo | fuso | superfici |
|---|---|---|
| `\|datetime_local` e affini (server) | `Europe/Rome` fisso | 36 template |
| `data-utc` + `TourneyUtils.utcToLocal` (browser) | quello del browser | 5 template |
| `static/js/datetime-local.js` | quello del browser | **0 — non incluso da nessuna parte** |

Il terzo file fa esattamente la cosa giusta ed è codice morto da sempre: nessun
template lo carica. Le iscrizioni, per conto loro, convertivano al fuso del
browser **in scrittura** (campi nascosti `*_utc` riempiti da JavaScript) mentre
la stessa pagina le rimostrava in ora italiana — cioè il valore usciva da un
fuso e rientrava da un altro.

Su `User` non esisteva nessuna colonna per il fuso.

## Decisione

### L'orario di riferimento è quello di chi legge

Non quello della sala, non quello del direttore che ha creato la gara: quello
della persona che in questo momento sta guardando lo schermo. È il modello di
Google Calendar, ed è quello che rende un'app utilizzabile da fusi diversi senza
che nessuno debba fare aritmetica.

L'alternativa seria era il **fuso del posto dove si gioca** («21:00 a Milano
resta 21:00 per tutti»), che per un evento fisico ha una sua logica. È stata
scartata perché richiede un fuso su ogni sala e su ogni gara — un dato in più da
raccogliere e da tenere corretto — mentre il fuso del lettore si deduce da solo.

Sul DB non cambia niente: i naive restano UTC (`utc_now()`, convenzione di
progetto). Cambia solo chi decide in cosa convertirli.

### Il fuso non si chiede: si deduce dal browser

Chiederlo in fase di registrazione sarebbe un campo in più in un modulo, per un
dato che l'utente spesso non sa nominare e che il browser conosce con certezza.
Si legge quindi da `Intl.DateTimeFormat().resolvedOptions().timeZone`.

Resta modificabile a mano il giorno in cui servirà: la colonna è un nome IANA,
non un flag.

### Ma va **salvato**, non solo dedotto al volo

È la parte non ovvia della decisione, ed è quella che ha determinato la forma di
tutto il resto.

Un fuso dedotto e non scritto esiste solo finché c'è una pagina aperta. Ma gli
orari escono anche da posti dove nessuna pagina esiste:

- i **promemoria dei match** e le notifiche degli appuntamenti d'esame nascono
  in uno scheduled task orario, ore dopo, per un destinatario che in quel
  momento non è collegato;
- le **email** (oggi verifica e recupero password; domani, prevedibilmente,
  qualcosa con un orario dentro) non eseguono JavaScript: Gmail, Outlook e Apple
  Mail scartano i `<script>`, quindi il trucco «mando UTC e lascio riscrivere al
  client» lì non funziona.

Quindi: colonna `user.timezone`, nome IANA, `NULL` = mai dedotto.

`NULL` e `"Europe/Rome"` sono due cose diverse e devono restare distinguibili.
Il primo si correggerà da solo al prossimo accesso; il secondo, scritto per
backfill su tutti gli account esistenti, resterebbe sbagliato per sempre per chi
sta altrove. Per questo la migration **non fa backfill**: indovinare il fuso da
un DB non si può, e scrivere un valore plausibile al posto di «non lo so» è il
modo di rendere permanente un errore.

### Si verifica a ogni accesso, si scrive solo quando cambia

Due punti, per due situazioni diverse:

1. un campo nascosto nel form di login, così la **prima** pagina della sessione
   è già nel fuso giusto invece di essere l'ultima in quello vecchio;
2. una chiamata a `POST /auth/timezone` dal guscio, che parte **solo** quando il
   browser dice qualcosa di diverso da quello che è in colonna. Copre le sessioni
   riprese da «ricordami» (che un login non lo fanno) e chi si sposta di fuso a
   sessione aperta.

Il valore arriva da un client, quindi si valida contro
`zoneinfo.available_timezones()`. Un nome inventato si scarta in silenzio
tenendo quello di prima: scritto in colonna solleverebbe a ogni pagina che
mostra un orario, cioè quasi tutte.

### Un messaggio che contiene un orario si scrive per destinatario

È il costo vero di questa decisione, e vale la pena nominarlo.

Le notifiche cuociono il testo dentro la riga: `create_bulk_notification`
riceveva **una** stringa per N destinatari. Con un fuso per lettore quella
stringa è giusta per uno solo di loro. I due punti che portano un orario — il
promemoria del match e le notifiche di appuntamento d'esame — costruiscono ora
il messaggio per ciascun destinatario (`ExamRequestService._notify` accetta una
funzione dell'id, oltre a una stringa già fatta).

La soluzione strutturale sarebbe tenere l'istante sulla notifica e formattarlo
alla lettura. Non è stata fatta ora: cambia il modello delle notifiche per un
guadagno che oggi riguarda due messaggi su decine. È annotata sotto.

## Conseguenze

- `utils/local_time.py` è l'unico posto che conosce un fuso. `resolve_timezone()`
  risponde per il lettore corrente, `resolve_timezone_for_user_id()` per un
  destinatario preciso. `Europe/Rome` compare una volta sola, come
  `FALLBACK_TIMEZONE`.
- I 36 template che usano `|datetime_local` non sono stati toccati: cambia il
  filtro, e li segue.
- Chi non ha ancora un fuso (anonimo, account vecchio, browser che non lo dice)
  legge in ora italiana — cioè esattamente come prima. Il cambiamento non
  peggiora nessun caso esistente.
- `static/js/datetime-local.js` era codice morto, ed è stato anche **superato**:
  la conversione la fa il server, che è l'unico posto che può farla anche fuori
  da una pagina. Rimosso insieme a `TourneyUtils` e ai sei attributi `data-utc`
  che sovrascrivevano lato client il testo già reso dal server.
- Il vincolo «un solo modulo conosce un fuso» ha ora un **presidio**:
  `test_only_one_module_knows_what_a_timezone_is` cammina l'AST di `models/`,
  `routes/` e `utils/` e fallisce su qualunque `ZoneInfo(...)` costruito fuori
  da `utils/local_time.py`. Serviva: dopo la prima stesura ne erano rimasti due
  — le ore di silenzio delle notifiche, valutate in ora italiana per chiunque, e
  `|date_local`, che non convertiva affatto e vicino a mezzanotte mostrava il
  giorno prima.

## Open Items

1. ~~**`datetime-local.js` e `TourneyUtils.utcToLocal`**~~ — fatto: rimossi
   entrambi, con i cinque template che usavano `data-utc`.
2. **Notifiche con l'istante invece del testo**: formattare alla lettura invece
   che alla scrittura toglierebbe la necessità di comporre per destinatario, e
   renderebbe corretti anche i messaggi già scritti quando un utente cambia fuso.
3. **Il fuso della sala**: scartato come riferimento primario, ma resta utile
   come *informazione aggiuntiva* («20:00 da te — 21:00 in sala») per chi legge
   da un altro paese. Richiede un fuso su `BilliardHall`.
4. **Modifica manuale nel profilo**: oggi il fuso è solo dedotto. Chi viaggia
   spesso potrebbe volerlo fissare.
