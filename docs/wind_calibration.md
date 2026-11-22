# Calibrazione eolica controllata — 10 novembre 2026

Autorizzata dall'utente per ora, con raccomandazioni sulle fasi successive al
termine. È un esperimento separato dallo screening; non ne cambia i criteri
né promuove retroattivamente il candidato rifiutato.

## Procedura fissata prima dei risultati

- Candidato: Timestral 28M/calendario, contesto 12 mesi, eolico terra + mare.
- Riferimenti: stesso candidato non calibrato, originale a 24 mesi e baseline
  deterministiche esistenti; tutti sugli stessi mesi valutabili.
- Dati: sole previsioni di sviluppo già salvate. Nessuna nuova inferenza,
  download, lettura del token o modifica dei pesi della rete.
- Un solo fattore positivo `s`: `Q_cal(q) = mediana + s * (Q(q) - mediana)`.
  Mediana, MAE e RMSE centrali non cambiano. Tutti i 21 quantili mantengono
  l'ordine; nessun clipping o riordinamento a posteriori.
- Fit sull'errore dei soli mesi già conclusi secondo il cutoff approvato:
  almeno sei errori, massimo 24 mesi di lookback. Il mese ancora in corso
  non entra nel fit. Warm-up escluso e segnalato, non contato come calibrazione.
- Obiettivo: media della pinball sui cinque livelli comuni, normalizzata
  per l'ampiezza 90% di ciascuna previsione storica, più `0.05 * (s - 1)^2`.
  È una scelta semplice di regolarizzazione, non ottimizzata sui nuovi risultati.
- Scala compresa tra 0,5 e 1,5, risolta con 80 passi numerici di bisezione
  sul sottogradiente dell'obiettivo convesso. Non sono 80 varianti confrontate:
  è una sola ottimizzazione numerica di un unico parametro.
- Nessuna ricerca alternativa se il risultato è sfavorevole. Vecchio test
  non valutato. Per una valutazione più ampia è fissato prima un requisito
  prudenziale di almeno 12 mesi, che da solo non garantirebbe significatività.

Con le undici origini disponibili, il warm-up e il ritardo di etichetta lasciano
quattro mesi valutabili. Sono troppo pochi per una promozione operativa;
non si riduce il minimo di sei errori dopo averlo constatato.
La procedura è causalmente corretta rispetto ai mesi, ma la famiglia del
metodo è stata scelta dopo aver esaminato lo screening: confronto esplorativo.

## Riproduzione

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.wind_calibration --config configs/project.yaml
```

Output in una cartella nuova. Impostazioni e hash salvati prima del fit,
poi trace dei mesi di calibrazione, scale, previsioni e metriche con manifest.
La calibrazione modifica l'output, non è fine tuning di Timestral.
I dati energetici restano in MWh per le metriche e i quantili mensili.

## Risultati effettivi

[Presentazione HTML](../reports/wind_calibration_20261110/presentazione.html).
Mesi valutati comuni: **luglio–ottobre 2024**, quattro casi. Non sono gli
undici mesi dello screening né il test novembre 2024–ottobre 2026.
Fattori stimati causalmente: 0,7580; 0,7583; 0,7581; 0,8423, usando
rispettivamente 6, 7, 8 e 9 errori già disponibili. Sette origini iniziali
restano escluse dal warm-up, senza contare una previsione identità come calibrata.

| Metrica, stessi quattro mesi | 12 mesi originale | 12 mesi calibrato | 24 mesi riferimento |
|---|---:|---:|---:|
| MAE MWh | 108.021,12 | 108.021,12 | 152.289,72 |
| RMSE MWh | 148.638,33 | 148.638,33 | 175.275,20 |
| Pinball MWh | 30.545,37 | 29.071,79 | 34.638,95 |
| Copertura 80% | 4/4 | 3/4 | 3/4 |
| Ampiezza media 80% MWh | 580.847,56 | 455.496,24 | 502.644,37 |
| Copertura 90% | 4/4 | 4/4 | 4/4 |
| Ampiezza media 90% MWh | 812.630,50 | 636.968,02 | 683.024,29 |

Pinball inferiore del 4,82% e intervalli circa 21,6% più stretti rispetto
allo stesso candidato non calibrato. La copertura all'80% scende però al75%:
non si deve nascondere questo effetto. MAE e RMSE identici per costruzione,
quindi non c'è un ulteriore miglioramento della previsione centrale.

Esito: **indicazione esplorativa favorevole alla precisione probabilistica,
non promozione operativa o garanzia di copertura**. Quattro casi sono meno
dei dodici previsti dal requisito prudenziale. Nessuna modifica alle soglie,
nessun secondo metodo o aggiustamento della penalità dopo i risultati.
I dati osservati sono revisionati come negli esperimenti originali: il
rispetto del cutoff mensile non ricostruisce la prima pubblicazione storica.

## Fasi successive consigliate, non avviate

1. **Usare prima le cinque origini eoliche già ammissibili nello storico:**
   luglio–novembre 2023, escluse dal precedente confronto a contesto comune.
   Servirebbero solo cinque nuove inferenze del medesimo candidato 28M/calendario/12,
   senza nuovi dati o pesi. Con la stessa procedura, teoricamente si passerebbe
   da quattro a nove mesi valutabili. È più economico del download massivo,
   ma resterebbe una valutazione esplorativa, non un test indipendente.
2. **Verificare e ampliare lo storico coerente se necessario.** Controllare
   anche se assenza di dati offshore indica dato mancante o assenza documentata
   di impianti: non sostituirla automaticamente con zero. Più stagioni e dati
   di capacità installata pubblicati al cutoff aiutano a distinguere variazioni
   strutturali da errore del modello. Disponibilità e confini della zona vanno
   verificati prima di chiedere un download esteso.
3. **Verificare gli archivi delle previsioni meteo mensili.** Serve un run già
   pubblicato all'emissione e con orizzonte che copra il mese, distinguendo
   archivio operativo, hindcast e rianalisi. Non promettere un miglioramento
   senza il confronto; mantenere parsimonioso il numero di nuove variabili.
4. **Congelare una soluzione e raccogliere nuove previsioni prima degli esiti.**
   È il passaggio necessario per una conferma indipendente e un portfolio
   che descriva l'utilità dimostrata, con baseline e intervalli, non solo una
   percentuale ottenuta sul passato. Fine tuning e taglie maggiori vengono dopo,
   se i dati giustificano il costo e la complessità.

## Verifiche concluse

335 test superati, uno smoke opzionale escluso, dipendenze coerenti e Ruff pulito.
Test della funzione obiettivo, positività e ordine, identità della mediana,
modifiche al futuro/mese in corso senza effetto sul fit, warm-up e mancanti.
Controllati indipendentemente cutoff, trasformazioni, MAE e pinball dai risultati
salvati. Manifest nuovi e precedenti invariati/coerenti; nessun dato sovrascritto.
HTML con tre grafici, zero risorse esterne e layout senza debordamento a 390px.
Nessuna inferenza o aggiornamento dei pesi in questa fase; Git resta assente.

Fonti consultate: [NumPy quantile](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html),
[pandas Period](https://pandas.pydata.org/docs/reference/api/pandas.Period.html).
