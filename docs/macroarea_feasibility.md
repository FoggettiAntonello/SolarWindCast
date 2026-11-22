# Fattibilità della macroarea Sud + Calabria — 10 novembre 2026

Aggiornamento 11 novembre: [raccordo Sud/Rossano verificato sui campioni](south_rossano_reconciliation.md).
Le conclusioni sotto descrivono lo stato precedente a questa verifica aggiuntiva.

[Presentazione HTML](../reports/macroarea_feasibility_20261110/presentazione.html)
e [audit JSON](../reports/macroarea_feasibility_20261110/audit.json).

## Esito

La somma osservata Sud + Calabria è tecnicamente fattibile sui campioni
successivi al 2021 per solare ed eolico a terra. Il raccordo storico non è
ancora validato: i vecchi poli e la componente offshore richiedono regole
documentate. Nessun modello è stato eseguito, nessuna prestazione migliorata
o promessa. La zona Sud ufficiale resta il target dei risultati già esistenti.

La macroarea proposta rappresenta Molise, Puglia, Basilicata e Calabria:
è un'aggregazione costruita nel progetto, non una singola zona di mercato attuale.
Il semplice elenco di regioni non certifica l'inclusione di ogni nodo/polo
nelle risposte aggregate del passato.

## Verifiche effettive e prototipo

Quattro nuovi campioni A75/A16, un giorno ciascuno:

- Sud e Rossano: 30 dicembre 2020, evitando di attraversare il cambio di configurazione;
- Calabria: 1 gennaio 2021 e 1 ottobre 2026.

Riutilizzati Sud del 1 gennaio 2021 dall'audit precedente e Sud del 1 ottobre
2026 dai Parquet già verificati. Un errore di trasporto sul secondo campione
Calabria è conservato in `failed_requests/IT_CALA_20261001_attempt01`, hash invariato;
il tentativo successivo è riuscito. Non si è riscaricato il resto.

Domini configurati: Sud `10Y1001A1001A788`, Calabria `10Y1001C--00096J`.
Rossano storico: `10Y1001A1001A77A`. Verificati i domini effettivamente
restituiti e gli hash. Le risoluzioni native sono riportate nel JSON;
il parser decodifica A03 e aggrega solo ore native complete.

| Giorno UTC | Componente macroarea | Ore valide | Energia osservata MWh |
|---|---|---:|---:|
| 2021-01-01 | Solare | 24/24 | 9.495,00 |
| 2021-01-01 | Eolico a terra | 24/24 | 31.013,00 |
| 2026-10-01 | Solare | 24/24 | 22.083,75 |
| 2026-10-01 | Eolico a terra | 24/24 | 11.179,50 |

Sono energie di giornate osservate, non totali mensili o previsioni.
I record orari del prototipo sono salvati in `prototype_hourly.json`.
L'eolico totale terra + mare ha zero ore complete in entrambi i campioni,
per la componente offshore non restituita. Questo non significa produzione
totale nulla: significa dato non ricostruibile con la politica attuale.

`macroarea.py` implementa una somma stretta di osservazioni MW tra domini
espliciti e univoci, sullo stesso target, frequenza e indice UTC. Un NaN
in un'area lascia NaN nel totale. Non aggrega covariate o quantili, non
riempie zeri strutturali e non decide la geografia storica: il chiamante
deve documentare disgiunzione, perimetro e validità temporale delle aree.

## Scoperta sul polo Rossano

Il campione del 30 dicembre 2020 restituisce nel dominio Rossano valori
**positivi** di solare ed eolico: 103 MWh e 1.003 MWh nella giornata,
con 24 ore valide per ciascuna fonte. Non è quindi sicuro assumere che
questo polo sia irrilevante per i due target o che contenga solo dati termici.
L'assenza di impatto rinnovabile non si deduce dal nome di una centrale.

Prima di adottare una ricetta tipo Sud storico + Rossano per il 2019–2020,
occorre verificare il contenuto delle aggregazioni e impedire doppi conteggi.
La distinta risposta ENTSO-E e la distinta zona sono evidenza da esaminare,
non una prova completa della ricostruzione territoriale per l'intero periodo.
La proposta illustrativa «prima del2021 = solo Sud storico» non è quindi
una ricetta già validata.

Prima del 2019 si aggiunge il raccordo dei poli Foggia/Brindisi e del nodo
Gissi, spostato verso Centro-Sud nella revisione. Non basta aggiungere
indiscriminatamente tutti i poli: va controllata la pertinenza al territorio.

## Offshore e confini temporali

Nei campioni Calabria manca B18 (offshore), mentre B16 e B19 sono disponibili.
Non si assume che B18 assente significhi zero. Per il target terra + mare
serve una politica esplicita, con fonti e periodo di assenza fisica verificato,
distinta da un buco di pubblicazione. Tale politica non è stata applicata.

Il cambio GME è definito per giorno di flusso. L'eventuale raccordo operativo
deve verificare l'istante UTC corrispondente e gestire il mese UTC che attraversa
la transizione. Non è stato codificato automaticamente un cambio a00UTC del
1 gennaio. Le due giornate prototipo sono interamente successive alla transizione.

I quantili mensili dovranno essere previsti direttamente sulla nuova serie
aggregata, non sommati da modelli distinti. Sono necessari un nuovo dataset
identificato chiaramente e un protocollo separato, preservando lo storico Sud.

## Percorso consigliato

1. Chiudere il raccordo Sud/Rossano per il 2019–2020 e la politica offshore,
   con regole scritte prima di qualsiasi nuovo esperimento sui risultati.
2. Se verificato, proporre l'acquisizione a lotti per gennaio 2019–ottobre 2026:
   **94 mesi di calendario possibili**, non copertura già accertata.
   Date, budget di richieste e approvazione del cambio geografico operativo
   restano da concordare prima del download completo.
3. Valutare il pre-2019 solo con ulteriore ricostruzione dei poli. Non ricercare
   una geografia che vinca sul vecchio test: la scelta va motivata dal caso d'uso.
4. Dopo il dataset verificato, backtest comune con baseline e Timestral,
   dichiarando i limiti della selezione retrospettiva e mantenendo una futura
   verifica su previsioni registrate prima degli esiti.

## Fonti primarie

- [ARERA 297/2020/R/eel, tabella 2](https://www.arera.it/fileadmin/allegati/docs/20/297-20.pdf):
  confronto territoriale prima e dopo la separazione Calabria.
- [ARERA 386/2018/R/eel](https://www.arera.it/fileadmin/allegati/docs/18/386-18.pdf):
  punti di produzione dei poli e decorrenza della revisione del 2019.
- [Terna, Bilancio consolidato 2018](https://www.terna-reports.it/2018/assets/pdf/Integrato_ITA/BilancioConsolidato.pdf):
  effetti della revisione dal 2019, accorpamenti e nodo Gissi.
- [entsoe-py](https://github.com/EnergieID/entsoe-py/blob/master/entsoe/entsoe.py)
  e [pandas sum/min_count](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.sum.html):
  documentazione verificata prima dell'uso.

La prima apertura di alcuni indirizzi ARERA non era disponibile al browser;
le fonti sopra sono state effettivamente aperte in seguito. Il Piano Terna2021
di grandi dimensioni non era leggibile con lo strumento: non si attribuisce
a una sua lettura integrale una conclusione non verificata.

341 test superati, uno smoke opzionale escluso, dipendenze coerenti e Ruff pulito.
Controllate indipendentemente somme energetiche, UTC, mancanti e hash nuovi/precedenti.
Report offline con sei righe di risultati e layout mobile verificato.
Nessuna acquisizione massiva, uso di token nel report, modifica dei dataset
precedenti o inizializzazione Git. Il prototipo non certifica interi anni di dati.
