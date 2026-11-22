# Struttura e configurazione — Step 1

Lo Step 12 aggiunge `load_data.py` (XML/CSV carico e residuo),
`load_experiment.py` (campioni, acquisizione autorizzata e backtest) e
`load_results_html.py` (presentazioni), con test in `test_load_data.py`.
L'estensione ha una sezione `step12` nella configurazione unica e non modifica
il protocollo solare/eolico congelato. [Metodo e comandi](load_and_residual.md).

La struttura attiva contiene `configs`, `src/solarwindcast`, `tests`, `scripts`,
`data`, `docs` e `reports`. La cartella `notebooks`, con sole istruzioni
obsolete e nessun notebook, è stata rimossa nella pulizia v1. I risultati precedenti sono separati
in un archivio compresso locale; codice, test e istruzioni obsoleti sono
stati rimossi. [Pulizia e contenuti conservati](cleanup_20261121.html).

`configs/project.yaml` è l'unica configurazione del nuovo percorso. I segnaposto
`DA DECIDERE` non sono valori operativi: il futuro lettore dovrà rifiutarli per
le operazioni che richiedono quei parametri. I vecchi TOML non sono più attivi.

UTC, zona IT_SUD, cartelle e metriche richieste sono espliciti; servizi reali e
modelli sono disattivati nella configurazione. Nessun segreto è incluso.

Il modulo `quality.py` conserva controlli riutilizzabili con test sintetici.
`evaluation.py` è stato aggiornato nello Step 6 con metriche configurabili;
il vecchio separatore orario è stato rimosso. Non è ancora il backtest dello Step 8.

Gli originali restano in `data/raw`; i vecchi derivati sono nell'archivio.
I dati sintetici andranno in `data/synthetic`, la cache in `data/cache` e gli output
futuri in `data/interim`, `data/processed` e `reports`.

Lo Step 2 aggiunge `src/solarwindcast/dataset.py` e `synthetic.py`, con test
dedicati. Il contratto e i limiti del generatore sono in [dataset.md](dataset.md).
Le impostazioni dei test sono esempi; il YAML conserva i parametri da decidere.

Lo Step 3 aggiunge gli adattatori `entsoe_csv.py` ed `entsoe_api.py`, con test
temporanei e rapporti espliciti. Uso e limiti sono in [entsoe.md](entsoe.md).
La proposta di gitignore, già applicata, è stata rimossa perché obsoleta.

Lo Step 4 aggiunge `weather.py`, test HTTP simulati e cache Open-Meteo con hash.
Le due risposte dimostrative reali sono in `data/cache/open_meteo/step4_demo/`.
Uso, prodotti e limiti di disponibilità sono descritti in [weather.md](weather.md).

Lo Step 5 aggiunge `calendar_features.py` e `features.py`, con test in memoria.
Unione, calendario e disponibilità sono descritti in [features.md](features.md).

Lo Step 6 aggiunge `baselines.py`, aggiorna `evaluation.py` e introduce il contratto
`ForecastResult` in `dataset.py`. Metriche, ritardi e limiti dei confronti sono
descritti in [evaluation.md](evaluation.md).

Lo Step 7 aggiunge `timestral_model.py` e test ordinari con backend simulato,
più una prova esplicita con pesi già in cache. API, revisioni e comportamento
dei mancanti sono descritti in [timestral.md](timestral.md).

Lo Step 8 aggiunge `backtest.py` e `backtest_demo.py`. Il profilo sintetico è nel
solo `configs/project.yaml`, separato dalle scelte operative. Il collaudo completo
è conservato nell'archivio storico compresso; regole e comandi in [backtest.md](backtest.md).

Lo Step 9 aggiunge `pyproject.toml` per pacchetto e regole Ruff, `constraints.txt`
per le versioni di riferimento e `scripts/check.ps1` per le verifiche locali.
La configurazione degli esperimenti resta soltanto YAML. Il vecchio conftest che
modificava sys.path è sostituito da `pythonpath = src` in `pytest.ini` e dal pacchetto
installabile. [Setup da zero e limiti delle verifiche](setup.md).

Lo Step 10 aggiunge `real_data_report.py` e `real_data_html.py`: ispezione locale
configurata dal YAML e presentazione HTML autonoma con grafici SVG.
Il risultato aggiornato è in `reports/step10_five_year_history_20261107/`;
[metodo e riproduzione](real_data.md). Nessuna prestazione dei modelli ancora calcolata.

Il proseguimento dello Step 10 aggiunge `history_acquisition.py` e
`history_report.py`: originali e metadati per richiesta in
`data/raw/entsoe/history_20241101_20261101/`, con campioni separati e lotti mensili.
I segmenti mantengono la frequenza nativa, compresi cambi dentro il mese.
Il report aggrega solo per visualizzazione e salva anche le serie native.

La preparazione approvata usa `real_preparation.py`.
I derivati iniziali dei soli due anni e la bozza di protocollo sono stati rimossi
nella pulizia finale: sostituiti dai dati quinquennali e dal protocollo congelato.
Inventario e hash sono nel registro della pulizia.
[Regole e riproduzione correnti](real_preparation.md).

L'estensione a cinque anni mantiene i 36 mesi aggiuntivi in
`data/raw/entsoe/history_20211101_20261101/` e riutilizza i 24 mesi precedenti
senza copiare gli XML. Report nativo in `reports/step10_five_year_history_20261107/`,
serie orarie in `data/processed/step10_five_year_hourly_20261107/`.
`monthly_summary.py` produce l'audit dei totali osservati in
`reports/step10_monthly_five_year_20261107/`. [Metodo mensile](monthly_summary.md).

Lo Step 11 aggiunge `monthly_forecasting.py`, `monthly_experiment.py` e
`monthly_results_html.py`; risultati reali in `reports/step11_monthly_20261107/`.
Il codice e i test attivi precedenti rimangono utili alla pipeline e alle
estensioni. [Esperimento, riproduzione e limiti](monthly_experiment.md).

Git locale è disattivato su richiesta dell'utente. I metadati precedenti sono
conservati nell'archivio compresso locale `archive/git_metadata_disabled_20261121.zip`; non ricreare `.git`
durante il progetto. Le regole di `.gitignore` sono pronte per un futuro ripristino.
Git, GitHub e GitHub Actions saranno rivalutati con l'utente alla conclusione.
