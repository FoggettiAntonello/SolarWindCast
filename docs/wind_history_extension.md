# Estensione delle origini eoliche — 10 novembre 2026

L'utente ha autorizzato di procedere con il primo passo proposto: recuperare
le cinque origini già ammissibili nei dati presenti, prima di estendere lo
storico con nuovi download. [Report HTML](../reports/wind_calibration_extended_20261110/presentazione.html).

## Che cosa è stato eseguito

Cinque nuove inferenze Timestral 28M/calendario/12: luglio, agosto, settembre,
ottobre e novembre 2023. Verificati protocollo, dati preparati e checkpoint
locali; nessun download, GPU o aggiornamento dei pesi. Il lotto mancante deve
coincidere esattamente con le cinque origini configurate, altrimenti il comando
si interrompe. Nessuna ricerca di altre taglie, contesti o iperparametri.

Le nuove cinque previsioni si aggiungono alle undici esistenti, conservate
identiche. Il precedente esperimento e la precedente calibrazione non sono
sovrascritti. Lo sviluppo del candidato passa a 16 origini, luglio 2023–ottobre
2024; dopo il warm-up sono valutabili **nove mesi, febbraio–ottobre 2024**.

È stato riutilizzato lo stesso calibratore con minimo sei errori, lookback24,
scala0,5–1,5, penalità0,05 e mediana invariata. Il programma confronta le
impostazioni con quelle salvate prima della prima calibrazione e rifiuta
cambiamenti. Per ogni emissione utilizza solo etichette già disponibili al
cutoff, escludendo il mese ancora in corso; gli errori storici passano da
sei nella prima calibrazione valutabile a quattordici nell'ultima.

## Risultati sui nove mesi comuni

| Metrica | 12 mesi originale | 12 mesi calibrato | 24 mesi riferimento |
|---|---:|---:|---:|
| MAE MWh | 96.429,85 | 96.429,85 | 117.926,70 |
| Pinball MWh | 32.120,82 | 30.890,50 | 30.806,51 |
| Copertura80 | 9/9 | 8/9 | 8/9 |
| Ampiezza80 MWh | 659.228,61 | 613.809,99 | 534.696,28 |
| Copertura90 | 9/9 | 9/9 | 9/9 |
| Ampiezza90 MWh | 929.326,47 | 865.303,59 | 719.687,40 |

Rispetto allo stesso candidato non calibrato, pinball inferiore del **3,83%**,
intervalli circa **6,89%** più stretti, MAE e RMSE centrali identici.
Il riferimento a 24 mesi conserva una pinball leggermente migliore e bande
più strette: non è dimostrata una superiorità complessiva del candidato calibrato.
Nove casi restano meno dei dodici previsti dal requisito prudenziale; anche
raggiungere dodici non darebbe automaticamente garanzie statistiche.

## Controllo sui quattro mesi precedenti

Per separare il cambio di storico dal cambio di periodo, il report conserva
anche un confronto ristretto a luglio–ottobre 2024:

| Metrica | Calibrazione precedente | Calibrazione con storico esteso |
|---|---:|---:|
| Pinball MWh | 29.071,79 | 29.599,51 |
| Copertura80 | 3/4 | 3/4 |
| Copertura90 | 4/4 | 4/4 |
| Ampiezza80 MWh | 455.496,24 | 531.991,14 |
| Ampiezza90 MWh | 636.968,02 | 744.145,29 |

Sul medesimo periodo la pinball peggiora dell'**1,82%** rispetto alla prima
calibrazione e le bande si allargano. I dati aggiuntivi conducono a correzioni
meno forti: sui nove mesi i fattori vanno circa da0,894 a0,942. Non si sceglie
retroattivamente la variante dello storico che produce il numero migliore.
È un esempio concreto del fatto che più dati non garantiscono meno errore.

Tutta la valutazione resta esplorativa: candidato e metodo sono stati scelti
dopo aver esaminato risultati precedenti, e i dati osservati sono revisionati.
Il vecchio test non è stato usato in questo recupero o nel fit. Nessuna promozione
operativa o riesecuzione del test, nessun ampliamento automatico della ricerca.

## Riproduzione e file

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.wind_history_extension --config configs/project.yaml
```

Il comando rifiuta output già esistenti. Occorrono cartelle nuove per una
riproduzione autorizzata, senza cambiare candidato, metodo o lotto di origini.

- [Bundle delle previsioni estese](../reports/wind_history_extension_20261110/):
  snapshot prima delle inferenze, dati combinati, provenienza/checkpoint e manifest.
- [Risultati della calibrazione estesa](../reports/wind_calibration_extended_20261110/):
  impostazioni prima del fit, previsioni, trace completo, metriche su nove mesi,
  confronto su quattro mesi, HTML e hash.

Verifica: 336 test superati, uno smoke opzionale escluso, dipendenze coerenti,
Ruff pulito e hash nuovi/precedenti verificati. MAE/pinball e cutoff ricontrollati
indipendentemente; mediana invariata. Browser: tre grafici, avvertenza nove mesi,
confronto ristretto visibile, zero risorse esterne e nessun debordamento a390px.

## Prossimo passo consigliato

Verificare la possibilità di uno storico più lungo **coerente**, prima di
scaricarlo. Priorità a confini della zona, copertura, qualità e significato
dei mancanti offshore: dato assente non va trasformato automaticamente in zero.
Controllare poi capacità installata pubblicata al cutoff e archivi delle
previsioni meteo mensili. Queste informazioni potrebbero spiegare cambiamenti
che più quantità di dati dello stesso tipo non risolve. Download estesi e nuove
prove restano da autorizzare. Conservare un piano per vere emissioni prospettiche.
