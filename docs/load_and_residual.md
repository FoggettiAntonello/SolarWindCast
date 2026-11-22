# Step 12 — carico, residuo e previsioni ufficiali

L'utente ha autorizzato lo Step 12 il 9 novembre 2026. L'estensione riutilizza il
protocollo mensile già approvato senza cambiare il confronto solare/eolico salvato.
Il download dello storico del carico è stato successivamente autorizzato
esplicitamente dall'utente; il flag `step12.acquisition.history_download_authorized`
è ora attivo nella configurazione unica. La presentazione dei soli campioni
conserva lo stato precedente all'autorizzazione come fotografia della verifica.

## Risultati reali completati

[Presentazione HTML](../reports/step12_monthly_20261109/presentazione.html).
Acquisiti 60 lotti; un tentativo di trasporto fallito è conservato separatamente
con hash invariato, poi ripetuto con successo senza modificare gli originali.
Carico: 43.824 ore valide, 60 mesi completi. Residuo: 38.857 ore valide,
4.967 mancanti e 52 mesi completi. Otto mesi incompleti per i buchi nella
produzione: novembre 2021–maggio 2022 e aprile 2026. Negativi conservati.

280 inferenze reali Timestral 5M/28M e 560 righe di confronto, CPU un thread.
Versioni, revisioni e hash dei pesi in `results.json`; risposte e hash dei lotti
in `source_inventory.json`. Parquet e mensilità osservate consentono controlli
indipendenti delle sottrazioni e dell'energia. Tutti i file hanno SHA-256.

| Target | Mesi test comuni | Baseline MAE minimo MWh | Timestral MAE minimo MWh |
|---|---:|---:|---:|
| Carico | 24 | 89.940,94 — stagionale + errori | 89.995,45 — 28M/calendario |
| Residuo | 23 | 296.923,53 — anno prima | 257.942,00 — 5M/calendario |

Sul carico il MAE è sostanzialmente pari: la differenza è circa 0,06%.
RMSE e pinball raccontano aspetti diversi; il rapporto li conserva, senza
attribuire una superiorità universale. Sul residuo il MAE del 5M/calendario
è inferiore del 13,13% rispetto alla migliore baseline nel campione.
28M solo target perde contro la baseline annuale per entrambi i nuovi target.

Carico 28M/calendario: copertura 21/24 all'80%, 22/24 al90%, ampiezze medie
322.250 e 461.411 MWh. Residuo 5M/calendario: 18/23 all'80%, 21/23 al90%,
ampiezze 853.810 e 1.188.575 MWh. Fasce ampie e pochi mesi non consentono
garanzie operative. Il riferimento probabilistico del residuo copre meno
del nominale nel test: 14/23 e 16/23. Nessun clipping o ricalibrazione sul test.

I valori negativi del residuo sono ammessi. Il conteggio dei mesi con quantili
negativi riguarda tutte le previsioni emesse, comprese quelle senza osservato;
non usa necessariamente lo stesso denominatore delle coperture.
Le origini di sviluppo comuni sono 11 per carico e quattro per residuo,
ridotte dal minimo di coppie di calibrazione. Non sono inventate finestre extra.

Verifica conclusiva: 321 test passati, uno smoke opzionale escluso, Ruff pulito,
dipendenze coerenti; risultati precedenti e protocollo congelato invariati.
Step 12 concluso; Step 13 non autorizzato.

## Definizioni e trasformazioni

- `load`: Total Load ENTSO-E, documento A65, processo A16, zona IT-South.
  È carico di sistema secondo il gestore, non una misura delle sole bollette
  finali o una serie esclusivamente pugliese.
- `residual_load`: carico osservato meno solare ed eolico a terra e in mare osservati.
  Si sottraggono potenze MW sulla medesima griglia UTC; una componente mancante
  rende mancante anche il residuo. Un residuo negativo è ammesso: non è un errore
  da tagliare e non descrive da solo importazioni, accumuli o altre produzioni.
- Ogni ora richiede tutti gli intervalli nativi, per esempio quattro quarti d'ora;
  niente medie su ore parziali, interpolazioni o espansioni di valori più grossolani.
- A03 viene decodificata solo entro il suo Period, come per la produzione.
  Duplicati, sovrapposizioni, unità inattese e domini errati bloccano il caricamento.
  Revisioni sovrapposte non vengono selezionate automaticamente.
- Il totale mensile richiede tutte le ore. Lo stesso mese di carico può essere
  completo mentre il residuo non lo è, per un buco nella produzione.
- La previsione del residuo è diretta: non sottrae quantili dei tre modelli.
  Si mantengono contesto, ritardo, due passi mensili, conversione MW→MWh,
  taglie e varianti dello Step 11. I risultati dei nuovi target sono separati.

## Verifiche reali delle fonti

Cinque richieste contenute, risposte conservate in
[step12_load_20261109](../data/raw/entsoe/step12_load_20261109/), senza sovrascrivere
originali. Tutte hanno restituito dati della zona `10Y1001A1001A788`:

| Campione UTC | Prodotto | Risultato osservato |
|---|---|---|
| 2021-11-01 | Carico A65/A16 | 24 ore complete, frequenza nativa PT60M |
| 2026-10-01 | Carico A65/A16 | 24 ore complete dopo aggregazione da PT15M |
| 2026-10-01 | Carico day-ahead A65/A01 | 24 ore complete, PT15M |
| Ottobre 2026 | Carico month-ahead A65/A32 | A60/A61, due serie di cinque punti settimanali P7D |
| 2026-10-01 | Rinnovabili day-ahead A69/A01 | B16 solare e B19 eolico a terra; B18 offshore assente |

Questa verifica non certifica cinque anni di disponibilità. Le curve A03 possono
avere meno punti del numero di intervalli rappresentati: questo non equivale
automaticamente a un buco. L'assenza della previsione offshore non vale zero.
`createdDateTime` della risposta API non prova la prima pubblicazione storica;
si conservano revisione, acquisizione e hash senza certificare vintage operative.

## Confronto ufficiale: limite dell'obiettivo mensile

La previsione ufficiale day-ahead è un riferimento appropriato per un esperimento
giornaliero con la stessa emissione, non per il nostro totale del mese futuro.
Sommarne le emissioni successive userebbe informazioni non note al nostro cutoff.

Il prodotto month-ahead standard ENTSO-E riguarda i massimi e minimi settimanali
del carico. Non sono né potenze medie né quantili: non è corretto integrarli
per ottenere energia MWh o trattarli come intervalli all'80/90%.
Le settimane ricevute possono iniziare prima del mese UTC e attraversare cambi
di ora locale: non vengono forzate in settimane UTC per inventare totali.

Non è quindi disponibile, tra i prodotti verificati, un confronto ufficiale
mensile equo con medesima quantità e scadenza. Non vengono attribuite prestazioni
ai dati ufficiali, né vengono dichiarate vittorie sui loro valori. Il report
ne mostra disponibilità e motivo dell'esclusione. Un eventuale benchmark
day-ahead è un esperimento distinto, da concordare, non un cambio dell'obiettivo.

## Comandi PowerShell

Piccole verifiche (riusa le risposte già presenti, previa verifica degli hash):

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.load_experiment --config configs/project.yaml --mode probe
```

Dopo la conferma al download e il relativo flag, acquisizione riprendibile
in lotti di mese di calendario (circa 60 richieste, pausa/timeout configurabili):

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.load_experiment --config configs/project.yaml --mode download
.\.venv\Scripts\python.exe -B -m solarwindcast.load_experiment --config configs/project.yaml --mode run
```

`run` richiede tutte le risposte verificate, controlla lo snapshot congelato,
usa solo pesi locali e salva Parquet, mensilità osservate, tutte le previsioni,
score con maschere comuni, HTML autonomo e manifest SHA-256 in una cartella nuova.
Un errore di trasporto interrompe il download; un esplicito `no_matching_data`
resta un periodo interamente NaN, non viene trasformato in zero.
Non si ritenta o modifica un originale già presente; va esaminato separatamente.

Il lettore CSV manuale `read_load_csv` richiede nomi colonna, area, separatore,
decimale e codifica espliciti: il formato del CSV di carico non è ancora stato
verificato su un'esportazione reale. Le fixture sintetiche non ne certificano
il formato del portale. Nel YAML questi parametri restano `DA DECIDERE`.

## Validazione e fonti consultate

Test sintetici: ore complete, A03, buchi, CSV, errori di unità/dominio/curva,
duplicati, mancata espansione, segno del residuo, protezione token, rifiuto
download non autorizzato, manomissione hash, backtest completo e HTML.
Le fixture sono temporanee. Nessun dato sintetico è presentato come risultato reale.

Documentazione ufficiale verificata prima dell'uso:

- [ENTSO-E: month-ahead total load](https://transparencyplatform.zendesk.com/hc/en-us/articles/16648033785492-Month-ahead-Total-Load-Forecast-per-Week-6-1-D)
- [ENTSO-E: descrizione dei prodotti](https://eepublicdownloads.entsoe.eu/clean-documents/Transparency/MoP_Ref2_DDD_v3r4.pdf)
- [entsoe-py: API sorgente](https://github.com/EnergieID/entsoe-py/blob/master/entsoe/entsoe.py)
- [pandas: resample](https://pandas.pydata.org/docs/reference/api/pandas.Series.resample.html)
- [NumPy: quantile](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html)
- [Timestral: codice](https://github.com/mistralai/timestral) e [pesi 28M](https://huggingface.co/mistralai/Timestral-28M)

Il vecchio indirizzo HTML della guida API ENTSO-E non era accessibile al browser:
si sono usate specifiche ufficiali, codice entsoe-py installato e risposte reali.
Versioni e revisioni restano quelle già bloccate, nessuna installazione o download
di modelli. Git e GitHub rimangono disattivati.
