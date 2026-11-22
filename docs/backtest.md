# Backtest a finestre scorrevoli — Step 8

[backtest.py](../src/solarwindcast/backtest.py) sposta in avanti l'origine della
previsione. A ogni origine usa soltanto il contesto già disponibile, esegue tutti
i modelli sullo stesso orizzonte e confronta le previsioni con i valori realizzati
successivamente. [backtest_demo.py](../src/solarwindcast/backtest_demo.py) permette
di collaudare il percorso completo su dati sintetici usando il YAML del progetto.

## Finestre e disponibilità

`BacktestConfig.from_project_config(project)` legge target, frequenza, prima
origine, contesto, orizzonte, passo e numero di finestre. La strategia è
`rolling_origin`, con contesto `fixed`. Non si introduce una finestra espandente
senza una scelta esplicita. Il ritardo di pubblicazione del target è comune a
tutti i modelli: un intervallo è disponibile solo dopo fine più ritardo.

Tutte le finestre sono verificate **prima** di chiamare i modelli: griglia UTC,
contesto sufficiente e orizzonti completi nel dataset. Non si tagliano finestre
finali incomplete e non si salta una finestra difficile. I mancanti nelle righe
esistenti restano NaN, non diventano un motivo per allungare automaticamente il
contesto o cambiare il periodo.

Il motore mantiene la verità di valutazione separata. Ai modelli e al componente
che prepara le feature passa copie con target futuri o non ancora pubblicati
mascherati come NaN. Ogni modello riceve una propria copia. Le feature vengono
ricostruite a ogni origine: non si riutilizzano covariate preparate per un'altra
ora di previsione. `feature_builder` deve usare le regole dello [Step 5](features.md),
comprese disponibilità e provenienza dei run meteo futuri. La trasformazione non
può cambiare il target o la griglia della finestra.

`build_models(project)` costruisce tutte le baseline e varianti Timestral
selezionate nel YAML, senza caricare pesi durante la costruzione. Il motore
controlla che contesto, orizzonte e ritardo coincidano per tutti. Il wrapper riusa
il modello caricato nelle finestre successive, senza riaddestrarlo.

## Casi comuni e quantili

Ci sono due gruppi di confronto distinti:

| Gruppo | Modelli inclusi | Casi valutabili |
|---|---|---|
| Puntuale | Tutti i modelli | Target e previsione puntuale presenti per tutti |
| Probabilistico | Solo modelli che dichiarano quantili | Target e tutti i quantili richiesti presenti per tutti i membri del gruppo |

Una baseline puntuale non riceve intervalli inventati e non entra nel confronto
probabilistico. Per confrontare pinball loss si seleziona lo **stesso insieme di
livelli richiesti** per tutti, anche se Timestral produce più quantili nativi.
I quantili aggiuntivi restano salvati nelle previsioni. Non si interpolano livelli
assenti; gli intervalli centrali richiedono i due livelli effettivamente presenti.

Ogni gruppo usa la stessa maschera di casi per tutti i suoi modelli. I rapporti
conservano anche osservazioni e previsioni mancanti, esclusioni e denominatori.
Con politica `omit`, un caso non valutabile è escluso esplicitamente dal gruppo;
con `raise`, la presenza di mancanti fa fallire il collaudo. Se non ci sono casi
valutabili, il punteggio è NaN, non zero. Numeri di casi diversi fra i due gruppi
non autorizzano confronti diretti fra metriche diverse.

## Aggregazione, sovrapposizioni ed errori

L'aggregazione supportata è `pooled_cases`: ogni caso origine–timestamp ha lo
stesso peso. MAE, bias, pinball, copertura e ampiezza sono medie pesate per i casi
usati. Per RMSE si aggregano prima gli errori quadratici: **non si fa la media
degli RMSE delle finestre**.

Le politiche di sovrapposizione sono esplicite:

- `reject`: rifiuta orizzonti sovrapposti;
- `all_origins`: conserva ogni previsione origine–timestamp, anche se lo stesso
  timestamp è previsto da origini diverse. Il conteggio delle ripetizioni è nei
  metadati; questi casi non sono osservazioni statisticamente indipendenti.

`failure_policy=raise` interrompe su errori di previsione o output incompatibili.
Con `record`, gli errori previsti di dati/esecuzione sono registrati e il modello
resta presente con previsioni NaN: non viene eliminato dal confronto. Di conseguenza
può rendere non valutabile quella finestra per l'intero gruppo, chiaramente
segnalato. Si registra la classe dell'errore, senza copiarne possibili dettagli
sensibili. Gli errori di configurazione e preparazione delle finestre sono bloccanti.
Lo stato `ok` indica l'esecuzione riuscita, non l'assenza di NaN né accuratezza.

## Risultati riproducibili

`BacktestResult.save(directory)` richiede una directory nuova e salva JSON standard:

| File | Contenuto |
|---|---|
| `predictions.json` | Origine, timestamp, passo dell'orizzonte, modello, verità, punto, quantili nativi e flag dei casi comuni |
| `metrics.json` | Metriche per finestra e denominatori |
| `summary.json` | Metriche aggregate correttamente per casi |
| `windows.json` | Maschere, esclusioni, mancanti, errori e metadati dei modelli, incluse revisioni e hash dei pesi |
| `run.json` | Configurazione effettiva, versioni delle librerie, gruppi di confronto e hash dell'input |
| `input.json` | Snapshot del dataset di input con timestamp UTC e metadati |
| `manifest.json` | Stato `complete` e SHA-256 dei sei file precedenti |

NaN viene codificato come JSON `null`, non come zero o stringa `NaN`.
Nessuna sovrascrittura: un nome di directory già esistente viene rifiutato.
Il manifest finale è scritto dopo gli altri file. L'hash dell'input è verificato
anche prima del salvataggio per rilevare modifiche successive al backtest.

Questi risultati documentano il collaudo; `final_test_validated` resta `false`.
La separazione finale fra sviluppo, scelta dei parametri e prova sui dati reali
deve ancora essere decisa. Non si trasformano tre finestre sintetiche in una
certificazione operativa, né si ignorano ritardi o revisioni non ricostruiti.

## Profilo sintetico nel solo YAML del progetto

La sezione `demonstrations.step8` di [project.yaml](../configs/project.yaml) è
etichettata `synthetic_validation_only`. Si applica soltanto su richiesta alla
copia in memoria del progetto: **i parametri operativi sopra restano DA DECIDERE**
e Timestral resta disattivato nel percorso ordinario. Il profilo vieta dati reali
e download di pesi.

Nel profilo: 96 ore sintetiche, contesto 64, orizzonte 8, passo 8, tre finestre,
tre baseline e tre varianti Timestral-5M su CPU. Meteo passato sintetico e calendario
sono preparati di nuovo a ogni origine. Frequenza, date, formule, seed e opzioni
sono nel YAML; nessuno di questi numeri decide gli esperimenti su dati reali.

Il collaudo completo del 5 novembre 2026 è conservato nell'archivio storico
compresso locale, descritto nel [registro della pulizia](cleanup_20261121.html).
Contiene 144 righe previsionali (6 modelli × 3 finestre × 8 passi).
Un mancante della baseline stagionale esclude un caso puntuale per tutti:
23 casi puntuali comuni su 24. Il gruppo probabilistico ha 24 casi comuni su 24.

| Modello | MAE sui 23 casi puntuali comuni, MW sintetici |
|---|---:|
| Persistenza | 7.189114 |
| Ripetizione stagionale | 3.670005 |
| Quantili storici, mediana | 7.396148 |
| Timestral solo target | 1.863020 |
| Timestral con covariate passate | 1.280035 |
| Timestral con passate e future note | 1.158465 |

Sono risultati del generatore usato per collaudare il codice, **non evidenza di
superiorità su produzione reale**. Anche i confronti sfavorevoli sono conservati:
nella terza finestra la baseline stagionale ha MAE circa 1.32, contro circa 3.72,
1.77 e 1.65 delle tre varianti Timestral. In questa prova, aggiungere covariate
peggiora anche alcuni confronti fra varianti nelle singole finestre.

La copertura degli intervalli nominali all'80% è 16/24 per i quantili storici,
21/24 per Timestral solo target e 24/24 per le altre due varianti. Non dimostra
calibrazione: le finestre sono poche, sintetiche e i campioni correlati. Ampiezze
e tutti gli altri punteggi sono conservati, senza selezionare solo risultati favorevoli.

## Comandi PowerShell

Dalla radice, per verificare i test automatici senza caricare pesi:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_backtest.py tests/test_backtest_demo.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m ruff check src tests --no-cache
```

Per ripetere il piccolo collaudo reale usare una **nuova** directory:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) "src"
.\.venv\Scripts\python.exe -B -m solarwindcast.backtest_demo `
  --config configs/project.yaml --profile step8 `
  --output reports/step8_synthetic_replica
```

La prova usa i pesi 5M già in cache e le revisioni documentate nello
[Step 7](timestral.md). Non scarica modelli, non chiama API meteo/ENTSO-E e non legge
token. Le fixture e i risultati fittizi dei test vengono rimossi dalle loro
directory temporanee. Il collaudo storico compresso resta come prova dello
Step 8, distinta dagli esperimenti futuri su dati reali. Git e GitHub restano disattivati.

Fonti primarie consultate il 5 novembre 2026:

- [FPP3, valutazione temporale](https://otexts.com/fpp3/toolbox.html)
- [pandas, date_range](https://pandas.pydata.org/docs/reference/api/pandas.date_range.html)
- [pandas, JSON](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_json.html)
- [Python, JSON standard](https://docs.python.org/3.12/library/json.html)
- [Timestral ufficiale](https://github.com/mistralai/timestral)
- [Timestral-28M](https://huggingface.co/mistralai/Timestral-28M)
