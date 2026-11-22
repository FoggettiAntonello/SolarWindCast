# Verifica dei risultati prima del portfolio — 14 novembre 2026

[Dati della verifica](../reports/readiness_review_20261114/assessment.json)
e [presentazione](../reports/readiness_review_20261114/presentazione.html).

## Giudizio attuale

Il progetto ha fondamenta tecniche verificate e segnali di utilità, ma non
dimostra ancora un vantaggio generale e stabile di Timestral rispetto alle
baseline. Non presentarlo come soluzione operativa validata o attribuirgli
risparmi economici non misurati. Una valutazione di assunzione non si può
garantire con una soglia numerica: i criteri sotto sono proposte del progetto,
non requisiti universali delle aziende.

L'utente ha approvato la semplificazione, chiedendo di verificare prima la
qualità dei risultati. Nessun nuovo download, training o backtest in questo
passaggio. La presentazione finale del portfolio è rinviata al riesame.

## Risultati ricontrollati sui forecast salvati

Hash di risultati e previsioni Step 11/12 verificati; MAE e numerosità del
periodo di test ricalcolati per tutti i modelli. Tutte le varianti, compresa
la baseline stagionale con errori rolling, devono restare nel confronto.

| Target Sud | Mesi test | Migliore Timestral nel test contro migliore baseline nel test, MAE | Variante con MAE sviluppo minimo: risultato sul test contro la stessa baseline |
| --- | ---: | ---: | ---: |
| Solare | 23 | +11,62% (peggiora) | +11,62% |
| Eolico terra + mare | 24 | -8,93% | +4,38% (peggiora) |
| Carico | 24 | +0,06% (sostanziale parità) | +24,75% (peggiora) |
| Carico residuo | 23 | -13,13% | -5,78% |

Segno negativo = meno errore. I migliori nel test sono riepiloghi descrittivi,
non modelli selezionati prima degli esiti. La seconda colonna di confronto è
un audit retrospettivo della regola «minimo MAE sviluppo», non una nuova
selezione operativa né un protocollo che risultasse preregistrato allora.
La baseline migliore nel test è anch'essa un riferimento descrittivo severo;
una futura baseline operativa va fissata prima della valutazione.

Sviluppo comune originario: 11 casi per solare/carico, solo 4 per eolico/residuo
nel riepilogo originale Step 11/12. Non confonderlo con gli 11 casi del
successivo screening contesti o i 16 forecast della calibrazione estesa.
Le due selezioni non hanno gli stessi denominatori.

Il solare 28M/calendario migliora rispetto alla sola ripetizione dell'anno
precedente, ma la baseline con errori rolling ha MAE 29.156,02 MWh contro
32.544,11 di Timestral. Timestral ha invece pinball inferiore (7.520,72 contro
7.943,19 MWh), con copertura 80% pari a 17/23 e copertura 90% pari a 19/23:
un punteggio migliore non dimostra che le probabilità dichiarate siano calibrate.

Sull'eolico il 5M/calendario è interessante nel test, ma la variante con MAE
sviluppo minimo era un'altra. Sul residuo il -13,13% del 5M è promettente ma
non rappresenta l'esito di una selezione congelata su un test mai visto.
Il vecchio test è già stato esaminato: ripeterlo non lo rende indipendente.

La calibrazione eolica controllata rimane esplorativa: nove mesi valutabili,
pinball -3,83% rispetto allo stesso candidato non calibrato, mediana invariata;
nessuna superiorità complessiva sul riferimento a 24 mesi dimostrata.

## Criteri da fissare prima di un eventuale ultimo esperimento

1. Un target, una geografia e un candidato fissati; confronto con tutte le
   baseline pertinenti sugli stessi mesi, senza scegliere finestre favorevoli.
2. Come soglia pratica proposta, almeno -5% di MAE rispetto al riferimento
   scelto sullo sviluppo, con RMSE e pinball non peggiori. Il 5% non è una
   soglia statistica o di assunzione. Riportare anche ogni baseline più forte
   emersa nel riepilogo, senza nasconderla.
3. Riportare errori per mese, vittorie/sconfitte, copertura e ampiezza degli
   intervalli; una copertura ottenuta allargando molto le bande non basta.
   Conservare i criteri più specifici del protocollo approvato, senza allentarli
   retroattivamente per promuovere un risultato già visto.
4. Tutti gli esiti di una nuova scelta sui periodi già esaminati restano
   esplorativi. Separare il piano di future emissioni registrate prima degli
   esiti dalla consegna del portfolio: una conferma prospettica richiede tempo.
5. Riproduzione dei risultati principali da comandi persistenti e verifica
   in ambiente pulito prima della consegna. I test locali da soli non
   certificano il setup da zero o la riproducibilità di ogni acquisizione recente.

## Verifica tecnica effettuata e percorso contenuto

`scripts/check.ps1`: 348 test superati, uno smoke reale facoltativo escluso,
dipendenze coerenti e Ruff senza errori. Nessun test o dato eliminato.
L'ambiente pulito non è stato ricreato in questa verifica.

Congelare il progetto principale sulla zona Sud e sul totale mensile
solare/eolico terra + mare. Macroarea Calabria come estensione documentata:
i suoi dati attuali sono onshore e non dimostrano nuovi risultati previsivi.
Altri modelli, pre-2021, fine tuning, meteo aggiuntivo e Streamlit rinviati;
resta l'HTML come interfaccia prevista per la chiusura.

Prossimo passo consigliato: preparare un solo protocollo finale eolico Sud,
riusando il candidato 28M/calendario/12 e il calibratore già studiati come
riferimenti, con analisi degli errori e budget chiuso prima di qualsiasi
eventuale correzione. Non autorizza nuove inferenze né un adattamento oggi.
Se non emerge un vantaggio verificabile, mantenere una baseline come opzione
utilizzabile e Timestral come confronto sperimentale, senza fabbricare una
vittoria. La consegna dovrà esplicitare l'ambito di utilità e i limiti.
