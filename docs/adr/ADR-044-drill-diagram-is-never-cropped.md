# ADR-044 L'immagine di un drill è un diagramma, e un diagramma non si taglia

**Data**: 2026-08-16
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

L'immagine di un drill non è decorazione: **è** l'esercizio. Dice dove stanno le
bilie, dov'è la battente, quali buche contano. Il testo la presuppone — «dalla
posizione in foto, imbuca la bilia 8 dopo almeno tre sponde» non significa
niente senza la foto.

Tutte e cinque le superfici che la mostravano usavano `object-fit: cover`, che
riempie il riquadro **ritagliando** ciò che avanza:

| superficie | riquadro | ritaglio su una foto 1.74:1 |
|---|---|---|
| `thumb()` in `_challenge_bits.html` (12 template) | 1:1 | 43% della larghezza |
| miniatura del modale di gestione | 4:3 | 24% |
| card del catalogo | 4:3 | 24% |
| dettaglio del drill | 16:10 | 8% |
| dettaglio del tentativo | 1:1 | 43% |

Quello che si perde ritagliando in larghezza sono **le due teste del tavolo**,
cioè le sponde corte e le buche d'angolo: esattamente ciò che dà senso alle
posizioni. E non si vede: un tavolo tagliato somiglia a un tavolo.

Il ridimensionamento lato server era già corretto (`img.thumbnail` preserva le
proporzioni, `utils/image_paths.py:138`): il problema era interamente nel CSS,
ricopiato cinque volte in altrettanti `style=` — ed è così che una superficie
sistemata da sola avrebbe lasciato indietro le altre quattro.

Le foto reali stanno intorno a **1.74:1** (800×459, il tetto del resize), con
qualche quadrata caricata a mano.

## Decisione

**L'immagine di un drill si mostra intera, sempre**, anche a costo di due bande
vuote ai lati. La regola vive in un posto solo, `.c7-diagram` /
`.c7-diagram__img` nel tema, e le cinque superfici la usano invece di
riscriversela.

Il fondo del riquadro è `--c7-sunken`, che fa da passe-partout e regge anche il
segnaposto quando l'immagine manca o non si carica — è la stessa soluzione del
prototipo (`#9b`: riquadro affossato con il contenuto centrato).

I riquadri che ospitano l'immagine in grande passano a **16/9**, il rapporto più
vicino a quello reale delle foto: le bande restano un filo invece di essere
due fasce.

### Il dettaglio che non è un dettaglio: `position: absolute`, non `height: 100%`

La prima stesura usava `width: 100%; height: 100%; object-fit: contain`. Sulle
foto 1.74:1 funzionava, e sembrava finita.

Su una foto **quadrata** no: dentro un riquadro che prende l'altezza da
`aspect-ratio`, una percentuale non ha un'altezza *definita* su cui risolvere,
quindi l'immagine ripiegava sulla propria misura intrinseca, usciva dal riquadro
e veniva ritagliata da `overflow: hidden` — cioè **esattamente il bug che si
stava togliendo**, sopravvissuto alla correzione. Verificato nel browser, non a
occhio: `img 282×282` dentro `frame 282×159`.

L'immagine si posiziona quindi sul riquadro (`position: absolute; inset: 0`):
lì il box è quello del riquadro, definito, e `contain` fa il suo mestiere per
qualunque proporzione.

## Alternative considerate

### Ritagliare, ma con `object-position` sul centro del tavolo

**Descrizione**: tenere `cover` e spostare il punto di ritaglio.

- **Pro**: riquadri sempre pieni, nessuna banda.
- **Contro**: il centro del tavolo non è il centro dell'esercizio — le bilie
  che contano stanno spesso proprio ai bordi. E resta un ritaglio: sposta
  soltanto *quale* pezzo si perde.

### Riquadri a rapporto libero (l'immagine detta l'altezza)

**Descrizione**: niente `aspect-ratio`, la card cresce con la foto.

- **Pro**: nessuna banda, mai.
- **Contro**: in una griglia di card le altezze ballano a seconda delle foto
  caricate, e una quadrata fa una card alta il doppio delle vicine. Il
  prototipo mostra riquadri di altezza fissa.

### Ritagliare solo le miniature piccole

**Descrizione**: `contain` in grande, `cover` nelle miniature da 56px.

- **Pro**: la miniatura resta piena e leggibile come blocco di colore.
- **Contro**: due regole invece di una, e la miniatura è proprio il punto in
  cui il ritaglio è più aggressivo (43%). Chi sceglie un drill da un elenco lo
  riconosce dalla disposizione: una miniatura ritagliata gliela nasconde.

## Conseguenze

- Cinque superfici, una regola: `.c7-diagram` (riquadro) e `.c7-diagram__img`
  (immagine), più i modificatori `--thumb`, `--card`, `--full`. Il JS del
  modale di gestione usa le stesse classi invece di ricostruirsi lo stile.
- Le foto quadrate caricate a mano appaiono con due bande laterali. È il
  comportamento voluto: meglio una banda che una bilia in meno.
- `tests/new/unit/test_drill_diagram_not_cropped.py` presidia le cinque
  superfici e fallisce su qualunque `object-fit: cover` ricompaia lì.
- Il ritaglio verticale delle card è ora deciso dal rapporto 16/9 invece che
  dalla foto: una futura foto molto più alta che larga avrebbe bande generose.
  Se capiterà, si taglia il **caricamento** (validando le proporzioni), non la
  visualizzazione.

## Open Items

1. **Rapporto in caricamento**: oggi si accetta qualunque proporzione e si
   compensa in visualizzazione. Validare in upload — o generare una versione
   16/9 con passe-partout cotto dentro — toglierebbe le bande alla radice.
2. **Ingrandimento a schermo intero**: sul dettaglio la foto è alta al massimo
   380px. Su un diagramma fitto può non bastare, e un tap per ingrandire non
   c'è.
