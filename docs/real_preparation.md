# Step 10 — griglia comune approvata

Il 7 novembre 2026 l'utente ha autorizzato di procedere dopo la proposta di
frequenza oraria. Questa scelta è registrata nel YAML; orizzonte e contesto
non sono ancora decisioni definitive.

[Riepilogo HTML della preparazione](../reports/step10_five_year_hourly_20261107/presentazione.html).
[Grafici dei cinque anni e audit degli originali](../reports/step10_five_year_history_20261107/presentazione.html).
[Totali mensili osservati e mesi completi](../reports/step10_monthly_five_year_20261107/presentazione.html).

## Regola di conversione

I valori rappresentano MW medi nell'intervallo, etichettato con il suo inizio UTC.
Un intervallo orario già presente conserva il proprio valore. Quattro intervalli
completi di 15 minuti diventano la loro media: hanno la stessa durata, perciò
la media conserva l'energia dell'ora. Se manca anche un solo quarto d'ora,
l'ora rimane NaN. Nessuna media dei soli valori rimasti, interpolazione o zero.

Non si espandono valori orari in quarti d'ora e non si usano aggregazioni con
rapporti di frequenza non interi. I confini dei segmenti devono essere allineati
alla griglia di destinazione. Serie duplicate, non contigue o fuori contratto
bloccano la preparazione. Gli originali e il report nativo restano invariati.

## Risultato verificato

Cartella: `data/processed/step10_five_year_hourly_20261107/`.

| Serie | Ore attese | Ore valide | Ore mancanti |
|---|---:|---:|---:|
| Solare | 43824 | 43823 | 1 |
| Eolico a terra | 43824 | 43824 | 0 |
| Eolico in mare | 43824 | 38858 | 4966 |

L'ora solare del 2 aprile 2026 alle 05:00 UTC resta NaN perché la fonte ha
un quarto d'ora mancante. Le altre tre osservazioni di quell'ora restano negli
originali, ma non bastano a dichiarare una media oraria completa.
Per l'offshore la fonte non restituisce i primi sei mesi e restituisce soltanto
parte di maggio 2022. I sette mesi interessati restano incompleti: non sono zeri.

Ogni Parquet contiene indice `timestamp_utc` UTC e colonna `target`, in MW.
`quality.json` registra identità del target, frequenza, mancanti, regola e
provenienza; `manifest.json` contiene gli hash. Solare ed eolico restano separati,
come le due componenti eoliche. Una loro futura somma richiederà una scelta esplicita.
Il componente di conversione accetta tutti i target del contratto, inclusi
carico e carico residuo già calcolato: non implementa qui il loro reperimento.

## Riproduzione locale

Usare cartelle di destinazione nuove, dalla radice in PowerShell:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.real_preparation `
  --config configs/project.yaml `
  --output data/processed/nuova_preparazione `
  --report reports/nuova_preparazione
```

Il comando verifica tutti gli hash del rapporto nativo prima di leggerne le
serie e rifiuta cartelle già esistenti. Non legge il token, non accede alla rete
e non carica modelli. Il calendario e il meteo si uniranno dopo la preparazione.
PyArrow, già installato, è dichiarato dipendenza diretta per i Parquet.

## Obiettivo mensile confermato, metodo da concordare

L'utente ha chiarito che vuole l'energia totale del prossimo mese di calendario
in MWh. La proposta precedente 24h/168h è superata. Le serie orarie restano
la base per un possibile metodo di previsione e aggregazione; non sono
automaticamente il risultato finale richiesto. [Definizione, limiti dello
storico e intervalli mensili](monthly_objective.md).

Restano da concordare l'emissione, i ritardi di disponibilità, i concorrenti,
le taglie, gli intervalli e le covariate; la definizione del target eolico è
ancora aperta. Il dato orario aggregato si completa alla fine dell'ora e può
essere pubblicato dopo: il timestamp iniziale non ne dimostra la disponibilità.
Usare oggi dati revisionati del passato produrrebbe un backtest retrospettivo,
non la prova di una previsione riproducibile in tempo reale. Non va dichiarata
affidabilità operativa prima di verificare disponibilità e revisioni.

Lo Step 10 resta in corso. Nessun backtest dello Step 11 eseguito.

## Documentazione ufficiale consultata il 7 novembre 2026

- [pandas: resample e confini degli intervalli](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.resample.html).
- [pandas: aggregazioni, mean esclude NaN e count conta i presenti](https://pandas.pydata.org/docs/reference/resampling.html).
- [pandas: salvataggio Parquet](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_parquet.html).
- [pandas: lettura Parquet](https://pandas.pydata.org/docs/reference/api/pandas.read_parquet.html).
