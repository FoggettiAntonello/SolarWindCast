# Setup e verifiche locali

Il 21 novembre 2026 è stata creata una nuova venv isolata, senza accesso ai
pacchetti dell'ambiente di lavoro. Le dipendenze sono state reinstallate dalle
wheel locali; il solo setuptools 78.1.0, assente dalla cache, è stato scaricato
(1,3 MB). Python 3.12.10, Windows, PyTorch 2.11.0+cu128; nessun peso scaricato.
La wheel Timestral proviene dal commit fissato nel TOML, verificato nei metadati
della cache. Non è una nuova verifica del recupero del sorgente da GitHub.

Il pacchetto SolarWindCast è stato costruito in wheel da una copia del progetto
senza dati, risultati sperimentali, token o ambiente preesistente, poi installato
normalmente (non in modalità modificabile). Importazione isolata fuori dalla
cartella e CLI della demo senza pesi riuscite. La demo usa i dati sintetici
generati in memoria; i valori non sono prestazioni su dati reali.

Aggiornamento del 22 novembre: il percorso Windows CPU con installazione da
Internet è stato verificato dalla [pipeline GitHub Actions](https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45040562965):
380 test passati, uno opzionale escluso, pip check/Ruff, demo e audit superati.
La prova GPU locale del 21 novembre resta documentata separatamente nel
[riepilogo del collaudo](validation.md#setup).

## Ambiente già pronto: percorso usato nella verifica

Dalla radice, senza attivare manualmente l'ambiente:

```powershell
.\.venv\Scripts\python.exe -B -m pip install --no-index --no-deps --no-build-isolation --no-cache-dir -e .
.\scripts\check.ps1
```

L'installazione modificabile aggiunge il solo pacchetto SolarWindCast: non aggiorna
librerie, non usa rete e non cambia i pesi. Le modifiche in `src/solarwindcast`
diventano subito disponibili senza reinstallare il codice. Se si cambiano le
dipendenze o gli entry point, si ripete l'installazione dei metadati.

Il pacchetto è ora importabile anche da un'altra directory, senza `PYTHONPATH`.
Il comando installato è:

```powershell
.\.venv\Scripts\solarwindcast-demo.exe --help
```

## Setup da zero, in una nuova cartella di progetto

Prerequisiti: Python 3.12 e il client Git disponibile per ottenere la dipendenza
Timestral dal suo commit pubblico. Il client Git serve a pip per la dipendenza;
questo procedimento non inizializza né collega il progetto a GitHub.
I download e l'installazione delle dipendenze sono operazioni separate dai
controlli locali: non eseguirli sull'ambiente già pronto per semplice verifica.

Per ottenere il codice pubblicato:

```powershell
git clone https://github.com/FoggettiAntonello/SolarWindCast.git
Set-Location SolarWindCast
```

Da questa copia **senza** ambiente preesistente:

```powershell
if (Test-Path -LiteralPath .venv) {
    throw "L'ambiente esiste già: usare il percorso ambiente pronto."
}
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt pip==26.2.2 setuptools==78.1.0
```

Prima si sceglie il tipo di PyTorch. Per la CPU:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints.txt torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
```

In alternativa, per riprodurre la build CUDA 12.8 già presente in questo computer:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints.txt torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
```

Il percorso CPU è sufficiente per il piccolo collaudo. La build CUDA richiede
hardware e driver compatibili: non è stata reinstallata o riconfigurata qui.
Le due righe sono alternative, non operazioni da eseguire entrambe.

Poi si installano il progetto e gli strumenti di sviluppo:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"
.\scripts\check.ps1
```

Non serve cambiare l'ExecutionPolicy o attivare l'ambiente per i comandi Python
diretti. Se le regole del proprio computer impediscono l'avvio dello script
PowerShell, si possono eseguire i singoli controlli della sezione successiva.

## Dipendenze e riproducibilità

[pyproject.toml](../pyproject.toml) contiene metadati del pacchetto, dipendenze
dirette e regole Ruff. I parametri degli esperimenti restano nel solo
[project.yaml](../configs/project.yaml): il TOML non è una seconda configurazione
di target, periodi o modelli.

L'extra `dev` include pytest, Ruff e scikit-learn, usato come confronto indipendente
nei test delle metriche. L'extra `analysis` raccoglie strumenti ulteriori già presenti
nel vecchio ambiente; non è necessario per il collaudo della Fase A.
[requirements.txt](../requirements.txt) rimanda al pacchetto con extra `dev` e ai
vincoli, senza duplicare la lista delle dipendenze. Dopo la scelta CPU/CUDA,
`python -m pip install -r requirements.txt` è equivalente all'installazione del
progetto indicata sopra. La vecchia lista GPU estesa è conservata solo nell'archivio
locale, escluso dalla pubblicazione, e non va applicata al nuovo setup.

[constraints.txt](../constraints.txt) registra 138 nomi/versioni dell'ambiente di
riferimento, senza URL privati o credenziali. I vincoli non installano i pacchetti
opzionali assenti. Per PyTorch si fissa la versione base 2.11.0, che ammette sia
CPU sia la variante locale `+cu128` secondo la semantica dei version specifier.
Timestral resta fissato al commit sorgente nel TOML. Questo file è un insieme di
vincoli dell'ambiente Windows verificato, **non un lock con hash** né una prova di
portabilità su altri sistemi. Le revisioni e gli hash dei pesi sono nei risultati
dei collaudi, separati dalle versioni del codice.

## Che cosa controlla lo script

[check.ps1](../scripts/check.ps1) esegue, fermandosi al primo errore:

```powershell
.\.venv\Scripts\python.exe -B -m pip check
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m ruff check src tests --no-cache
```

È possibile indicare un altro interprete con `-PythonPath` e il suo percorso.
Lo script funziona anche chiamandolo da un'altra cartella: trova la radice
rispetto alla propria posizione e ripristina la directory iniziale alla fine.

I test sono limitati a `tests`, con importazione da `src`, marker e configurazione
rigorosi e avvisi trattati come errori. Archivio, dati, report e ambiente non sono
raccolti. Il vecchio `conftest.py` che modificava `sys.path` è stato rimosso perché
sostituito dalla configurazione esplicita. Le fixture temporanee continuano a
essere eliminate dai test; i test utili non vengono rimossi solo perché sintetici.

Ruff usa regole locali esplicite per errori di codice, import, costrutti sospetti,
aggiornamenti Python, alcuni controlli sulle eccezioni, annotazioni e docstring
dei moduli. Target Python 3.12 e versione Ruff 0.17.3 sono fissati. Non si usa
`--fix`: i controlli non riscrivono il codice. Questa verifica non è una certificazione
di sicurezza o una prova completa dei tipi come un type checker dedicato.

La prova con pesi resta disattivata nella verifica ordinaria anche se la variabile
di ambiente fosse rimasta attiva da un comando precedente. Per abilitarla
esplicitamente, **solo se i pesi 5M sono già in cache**:

```powershell
.\scripts\check.ps1 -CachedTimestral
```

Lo script ripristina alla fine l'eventuale valore precedente della sola variabile
di controllo della prova. Non legge `.env`, non installa pacchetti e non avvia
download. Il test con pesi usa CPU, dati sintetici e `local_files_only=True`.

## Collaudo completo e pesi su una macchina nuova

Con il pacchetto installato e i pesi in cache, dalla radice:

```powershell
.\.venv\Scripts\solarwindcast-demo.exe `
  --config configs/project.yaml --profile step8 `
  --output reports/replica_sintetica
```

La directory di output deve essere nuova. Il profilo rimane dimostrativo e non
abilita fonti energetiche o meteo reali.

Su una nuova macchina, i pesi 5M non saranno già disponibili. Il loro download
è una scelta esplicita, da approvare prima di eseguirlo durante il lavoro assistito.
Il comando seguente non è stato eseguito nello Step 9:

```powershell
.\.venv\Scripts\python.exe -c 'from huggingface_hub import snapshot_download; snapshot_download("mistralai/Timestral-5M", revision="bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f", allow_patterns=["config.json", "model.safetensors", "LICENSE"], token=False)'
```

Il wrapper non avvia questo download per rimediare a una cache mancante. Licenze,
revisione del codice e clausola sul fatturato sono riepilogate nel [README](../README.md)
e nella [documentazione Timestral](timestral.md).

## Segreti e stato Git

La Fase A non richiede token. Per predisporre il file locale senza sovrascriverne
uno già presente:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Il campo d'esempio è solo `ENTSOE_API_KEY=` vuoto. Il token del progetto non è
stato letto per questi controlli. La wheel locale è stata costruita e ispezionata:
contiene codice/metadati, senza dati energetici, archivio, report o `.env`.
Dal ritocco grafico del 21 novembre include anche lo SVG regionale e lo sfondo
PNG generato, necessari per rigenerare le slide e distinti dai dataset degli esperimenti. La nuova
wheel è stata costruita e la lettura della risorsa geografica da wheel isolata
è riuscita; attribuzione in [licenza della mappa](licenses/geographic_visual.md).
La wheel di prova e gli intermedi di build sono stati rimossi; i metadati tecnici
dell'installazione modificabile restano necessari e sono ignorati dalle esclusioni.

Git locale resta disattivato, con i metadati precedenti nell'archivio. Non vengono
aggiunti remote, workflow o pubblicazioni. GitHub Actions è rinviato alla conclusione
del progetto; lo script locale fornisce già una sequenza di verifiche riutilizzabile.

Fonti ufficiali consultate il 5 novembre 2026:

- [Python venv](https://docs.python.org/3.12/library/venv.html)
- [pip install](https://pip.pypa.io/en/stable/cli/pip_install/)
- [setuptools e pyproject](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)
- [Version specifier](https://packaging.python.org/en/latest/specifications/version-specifiers/)
- [pytest](https://docs.pytest.org/en/stable/reference/customize.html)
- [Ruff](https://docs.astral.sh/ruff/configuration/)
- [PyTorch: versioni e indici](https://pytorch.org/get-started/previous-versions/)
- [Hugging Face: download](https://huggingface.co/docs/huggingface_hub/guides/download)
