# Formato interno e serie sintetiche — Step 2

Un dataset è una `TimeSeriesDataset`: tabella pandas `frame` e metadati `spec`.
L'indice `timestamp_utc` è un `DatetimeIndex` UTC, ordinato, univoco e regolare,
con frequenza dichiarata. Ogni timestamp indica l'inizio dell'intervallo
`[timestamp, timestamp + frequenza)`. Il target è potenza media nell'intervallo,
espressa in **MW**, non energia MWh. La conversione di altre fonti dovrà rispettare
la loro semantica temporale e dichiarare eventuali aggregazioni.

La colonna numerica `target` ha sempre lo stesso nome; `spec.target` identifica
`solar`, `wind`, `load` o `residual_load`. I nomi delle altre colonne sono dichiarati
in due elenchi disgiunti: `past_covariates` e `known_future_covariates`. Ogni covariata
ha una unità dichiarata. `provenance` descrive l'origine; gli adattatori dovranno
conservare anche originali, dettagli di acquisizione e revisioni.

I valori mancanti restano `NaN`, inclusi interi intervalli senza osservazioni.
Non si eliminano righe né si interpolano valori. `validate()` controlla il contratto
senza modificare i dati: rifiuta duplicati, griglie irregolari, colonne non dichiarate,
stringhe e infiniti. L'inserimento esplicito degli intervalli assenti, con rapporto
dei buchi, sarà compito degli adattatori dello Step 3. Per rilevare buchi prima e
dopo la tabella serviranno anche i limiti del periodo richiesto: il contratto da
solo non può dedurli. I valori negativi non vengono corretti o rimossi.

## Disponibilità delle covariate

Il ruolo futuro noto **non è una prova di disponibilità**. Quando useremo meteo
e backtest, occorrerà verificare l'istante di emissione e di pubblicazione di ogni
previsione rispetto all'origine della finestra. Meteo osservato futuro e target
futuri non potranno entrare negli input. Lo Step 2 non implementa tale selezione.
Sono ammessi elenchi di covariate vuoti; calendario e meteo arriveranno negli step
dedicati. Nessuna funzione estrae automaticamente tutte le colonne come input.

## Generatore sintetico

`SyntheticConfig` richiede esplicitamente target, inizio UTC, frequenza, numero di
passi, livello medio `baseline_mw`, ampiezza giornaliera e stagionale, periodo
stagionale in passi, deviazione standard del rumore, frazione di mancanti e seed.
`generate(config)` restituisce il formato interno già validato, senza leggere file,
fare richieste di rete, usare GPU o scrivere output.

La formula è un livello medio più una sinusoide giornaliera ancorata all'ora UTC,
una sinusoide stagionale e rumore gaussiano. Le ampiezze e il rumore sono in MW.
La fase stagionale parte da zero all'inizio del campione. Il periodo giornaliero
è di 24 ore UTC; non rappresenta il calendario locale o l'alba in Puglia.
È una forma generica uguale per tutti i target, **non un simulatore fisico**:
può produrre valori negativi e produzione solare notturna. Non viene applicato
alcun clipping nascosto. Serve a verificare la pipeline, non a misurare capacità
previsiva su produzione reale. Le covariate generate sono per ora assenti.

I buchi sono posizioni casuali senza reinserimento: il numero è
`floor(number_of_steps * missing_fraction)`. Indice e numero di righe non cambiano.
Rumore e buchi usano flussi casuali separati: cambiare la frazione dei buchi non
cambia i valori rimasti osservabili. La riproducibilità richiede stessi parametri
e ambiente NumPy; non è una promessa di uguaglianza fra versioni diverse.

## Uso e verifica in PowerShell

I valori operativi restano `DA DECIDERE` in `../configs/project.yaml`.
`SyntheticConfig.from_project_config(yaml.safe_load(...))` legge la sezione
`synthetic` e `target.selected`, rifiutando campi assenti o ancora da decidere.
Il nuovo campo `synthetic.baseline_mw` è anch'esso un segnaposto. Nessun parametro
dei test costituisce una decisione sugli esperimenti reali.

Dalla radice del progetto:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_dataset.py tests/test_synthetic.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m ruff check src tests --no-cache
```

Esempi riproducibili sono in `../tests/test_synthetic.py`; includono i quattro
target, cicli senza rumore, buchi e parametri errati. I test non salvano dati
né scaricano modelli. Git locale e GitHub restano disattivati.

Documentazione ufficiale consultata il 4 novembre 2026 prima dell'implementazione:

- [pandas: date_range](https://pandas.pydata.org/docs/reference/api/pandas.date_range.html)
- [NumPy: Generator](https://numpy.org/doc/stable/reference/random/generator.html)
- [pytest: parametrizzazione](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [Ruff: controlli del codice](https://docs.astral.sh/ruff/linter/)
