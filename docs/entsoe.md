# Adattatori ENTSO-E — Step 3

## Importazione dei CSV manuali

[entsoe_csv.py](../src/solarwindcast/entsoe_csv.py) legge uno o più file locali
senza modificarli e restituisce `ImportResult(dataset, report)`. La configurazione
`ImportConfig.from_project_config(project)` legge la struttura di
[project.yaml](../configs/project.yaml), rifiutando i segnaposto ancora aperti.
I percorsi dei file sono passati a `read_csv(paths, config)` come lista di `Path`;
il chiamante può ricavarli da `sources.entsoe.csv_paths`.

Il formato supportato è quello indicato per l'esportazione manuale:

| Campo | Significato |
|---|---|
| `MTU (UTC)` | Intervallo `gg/mm/aaaa hh:mm:ss - gg/mm/aaaa hh:mm:ss` in UTC |
| `Area` | Etichetta esatta configurata, ad esempio `BZN\|IT-South` |
| `Production Type` | Componenti esplicitamente selezionate |
| `Generation (MW)` | Potenza media nell'intervallo, non energia MWh |

Separatore, decimale, codifica, periodo e frequenza sono configurabili. Non si
indovinano separatori delle migliaia o frequenze. Le righe di altre zone/fonti
sono escluse dalla selezione e contate nel rapporto. I limiti sono `[inizio, fine)`.
Righe selezionate fuori dal periodo sono segnalate ed escluse esplicitamente.

Il risultato contiene il [formato interno](dataset.md) su tutta la griglia richiesta,
inclusi i buchi all'inizio e alla fine. `n/e`, `N/A` e celle vuote diventano `NaN`;
gli intervalli assenti vengono inseriti con `NaN` e segnalati per componente.
Valori negativi sono conservati e segnalati. Gli originali hanno percorso e SHA-256
nel rapporto; i riferimenti indicano il numero del record dati, non necessariamente
la riga fisica se un campo CSV contiene più righe.

Duplicati della stessa componente allo stesso istante (anche fra file diversi),
numeri sconosciuti o infiniti, intervalli malformati, frequenze incompatibili e
timestamp fuori griglia sono **bloccanti**: `dataset` vale `None`, il rapporto
indica i motivi. Non si fa media, deduplicazione, interpolazione o ricampionamento
automatico. Una struttura CSV incompatibile o una configurazione errata provoca
un'eccezione esplicita. I rapporti restano in memoria: salvarli insieme agli output
sarà responsabilità dei comandi dei prossimi step.

Per `solar` la componente è `Solar`; per `wind` si scelgono esplicitamente
`Wind Onshore`, `Wind Offshore` o entrambe. La scelta offshore resta DA DECIDERE.
Quando si scelgono entrambe, il totale esiste soltanto dove sono disponibili
entrambe: una componente mancante non equivale a zero. L'adattatore di produzione
rifiuta `load` e `residual_load`: i relativi prodotti e la derivazione del residuo
saranno aggiunti nello Step 12, senza confonderli con tipi di produzione.

## API predisposta e disattivata

[entsoe_api.py](../src/solarwindcast/entsoe_api.py) usa `EntsoeRawClient` della
versione installata `entsoe-py==0.8.1`. I test usano un client finto e XML sintetici:
**nessuna richiesta reale eseguita e nessuna lettura del token del progetto**.

`ApiSettings.from_project_config(project, dotenv_path, raw_directory)` legge
flag, zona e limiti della richiesta. Per acquisire occorrono entrambi i flag
`sources.entsoe.api_enabled` ed `execution.real_data_enabled` a `true`, parametri
completati e un token non vuoto. Il token viene letto da `ENTSOE_API_KEY`
nell'ambiente oppure dal percorso `.env` esplicito, senza stampare il valore e
senza modificare l'ambiente. Il YAML non contiene segreti. Impostare un token
da solo non attiva il servizio. I flag restano `false` nel progetto.

`fetch_generation(config, settings)` esegue una singola richiesta di produzione
osservata. `chunk_days` è un tetto alla durata: il chiamante deve suddividere
periodi più lunghi e concordare acquisizioni pesanti prima di eseguirle.
Timeout, numero di tentativi e pausa provengono dalla configurazione. I limiti
devono essere su ore intere perché la versione installata del client li arrotonda
all'ora; l'adattatore rifiuta limiti diversi invece di modificarli. Ciò non impone
una frequenza oraria ai valori del dataset.

La directory di acquisizione deve essere nuova. Vengono conservati:

- `response.xml`: testo XML restituito dal client, salvato UTF-8; non è una cattura
  dei byte HTTP originali.
- `metadata.json`: zona e codice EIC, periodo richiesto, orari UTC di richiesta e
  ricezione, versione della libreria e SHA-256 dell'XML salvato; nessun token o URL
  con credenziali.

L'XML è conservato prima del parsing, anche quando il formato non è supportato.
Documenti A75/A16 con curve A01, unità MAW e punti espliciti sono convertiti senza
riempimenti; curve A03 e altri formati sono rifiutati. I duplicati sono segnalati,
non rimossi. Non si usa il parser pandas della libreria perché nella versione
installata elimina alcuni duplicati. Revisioni e dettagli documentali restano
nell'XML originale: nessuna scelta automatica fra revisioni concorrenti.

La libreria installata può scrivere il token nei log DEBUG: durante la sola
chiamata sincrona vengono temporaneamente sospesi i log Python e ripristinati
nel `finally`. Questa sospensione è globale al processo: l'acquisizione è destinata
all'uso sequenziale, non a un servizio concorrente. Gli errori del client diventano
un messaggio generico senza URL o catena di eccezioni contenente credenziali.

Questi adattatori importano lo stato dei dati al momento dell'acquisizione:
**non ricostruiscono la disponibilità storica** di dati pubblicati in ritardo
o rivisti. Un backtest operativo dovrà modellare tali limiti negli step dedicati.

## Test e pulizia

In PowerShell, dalla radice:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_entsoe_csv.py tests/test_entsoe_api.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m ruff check src tests --no-cache
```

I CSV e gli XML di prova sono creati dai test. I file su disco sono in directory
temporanee eliminate automaticamente al termine del singolo test, anche in caso
di errore. Nessuna collezione di CSV fittizi viene aggiunta al progetto.
I test automatici sono ancora necessari per individuare regressioni; verranno
rimossi quelli superati o relativi a funzionalità eliminate, non quelli utili.
Gli originali e i risultati scientifici precedenti restano conservati.

È stata rimossa la proposta di gitignore ormai obsoleta dopo aver verificato
che coincideva con le regole già applicate. Git e GitHub restano disattivati.

## Estensione locale nello Step 10

Il parser ora supporta anche A03 con opzione esplicita `allow_a03=True`:
decodifica i blocchi costanti entro ciascun Period, conservando i veri mancanti.
Il percorso API ordinario mantiene il rifiuto predefinito di A03.
[Analisi reale, verifiche della specifica e limiti](real_data.md).

Il comando autorizzato dello storico usa `fetch_raw_generation`, conservando
prima gli originali e verificando poi la risoluzione effettiva. Quando cambia
all'interno dello stesso mese, il lettore seleziona esplicitamente i Period
del segmento: non copia o modifica gli XML, non ricampiona. I normali percorsi
restano stretti. [Piano, comandi e limiti dello storico](history_plan.md).

## Fonti consultate il 4 novembre 2026

- [entsoe-py: documentazione del progetto](https://github.com/EnergieID/entsoe-py)
- [Client ufficiale della libreria](https://github.com/EnergieID/entsoe-py/blob/master/entsoe/entsoe.py)
- [Parser della libreria](https://github.com/EnergieID/entsoe-py/blob/master/entsoe/parsers.py)
- [Codici di area e produzione](https://github.com/EnergieID/entsoe-py/blob/master/entsoe/mappings.py)
- [pandas.read_csv](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html)
- [python-dotenv](https://bbc2.github.io/python-dotenv/)
- [Python ElementTree](https://docs.python.org/3.12/library/xml.etree.elementtree.html)

Il codice installato è stato controllato oltre alla documentazione online:
l'upstream ha già differenze nella protezione dei log. La vecchia pagina della
guida ENTSO-E non era accessibile al browser automatico; non si dichiara verificata
l'intera specifica o la compatibilità con tutti i documenti reali.
