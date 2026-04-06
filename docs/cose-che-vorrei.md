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