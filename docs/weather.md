# Meteo Open-Meteo e cache — Step 4

[weather.py](../src/solarwindcast/weather.py) acquisisce dati orari per punti
configurabili. Ogni `Location` ha nome e coordinate; una `WeatherRequest` dichiara
prodotto, modello, variabili, inizio UTC e fine esclusiva UTC. Per Single Runs
occorre anche l'inizializzazione `run_utc`. `fetch_points` gestisce più punti in
sequenza, mantenendoli separati; nessuna media territoriale viene applicata.
Un punto in Puglia non rappresenta automaticamente l'intera zona di mercato Sud.

## Prodotti e disponibilità delle previsioni

| Prodotto nel codice | Origine | Uso come covariata futura |
|---|---|---|
| `reanalysis` | Storico ricostruito, ad esempio ERA5 | Bloccato |
| `historical_forecast` | Serie continua composta da più previsioni storiche | Bloccato per simulazioni operative a origine precisa |
| `single_run` | Una singola esecuzione archiviata di un modello | Ammesso solo dopo i controlli sotto |
| `forecast` | Risposta dell'API di previsione corrente | Solo da quando la risposta è stata acquisita |

L'archivio Single Runs esiste e permette di scegliere il run. La sua copertura
dipende dal modello; inoltre parte dello storico ECMWF precedente al cambio
di ciclo del maggio 2026 è descritta dal fornitore come **hindcast**. Non va
etichettata automaticamente come previsione operativa originale.
Fonte: [Single Runs](https://open-meteo.com/en/docs/single-runs-api).

L'inizializzazione non coincide con la pubblicazione. `WeatherResult.future_at`
richiede, per un run archiviato, origine `operational_archive`, ritardo esplicito
e una fonte o assunzione documentata. Blocca il run se inizializzazione più ritardo
supera l'origine della previsione. Origini `unverified` e `hindcast` restano bloccate.
La selezione restituisce anche questi dettagli negli attributi del frame.
Il controllo applica ciò che si dichiara: **non certifica che un ritardo ipotizzato
sia corretto**, né ricostruisce da solo l'arrivo storico dei dati.

Una previsione corrente salvata può essere usata solo a origini successive alla
sua acquisizione effettiva. Una risposta scaricata oggi non viene presentata come
disponibile ieri. Il criterio di selezione dei run e i ritardi per modello restano
DA DECIDERE; il backtest sarà integrato negli step dedicati.

## Variabili e significato temporale

| Variabile | Unità richiesta | Riferimento temporale |
|---|---|---|
| `temperature_2m` | °C | Istante indicato |
| `wind_speed_100m`, oppure quote supportate dal prodotto/modello | m/s | Istante indicato |
| `shortwave_radiation` | W/m² | Media nell'ora precedente il timestamp |
| `cloud_cover` | % | Istante indicato |

Sono supportate quote del vento a 10, 80, 100, 120 e 180 metri; la disponibilità
effettiva dipende dal modello e dal prodotto. Il servizio può rifiutare una
combinazione non supportata: non si sostituisce automaticamente un'altra quota.
Le unità della risposta vengono controllate.

Il frame mantiene i timestamp del fornitore in UTC e registra la semantica di
ogni variabile. **Non si trasla l'irraggiamento in silenzio**: l'allineamento con
il target, che indica l'inizio dell'intervallo, è esplicito nello [Step 5](features.md).
Anche ricampionamento a 15 minuti o aggregazioni spaziali sono rinviati agli step
dedicati. La frequenza oraria di questa acquisizione non fissa quella del progetto.

I mancanti JSON `null` e i timestamp assenti diventano `NaN` sulla griglia richiesta
e sono contati nei metadati. Duplicati, ordine errato, unità incompatibili, infiniti
e valori non numerici bloccano l'importazione. Nuvolosità fuori 0–100, vento o
irraggiamento negativi vengono segnalati ma conservati. Nessuna interpolazione.
Coordinate richieste e coordinate di griglia restituite sono entrambe conservate.

## Configurazione, rete e cache

`WeatherRequest.from_project_config(project, location_name, product)` legge
periodo da `data`, punto, modello, variabili e run dalla sezione `sources.weather`
del [YAML](../configs/project.yaml). `product` è scelto esplicitamente dal chiamante;
può derivare da `historical_product` o `forecast_archive_product` una volta decisi.
Formato dei punti: lista di dizionari con `name`, `latitude`, `longitude`.

`WeatherClient.from_project_config(project, project_root)` legge cartella cache,
timeout, tentativi, pausa e politica. La rete richiede sia `weather.enabled` sia
`execution.real_data_enabled`. Entrambi restano disattivati nel YAML. Le due piccole
prove autorizzate sotto usano impostazioni dimostrative esplicite in memoria;
non modificano la configurazione degli esperimenti.

La chiave SHA-256 include endpoint e parametri esatti: coordinate, modello,
variabili, date, unità e run. Ogni file JSON contiene richiesta, testo originale
della risposta, hash della risposta e data UTC di acquisizione. Il file si crea
in modo esclusivo: nessuna sovrascrittura. A una lettura successiva si verificano
identità e hash. La cache non è solo una tabella derivata: permette di riprodurre
esattamente l'acquisizione usata.

Politiche supportate: `immutable` (riusa, altrimenti acquisisce se autorizzato)
e `cache_only` (non usa rete). **Non c'è scadenza o aggiornamento automatico**:
per una nuova fotografia delle previsioni correnti si sceglie una nuova cartella
cache, conservando la precedente e la sua data. Non si dichiara fresca una risposta
vecchia. Gli errori HTTP non vengono salvati come dati validi; timeout, 429 e 5xx
possono essere ritentati entro il numero configurato, mentre un 400 non si ritenta
automaticamente.

## Due piccole prove reali eseguite

Punto richiesto: Foggia, latitudine 41.46 e longitudine 15.55. I valori seguenti sono
**risposte ricevute**, non risultati previsivi di SolarWindCast. Date, coordinate,
modelli e periodi sono esempi dimostrativi, non impostazioni approvate.

### Storico ERA5: 1° gennaio 2025

Ricevute 24 righe orarie, nessun mancante nelle quattro variabili. Griglia restituita:
41.5, 15.5; quota 78 metri. Acquisizione: 4 novembre 2026, 11:10:54 UTC.

| Ora UTC | Temperatura °C | Vento 100 m, m/s | Irraggiamento W/m² | Nuvolosità % |
|---|---:|---:|---:|---:|
| 00:00 | 5.8 | 1.35 | 0 | 2 |
| 12:00 | 13.2 | 0.67 | 413 | 0 |
| 23:00 | 6.7 | 2.17 | 0 | 84 |

[Risposta e provenienza nella cache](../data/cache/open_meteo/step4_demo/26a4d158a4c77c9816c05041bcabdea0061490f67de137881f1e14a4bf76f1dc.json).

### Single Runs ECMWF IFS: run 1° novembre 2026, 00 UTC

Ricevute 24 righe orarie per il 1° novembre, con un mancante di irraggiamento
all'ora iniziale. Acquisizione: 4 novembre 2026, 11:12:04 UTC. La provenienza
operativa e il ritardo del modello restano `unverified`: questa prova dimostra
l'accesso all'archivio, non autorizza l'uso nel backtest senza le ulteriori verifiche.

| Ora UTC | Temperatura °C | Vento 100 m, m/s | Irraggiamento W/m² | Nuvolosità % |
|---|---:|---:|---:|---:|
| 00:00 | 12.7 | 8.31 | NaN | 43 |
| 12:00 | 14.9 | 6.72 | 405 | 32 |
| 23:00 | 9.4 | 6.88 | 0 | 100 |

[Risposta e provenienza nella cache](../data/cache/open_meteo/step4_demo/b38c1bffd6f2dfe69a90f5bbe5d48bd9f4537e41ce5ca9f31aa9f846afacf279.json).

La prima chiamata a Single Runs ha restituito HTTP 400: `start_date` non è ammesso,
pur essendo descritto un insieme di parametri comune alle API nella documentazione
generale. Il messaggio è stato controllato; il modulo ora invia `run` e
`forecast_hours`, poi seleziona localmente `[inizio, fine)`. Un test verifica questa
regola. Non è stata fatta una ricerca automatica su molti run o modelli.

## Verifica locale e pulizia

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_weather.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m ruff check src tests --no-cache
```

Per rileggere la prova reale dalla cache, senza una nuova richiesta, dalla radice:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) "src"
@'
from pathlib import Path
from solarwindcast.weather import Location, WeatherRequest, WeatherClient
request = WeatherRequest(
    "reanalysis", Location("Foggia_demo", 41.46, 15.55),
    "2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z", "era5",
    ("temperature_2m", "wind_speed_100m", "shortwave_radiation", "cloud_cover"),
)
client = WeatherClient(Path("data/cache/open_meteo/step4_demo"), 30, 1, 0,
                       network_enabled=False, cache_policy="cache_only")
result = client.fetch(request)
print(result.frame.iloc[[0, 12, 23]])
print("Dalla cache:", result.metadata["cache_hit"])
'@ | .\.venv\Scripts\python.exe -B -
```

I dati fittizi dei test vengono rimossi insieme alle loro directory temporanee.
Le due risposte reali restano conservate come provenienza della verifica; non
sono file di test obsoleti. Nessun token, modello GPU o dataset energetico usato.

## Documentazione ufficiale consultata

- [Historical Weather](https://open-meteo.com/en/docs/historical-weather-api)
- [Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api)
- [Single Runs](https://open-meteo.com/en/docs/single-runs-api)
- [Weather Forecast](https://open-meteo.com/en/docs)
- [Requests](https://requests.readthedocs.io/en/latest/user/quickstart/)

Consultazione e prove: 4 novembre 2026. L'API pubblica è stata usata senza chiave.
