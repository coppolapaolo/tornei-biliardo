# [077] Il limite di tempo è un riferimento visivo: interrompe il direttore

**Data**: 2026-10-06
**Stato**: Accepted
**Decisori**: Paolo Coppola (committente), Claude

## Contesto

Biliardo 74 organizza ogni lunedì una gara con questa formula: gironi
all'italiana, incontri al 3, **30 minuti per incontro, poi vale il punteggio
maturato**. Fino a questa data l'app chiudeva una partita **solo alla
distanza** (`Match.is_at_distance`): il tempo non esisteva.

Le domande da decidere erano quattro:

1. che cosa succede allo scadere: si chiude da sola, o no;
2. da quando si conta il tempo;
3. dove vive il limite, e come si cambia a gara avviata;
4. come si chiude una partita sotto la distanza, e che cosa vale un pari.

## Decisione

**1. La partita ha sempre una distanza; il limite di tempo le si affianca.**
Una partita che arriva alla distanza si chiude come sempre, anche a tempo
scaduto, e **non** porta il segno «a tempo».

**2. Il conto alla rovescia è solo visivo.** Allo scadere non succede niente
da sé: il timer passa a «Tempo scaduto +2'», la card del direttore passa
all'avviso e **sale fra quelle da guardare** (`direttore_view.partite_del_turno`).
È il direttore che va al tavolo e decide.

**3. Il tempo parte una volta sola**, e il fatto si scrive sulla partita
(`Match.timer_started_at`):

- con la regola **acchito**, quando si registra chi l'ha vinto
  (`ScoringService.register_lag`);
- con **«apre il primo giocatore»**, con il pulsante **«Avvia partita»**, che
  premono i due giocatori dal segnapunti o il direttore dalla card. Il
  direttore può premerlo con qualunque regola: è il rimedio quando i giocatori
  l'acchito non lo registrano.

Il server dà inizio e durata; il tempo che resta lo calcolano le pagine
(`static/js/conto_alla_rovescia.js`), correggendo lo scarto dell'orologio del
dispositivo con l'ora del server scritta nella pagina. La partenza è un evento
live (ADR-057, `timer_started` sulla partita e `match_updated` sulla gara),
scritto nella stessa transazione del fatto.

**4. Il limite è una regola come le altre (ADR-075).** Tre posti, la stessa
catena di `has_handicap`:

| Dove | Colonna | Valori |
|---|---|---|
| Campionato | `default_time_limit_minutes` | 0 = nessun limite (NOT NULL) |
| Gara | `time_limit_minutes` | NULL = come il campionato (gara singola: nessuno), 0 = senza limite, N |
| Partita | `time_limit_minutes` | fissato alla nascita da `fissa_regole`; NULL = nessuno |

Il campionato **propone** (si copia sulla gara quando nasce, e un cambio si
propone alle gare non avviate da `campionato/proposte.py`); la gara **decide**,
anche una gara singola; la partita **tiene** il valore con cui è nata. È in
`campi_modificabili.REGOLE`: a gara avviata si cambia e vale dal turno dopo.

**5. Interrompe il direttore** (a seguire, stesso ADR): «Interrompi partita»
chiude sul punteggio maturato, anche prima dello scadere (il foglio avverte
«mancano N minuti»). Chi è avanti vince; a parità c'è **pareggio dove il
pareggio è ammesso** — fuori dal tabellone — mentre nel tabellone il direttore
indica chi passa. La partita interrotta porta `closed_on_time` («a tempo» nei
risultati) e si corregge anche sotto la distanza.

**6. Fuori in questa versione**: partite a set, trio, X. Il valore resta
fissato anche lì (è la regola della gara in quel momento), ma
`tempo.limite_minuti` risponde None e nessuna schermata mostra il timer.

## Alternative Considerate

### Alternativa 1: allo scadere la partita si chiude da sola

**Descrizione**: un controllo (al poll o a ogni lettura) chiude la partita sul
punteggio maturato appena il tempo finisce.

- **Pro**:
  - nessuno deve ricordarsi di farlo.
- **Contro**:
  - in sala il tempo si ferma e riparte per mille ragioni (un tavolo occupato,
    una contestazione, una partita cominciata in ritardo): un orologio che
    chiude da solo sbaglia proprio quando serve un giudizio;
  - il rack in corso allo scadere va finito o no? Le regole di sala cambiano:
    deciderlo nel codice impone una regola che il direttore non ha scelto;
  - chiudere senza una richiesta vuol dire uno stato che cambia «da sé» fra
    due poll, in tre processi (ADR-057): un ordine di eventi difficile da
    garantire.

### Alternativa 2: il limite al posto della distanza

**Descrizione**: una partita «a tempo» non ha distanza; vince chi è avanti allo
scadere.

- **Pro**:
  - modello più semplice per la sola formula del lunedì.
- **Contro**:
  - la formula dice «al 3, poi vale il punteggio»: la distanza c'è;
  - tutto lo scoring (ADR-027, `Distance`) presuppone una distanza: toglierla
    vorrebbe dire un secondo percorso di chiusura in ogni strategia.

### Alternativa 3: il timer solo nel browser

**Descrizione**: il segnapunti fa partire un cronometro locale, senza scrivere
nulla.

- **Pro**:
  - nessuna colonna, nessuna migration.
- **Contro**:
  - avversario, direttore e schermo sala vedrebbero tre tempi diversi, o
    nessuno: il punto è che lo vedano tutti uguale.

## Conseguenze

### Positive

- Chi non usa l'opzione vede l'app di sempre: niente timer, niente pulsanti,
  nessuna riga nel regolamento.
- Funziona dentro un campionato e su una gara singola, con lo stesso campo.
- Un cambio del limite non tocca le partite già nate (ADR-075).

### Negative

- Il direttore deve guardare: una partita a tempo scaduto resta aperta finché
  qualcuno non la interrompe. È voluto, e la card glielo segnala.
- Con l'acchito, se i giocatori non lo registrano il tempo non parte: resta il
  pulsante del direttore.

### Rischi

- Il ritardo fra un evento e la pagina aperta (poll ogni tre secondi) fa
  arrivare la partenza con qualche secondo di ritardo all'avversario: il tempo
  però si calcola dall'inizio scritto sul server, non dall'arrivo dell'evento.

## Note Implementative

- `models/match/tempo.py`: la regola (`limite_minuti`, `scadenza`,
  `tempo_scaduto`, `avvia_conto_alla_rovescia`, `vista`, `evento_live`).
- `MatchService.avvia_partita` (`@transactional`): giocatori della partita o
  chi dirige; route `player.avvia_partita` e `admin.match.avvia_partita`.
- Il timer si disegna da un solo macro, `components/_conto_alla_rovescia.html`:
  punteggio della partita, tabellone, card del direttore, schermo sala.
- Il campo dei moduli è uno solo, `components/_campo_limite_tempo.html`
  (vuoto = nessun limite, 1–600 minuti, `LIMITE_DI_TEMPO_MASSIMO`).
- Migration `20261006_limite_di_tempo.py`. Nessun riempimento: le partite
  esistenti restano senza limite.
- Specifica: `SPECIFICHE.md`, «Limite di tempo»; presidi in
  `tests/new/unit/test_limite_di_tempo.py`, `test_limite_di_tempo_moduli.py`
  e `test_specifiche_conformita.py::TestIlLimiteDiTempo`.

## Emendamento (2026-10-06) — il limite di un singolo turno

Seconda tappa dell'attuazione. `RoundConfiguration.time_limit_minutes`
sovrascrive il limite per turno, come disciplina e distanza (ADR-027), ma con
**tre** stati invece di due: NULL = come la gara, 0 = senza limite per quel
turno, N minuti. Per questo `create_or_update` lo tratta a parte: `None`
passato esplicitamente toglie l'override (per gli altri campi vuol dire «non
toccare»), e non passarlo lo lascia com'è (`NON_TOCCARE`). La partita lo
riceve alla nascita: `fissa_regole` chiede a `tempo.limite_del_turno`, che
legge il turno prima della gara. Dalla route (`upsert_round_config`) `null`
toglie l'override e un valore fuori da 0–600 si rifiuta con 400.

L'interfaccia è quella dei turni su misura (`direttore/preparazione/_turni.html`),
che oggi esiste solo per Amalfi e casuale con più di un turno: per il girone
all'italiana e i tabelloni l'override si scrive solo dalla route.

## Emendamento (2026-10-06) — l'interruzione

Terza tappa: «Interrompi partita». Le regole stanno in un modulo solo,
`models/match/chiusura.py`: `motivo_non_interrompibile` (limite di tempo,
partita in gioco, non a set, trio o X), `esito` (chi è avanti vince; a parità
pareggio se `pareggio_ammesso`, altrimenti serve chi passa) e `chiudibile`
(alla distanza o interrotta). `MatchService.interrompi_partita` — solo chi
dirige la gara — scrive vincitore e `Match.closed_on_time`, poi completa con
`MatchValidationService.validate_and_complete`, che chiede `chiudibile`
invece della sola distanza. `awaiting_validation` resta com'è: una partita
interrotta non aspetta il direttore, la chiude lui.

Dove si legge il vincitore indicato: `DirectEliminationStrategy._winner_of`
leggeva già `winner_id`; `ScoreAggregator._process_regular_match` ora conta la
vittoria di chi passa su un pari. La correzione (`correction_service`) accetta
per le partite interrotte punteggi sotto la distanza, mai oltre; corretta
alla distanza la partita perde il segno, e nel tabellone un pari tiene chi
il direttore aveva fatto passare.

Un ruolo di arbitro, nominato nel piano, nell'app non esiste: «Interrompi» è
del direttore (`admin.match.interrompi_partita`, `{"director"}`).

## Riferimenti

- ADR-027 (override per turno), ADR-057 (eventi live), ADR-074 (conferme),
  ADR-075 (regole fissate sulla partita, il campionato propone).
- Piano «gironi multipli, limite di tempo, listino quote, ordinamenti», PR 1.
