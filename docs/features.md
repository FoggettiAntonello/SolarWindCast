# Calendario e unione dei dati — Step 5

[calendar_features.py](../src/solarwindcast/calendar_features.py) costruisce
colonne numeriche dipendenti soltanto dalle date. [features.py](../src/solarwindcast/features.py)
unisce target, calendario e sorgenti meteo sul [formato comune](dataset.md).
Non scarica dati, non allena modelli e non esegue backtest.

## Calendario configurabile

Si scelgono esplicitamente le feature: `hour`, `minute`, `day_of_week`, `month`,
`day_of_year`, `is_weekend`, `is_holiday`. I nomi nel dataset iniziano con `calendar_`.
Il giorno della settimana va da lunedì=0 a domenica=6; weekend e festività valgono
0 oppure 1. Le festività sono quelle nazionali italiane fornite da `holidays`,
senza assumere una provincia rappresentativa della zona Sud.

Il fuso va scelto nella configurazione: `UTC` usa la data UTC, `Europe/Rome` usa
la data e l'ora italiane, compresa l'ora legale. **L'indice resta sempre UTC**:
al cambio d'ora possono esserci due ore locali uguali, ma non timestamp duplicati.
Il parametro `observed` della libreria è esplicito; la sua versione è nel rapporto.
L'elenco legale è quello dell'ambiente installato, non una ricostruzione di ciò
che era stato promulgato a ogni origine storica.

Esempio verificato nei test: il 31 dicembre 2025 alle 23 UTC è già il 1° gennaio
in Italia. La feature festività cambia secondo il fuso scelto. Questi esempi non
fissano ancora il fuso definitivo degli esperimenti.

## Unione e ruoli

`assemble_features(target, config, weather, origin_utc)` riceve un dataset con il
solo target, una `FeatureConfig` e una tupla di `WeatherBinding`. Ogni binding
dichiara nome, sorgente meteo già acquisita, variabili selezionate, ruolo, regola
temporale per variabile e informazioni di disponibilità. Il nome delle colonne è
`weather_<nome_binding>_<variabile>`, per distinguere punti e prodotti diversi.

- `past`: solo rianalisi come meteo passato, con ritardo di pubblicazione e
  fonte/assunzione documentata. Un valore è ammesso soltanto se il suo istante di
  riferimento più il ritardo non supera l'origine e il suo intervallo è nel passato.
  Gli altri valori diventano `NaN`, con un conteggio nel rapporto.
- `known_future`: previsioni che superano `WeatherResult.future_at`. Per i run
  archiviati occorrono origine operativa dichiarata, ritardo e fonte/assunzione;
  per gli snapshot correnti conta quando furono acquisiti. Rianalisi, storico
  continuo e hindcast non diventano covariate future operative cambiando etichetta.
- Il calendario è futuro noto perché deriva dalle date e dal calendario selezionato.

I nomi elencati in `past_covariates` e `known_future_covariates` devono coincidere
esattamente con quelli prodotti e con i rispettivi ruoli. Colonne extra, nomi
duplicati, unità errate e allineamenti non dichiarati vengono rifiutati.

La tabella completa mantiene il target futuro come verità da valutare. Per gli
input si usa **`FeatureResult.model_inputs()`**, che restituisce:

1. contesto con target e covariate soltanto prima dell'origine;
2. tabella futura con le sole covariate future note, senza target o meteo passato.

Il rapporto conserva sorgenti, unità, disponibilità, allineamenti e conteggi NaN.
Gli input non vengono modificati. I ritardi dichiarati del meteo sono assunzioni
da verificare, non una certificazione della disponibilità reale. Il ritardo e le
revisioni del **target** non sono ancora applicati: prima del backtest operativo
andrà limitato anche il contesto del target a ciò che era stato pubblicato.

## Allineamento temporale esplicito

L'unica politica implementata è `exact`: corrispondenza esatta sulla griglia del
target, senza interpolazione, riempimenti o ricampionamenti impliciti.

| Semantica della sorgente | Regola da dichiarare | Effetto |
|---|---|---|
| Valore istantaneo | `instant_at_start` | Colonna associata allo stesso timestamp iniziale del target |
| Media nell'ora precedente | `mean_to_interval_start` | Timestamp spostato indietro di un'ora; richiesto target orario |

Esempio sintetico: irraggiamento etichettato alle 13, media fra le 12 e le 13,
si unisce al target delle 12, che rappresenta `[12, 13)`. Lo spostamento usa
timestamp, non posizioni delle righe. Nel controllo di pubblicazione resta valido
il riferimento originale alle 13: spostarlo alle 12 non rende il dato noto prima.

Una media oraria non viene copiata su quattro intervalli da 15 minuti; la richiesta
viene rifiutata finché non sarà concordata una trasformazione. Una variabile
istantanea oraria può essere unita a un target a 15 minuti, ma le righe intermedie
restano `NaN`: non viene applicato forward-fill.

All'estremo finale, una media dell'intervallo può richiedere un timestamp sorgente
successivo all'ultimo timestamp del target. Se non è stato acquisito, resta `NaN`.
Nessun download supplementare viene eseguito automaticamente; il margine temporale
di acquisizione resta da decidere. Punti diversi restano colonne separate:
nessuna media spaziale implicita.

## Configurazione unica

`FeatureConfig.from_project_config(project)` legge le liste dei ruoli, la politica
di allineamento e il calendario dal [YAML](../configs/project.yaml).
`bindings_from_project_config(project, sources)` associa i risultati meteo già
presenti in memoria ai binding dichiarati. I segnaposto sono rifiutati.

Forma di un binding, con valori soltanto illustrativi:

```yaml
name: punto_osservato
source: meteo_storico
role: past
variables: [temperature_2m]
time_alignment:
  temperature_2m: instant_at_start
publication_delay: "DA DECIDERE"
availability_evidence: "DA DECIDERE"
```

Nessun valore di esempio è stato attivato nel YAML. Sono stati aggiunti soltanto
`features.alignment_policy`, `features.weather_bindings` e `features.calendar.observed`,
tutti DA DECIDERE. Liste dei ruoli, fuso e selezione delle feature rimangono aperti.

## Verifica

In PowerShell, dalla radice:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_calendar_features.py tests/test_features.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m ruff check src tests --no-cache
```

I test verificano festività, data locale, ora legale, i quattro target, disponibilità,
conservazione dei mancanti, limiti degli intervalli e separazione dei ruoli. Una prova
modifica drasticamente target futuro e osservazioni meteo future: gli input del
modello devono restare identici. Le fixture sono solo in memoria, senza nuovi
file temporanei, download, token o dati reali. I test utili restano nel progetto.

Fonti ufficiali consultate il 4 novembre 2026:

- [holidays: API](https://holidays.readthedocs.io/en/latest/api/)
- [holidays: Italia](https://holidays.readthedocs.io/en/latest/auto_gen_docs/italy/)
- [pandas: reindex](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.reindex.html)
- [pandas: tz_convert](https://pandas.pydata.org/docs/reference/api/pandas.DatetimeIndex.tz_convert.html)
