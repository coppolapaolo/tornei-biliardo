# Elenco funzionalità che vorrei implementare

In questo file scrivo le funzionalità che vorrei implementare, man mano che mi vengono in mente. Per ognuna di queste occorre
1. controllare che non sia già implementata. Nel caso segnarla come fatta
2. se non è implementata, fare una ricerca nel codebase per vedere se è già stata implementata in parte
3. usare bmad per raccogliere i requisiti e fare un piano di implementazione e poi implementarla

## Rivedere il sistema di gamification
Voglio assicurarmi che il sistema copra tutte le funzionalita'. Che sia configurabile lato amministratore. Al momento mi sembra troppo poco funzionale. Forse la grafica e' sbagliata o vecchia. Anche i livelli non sono chiari. Probabilmente vanno rivisti i percorsi "di esplorazione" attraverso i quali gli utenti scoprono nuove funzionalita' man mano che aumentano di livello. Il ritmo deve essere giusto per spingere a tornare. 

## Rivedere il sistema di kpi
L'amministratore e' in grado di capire se la community sta andando bene e se ci sono problemi? Ci sono metriche che dovrei monitorare? Come posso usarle per migliorare la piattaforma? 

## Sistema di handicap
Aggiungere alle gare e ai campionati la possibilita' di definire un sistema di handicap. Il livello di gioco puo' essere impostato a livello di gara, di campionato o generale. L'handicap impatta sul calcolo del punteggio. Ho in mente almeno due tipi:
1. giocatori in diverse categorie, ad esempio A, B, C e handicacp uguale alla distanza tra categorie con rack in piu' per chi ha categoria maggiore (ad esempio A vs C -> 2 rack in piu per A)
2. handicap basato su rating. Questo non mi e' chiarissimo, ma dovrbbe essere un handicap tale per cui la probabilita' di vittoria sia sempre 50%. Non mi e' chiaro se funziona solo con punteggi che contano il numero di biglie imbucate (cosa che al momento in cui scrivo non e' implementata), oppure anche con altri tipi di punteggi. Mi sembra che APA (American Pool Association) usi un sistema di questo tipo.

## Georeferenziazione che funzioni in tutto il mondo, senza admin nel ciclo
L'ambizione e' che il sito sia utile ovunque, non solo dove lo sviluppo e lo provo io. Oggi lo testo a Udine, ma se domani lo pubblicizzo e si iscrive uno di Sydney, o tre giapponesi, le community locali devono poter emergere **da sole**: senza che io, da qui, debba creare la loro sala o approvare il loro direttore. Il sistema attuale (ADR-034) non lo permette, e non per un bug: e' proprio il modello, disegnato quando l'orizzonte era nazionale.

Oggi la catena e' `citta' scritta a mano -> sale con quelle coordinate -> centroide`. Quindi una citta' "esiste" solo se un admin ha gia' creato li' almeno una sala **e** le ha digitato dentro latitudine e longitudine a mano. Chi si iscrive a Sydney: non ha centroide (`AvailabilityService.city_centroid_for`), vede l'elenco delle sale italiane senza distanze (`routes/individual_match/availability.py:182-190`), non puo' dichiarare disponibilita' perche' dopo ADR-033 sono solo per sala, ha una classifica di zona con dentro solo se' stesso, e non puo' nemmeno emettere un segnale-domanda (`demand.create_signal` e' gated a `{director}`). Per sbloccarsi servirebbero una sala (`routes/admin/venue.py:226`, `@admin_required`) e un direttore approvato (`routes/admin/user.py:88`, admin-only). Cioe' io. I tre giapponesi invece falliscono anche fra loro: la zona si calcola per **uguaglianza testuale** fra citta' (`community_leaderboard_service.py:62-84`), quindi `東京`, `Tokyo` e `Tōkyō` sono tre zone disgiunte.

L'idea e' invertire la gerarchia: non piu' `citta' (stringa) -> sale (admin) -> coordinate`, ma `coordinate (dall'utente) -> zona metrica -> nome`. Il nome della zona diventa un'etichetta da mostrare, mai una chiave su cui fare join. Decisioni gia' prese, da confermare quando ci metto mano:

- **La posizione si sceglie su una mappa** (pin, tipo Leaflet, con GPS come scorciatoia e ricerca per nome opzionale via Photon). Cosi' non c'e' piu' nessuna stringa da validare o normalizzare: l'output e' direttamente lat/lng, e tutto il problema "la citta' esiste davvero?" sparisce alla radice. Nota: le tile arrivano per forza da un servizio esterno, quindi serve aprire la CSP su `img-src` (e' il punto dove il progetto e' gia' inciampato con GA4) e serve un ripiego se il tile server non risponde. Terrei l'URL delle tile in una env var, per cambiare provider senza toccare il codice quando il traffico cresce.
- **Si persiste solo il quadrante**, coordinate arrotondate a una griglia da 5-10 km, mai il punto esatto. Basta per zone da 20-30 km e non identifica nessuno. Questo rinegozia ADR-034 §2 ("nessuna coordinata utente in DB"), che e' il vincolo da cui discende tutta la dipendenza dalle sale — e quindi dall'admin. Il precedente in casa c'e' gia': `DemandSignal` persiste lat/lng con cooldown per riquadro arrotondato.
- **La zona diventa metrica pura**: utenti entro R km dal proprio quadrante. Spariscono `cities_in_zone` e il confronto testuale. `home_city` sopravvive come etichetta decorativa nel profilo.
- **Le sale smettono di essere il prerequisito per esistere**: con lo stesso selettore su mappa un giocatore puo' proporre una sala mettendoci il pin, invece di aspettare che le digiti io. Un solo componente di interfaccia rimuove tre blocchi.
- **I direttori emergono da soli**: quando N segnali-domanda si accumulano in una zona che non ha direttori, chi si candida viene promosso automaticamente, con poteri limitati alla propria zona. L'infrastruttura di ADR-036 c'e' gia', ma oggi l'escalation finisce agli admin — che e' esattamente cio' che non scala fuori dal mio fuso orario.

Tocca ADR-034 (§2 e §4), ADR-033, ADR-036 e ADR-037: e' materia da ADR nuovo, non da patch. Due cose minori da raccogliere nello stesso giro: `bounding_box` in `utils/geo.py:43-47` guarda i poli ma **non l'antimeridiano** (la longitudine non fa wrap: si rompe per Figi, Nuova Zelanda orientale, Kiribati), e le traduzioni oggi sono solo `it`/`en`.