# Il campionato concluso — stato al 2026-09-14

Disegni di come si presenta un campionato **finito**: vetrina pubblica, pagina
del direttore, pagina pubblica dentro l'app. Qui ci sono solo i disegni e le
decisioni: il codice arriva in PR separate.

| Cosa | Dove |
|---|---|
| Canvas dei disegni (4 pagine) | <https://claude.ai/code/artifact/5dac2f9e-6151-469f-9c54-bdc5553e418a> |
| Sorgenti degli artboard | `sorgenti/gen.py` (vetrina), `sorgenti/gen_pagine.py` (pagine dell'app, riusa i pezzi di `../canvas-gara-direttore/sorgenti/gen_fasi.py`) |

Per rigenerare tutto, artboard e `canvas.json`:

```bash
python docs/redesign-7c/campionato-concluso/sorgenti/gen_pagine.py
```

## Il problema

Su un campionato concluso nessuna pagina diceva **chi ha vinto**. La vetrina
aveva in cima solo «Campionato concluso», e il vincitore andava dedotto da una
classifica «dopo N gare» che veniva dopo il calendario. In fondo restava il
riquadro delle iscrizioni. La pagina del direttore diceva «Playoff Elite:
vince X», cioè il vincitore della finale, che non è per forza il campione
(ADR-053, `campionato_plus_playoff`). La pagina pubblica era ancora quella
Bootstrap.

## Le decisioni

1. **Il campione è il primo della classifica finale**, che segue già
   `final_ranking_mode`. Non è il vincitore della gara di playoff.
2. **Il vincitore dei playoff si mostra come quello delle altre gare**: la
   finale sta nel calendario con «Vince X» / «ha vinto X». Nessun pulsante
   dedicato.
3. **Forma A, il campione sulla targa.** Nella vetrina sta dentro la targa
   scura, sotto il titolo, con secondo e terzo sotto. Nella pagina del
   direttore sta nella fascia accento. Le alternative B (podio a tre posti come
   la gara conclusa) e C (il podio dentro la classifica) sono nella quarta
   pagina del canvas.
4. **Correzioni comuni.** La classifica si chiama «Classifica finale» e, sul
   telefono, viene prima delle gare. Sparisce il riquadro delle iscrizioni.
   A playoff conclusi la classifica perde la zona playoff e le frecce di
   tendenza. Su desktop la vetrina mette la classifica nella colonna di
   destra.
5. **Le gare si contano «5 + finale»**: la finale non è una delle gare
   previste. Oggi la pagina del direttore scrive «3 di 2».
6. **Vetrina e pagina del direttore in una sola PR**, il conteggio in una PR
   a sé.
7. **La pagina pubblica** (`/campionato/<id>/public`) all'utente sembra
   ridondante con la vetrina, «a meno che non ci siano casi in cui la vetrina
   non c'è». Il disegno `Pubblica*` resta come riferimento se servisse
   tenerla.

   **Cosa è emerso il 14/09.** La vetrina esiste per ogni campionato vero:
   - il token l'ha assegnato la migration `20260830_vetrina_campionato`;
   - la prova non ha pagina pubblica né in un posto né nell'altro;
   - la matrice dei ruoli è la stessa.

   Resta però un caso senza risposta pulita: **la pagina pubblica è l'unico
   posto in cui un giocatore vede la classifica completa e la zona playoff**.
   - La vetrina si ferma a 8 righe e non ha la zona.
   - La pagina del direttore è riservata a chi dirige.
   - Le tessere campionato e playoff della dashboard portano lì apposta.

   Per chi è entrato nell'app c'è una differenza in più: la vetrina esce dalla
   struttura dell'app, senza barra laterale né navigazione, e le sue gare
   passano da `/g/<token>`.

   Decisione aperta:
   - **arricchire la vetrina** (classifica completa, zona playoff, link diretti
     per chi è entrato) e poi reindirizzare;
   - **tenere le due pagine** con ruoli distinti: la vetrina per chi arriva da
     fuori, la pubblica portata in 7c per chi usa l'app.

   Nel frattempo si corregge un difetto trovato strada facendo: la pagina
   pubblica di un campionato eliminato rispondeva 200.
