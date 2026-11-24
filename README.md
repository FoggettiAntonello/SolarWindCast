# SolarWindCast

Previsioni probabilistiche della produzione solare ed eolica della zona di
mercato **Sud Italia**, con Timestral e baseline semplici. La zona Sud non
coincide con la sola Puglia.

**Versione 1.0.0.** Il progetto comprende una valutazione mensile
in MWh e un percorso sperimentale sulle prossime 24 ore in MW. I risultati
sono retrospettivi, su dati revisionati: non una soluzione operativa certificata.

[SolarWindCast sul sito personale](https://foggettiantonello.github.io/#progetti) ·
[Presentazione PDF online](https://foggettiantonello.github.io/documents/solarwindcast/PresentazioneSolarWindCast.pdf) ·
[Presentazione HTML locale](docs/portfolio/index.html) ·
[Copia PowerPoint](docs/portfolio/PresentazioneSolarWindCast.pptx) ·
[Metriche aggregate complete](docs/portfolio/metrics.json) ·
[Configurazione](configs/project.yaml) · [Verifiche tecniche](docs/validation.md)

La presentazione HTML comprende **12 slide**, con testo e grafico o tabella
affiancati. Le frecce permettono di avanzare; i confronti completi sono in un
[approfondimento separato](docs/portfolio/details.html#complete).
Mappa regionale, sfondo sobrio e illustrazioni delle fonti sono incorporati:
non servono immagini remote. [Provenienza e licenza della mappa](docs/licenses/geographic_visual.md).
La copia PowerPoint apre con autore, foto e contatti, seguiti dalle dodici
slide del progetto: tredici slide in totale. Conserva sole e pale eoliche sullo sfondo e
grafici/tabelle modificabili. [Versione PDF](docs/portfolio/PresentazioneSolarWindCast.pdf). [Come rigenerarla](docs/powerpoint_export.md).
La pagina è autonoma e si può aprire localmente nel browser. I file HTML
su GitHub vanno scaricati/aperti localmente. Il sito personale ospita la
presentazione PDF e il download PowerPoint, entrambi con tredici slide.

## Risultati in evidenza

| Confronto | Campione | Risultato osservato | Compromesso |
| --- | --- | --- | --- |
| 24 ore, solare 5M | 69 giornate, 1.656 ore | MAE -4,18% rispetto alla migliore baseline del campione | Pinball grezza peggiore della baseline probabilistica |
| 24 ore, eolico terra + mare 5M | 72 giornate, 1.728 ore | MAE -4,97% rispetto alla migliore baseline del campione | Intervalli grezzi sottocoperti |
| Calibrazione oraria eolica | 54 giornate, 1.296 ore | Pinball -11,35% rispetto allo stesso 5M grezzo; coperture80/90 al 79,32%/90,28% | Pinball +7,91% e ampiezza 90 +37,00% rispetto alla baseline probabilistica |

Sono confronti diversi: non combinare le percentuali o attribuire un cambio
di campione a un miglioramento del modello. La calibrazione preserva i punti,
quindi non riduce il MAE. I periodi erano già stati esaminati.

La [valutazione completa](docs/portfolio/details.html#complete) conserva tutte
le baseline e le varianti, anche quando Timestral perde. Sul solare mensile,
la baseline con errori passati ha MAE migliore del migliore Timestral nel test;
il candidato eolico mensile a 12 mesi non supera i criteri del confronto finale.
La calibrazione oraria non supera tutti i criteri per nessuno dei due target.

## Prova il progetto senza dati reali o pesi

Nell'ambiente già predisposto, dalla radice in PowerShell:

```powershell
.\scripts\check.ps1
.\.venv\Scripts\python.exe -B -m solarwindcast.backtest_demo `
  --config configs/project.yaml --profile step8 --baselines-only `
  --output reports/demo_baseline_v1
```

La demo genera dati sintetici, costruisce le feature, esegue tre baseline,
valuta le stesse finestre e salva risultati con hash. Non richiede token,
pesi Timestral o richieste di rete durante l'esecuzione. La cartella di output
deve essere nuova; non sovrascrivere una demo precedente.

Questa è una verifica del funzionamento, **non una prestazione su dati reali**.
Per la variante sintetica con Timestral togliere `--baselines-only`: servono
pesi 5M già in cache, non scaricati automaticamente dalla demo.

[Setup da zero e scelta CPU/CUDA](docs/setup.md). Il collaudo del 21 novembre
ha usato una nuova venv Windows/Python 3.12.10, dipendenze reinstallate da
wheel locali e PyTorch cu128. Il 22 novembre anche il percorso **CPU con
installazione da Internet** ha superato test, demo e audit su GitHub Actions.
[Collaudo locale](docs/validation.md#setup) ·
[CI del progetto aggiornato](https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45051464976).

## Pipeline implementata

1. Acquisizione ENTSO-E da CSV manuali o API, conservando risposta originale,
   provenienza e hash; controllo di copertura, frequenza, duplicati e anomalie.
2. Dataset interno con timestamp UTC, target e ruoli delle covariate espliciti.
   Serie di potenza in MW e aggregati di energia in MWh, senza riempimenti nascosti.
3. Feature temporali e collegamento a Timestral, con controllo della disponibilità
   dei dati al momento della previsione e revisioni dei pesi fissate.
4. Backtest a origini temporali successive: Timestral e baseline condividono
   finestre e osservazioni valutabili. Le baseline sono implementate nel progetto
   con NumPy/pandas, senza un servizio di previsione esterno.
5. Metriche puntuali e probabilistiche, calibrazione basata solo su errori passati,
   salvataggio di configurazioni, risultati e manifest SHA-256.
6. Resoconti HTML, grafici e presentazioni; controlli automatici prima della
   pubblicazione dei soli indicatori aggregati.

I risultati pubblicati usano **Timestral 5M e 28M senza riaddestramento dei pesi**.
Nel mensile sono state confrontate varianti solo target e con calendario;
il percorso a 24 ore usa 5M solo target. La calibrazione modifica gli intervalli
usando errori passati e conserva la mediana. L'audit di fattibilità del fine tuning
ha calcolato gradienti su dati sintetici, con **zero passi di ottimizzazione**:
non è stato eseguito fine tuning sui dati reali.
[Dettagli dell'audit](docs/finetuning_feasibility.md).

## Come sono valutati gli esperimenti

- **Mensile:** prossimo mese UTC, eolico terra + mare; 24 mesi di contesto,
  emissione 12 ore prima del mese, esclusione del mese ancora in corso.
  Distribuzione mensile diretta della potenza media e conversione in MWh.
- **24 ore:** 5M senza meteo, 28 giorni di contesto, ritardo dati assunto24 ore.
  Si prevede anche il divario dei dati non ancora disponibili. Origini fissate
  prima dei calcoli; modelli e baseline sulle stesse finestre.
- **Calibrazione oraria:** correzioni laterali solo da giornate interamente
  disponibili al cutoff, 180 giorni di storico e almeno 20 giornate valide;
  mediana invariata. Nessuna garanzia conformale automatica con ore correlate.
- MAE, RMSE, bias, pinball, coperture e ampiezze sono presentati insieme;
  le metriche orarie in MW non si confrontano direttamente con le mensili in MWh.
- I mancanti restano NaN; nessuno zero offshore inventato. Non si sommano
  quantili marginali per dichiarare intervalli dell'energia aggregata.

[Metodo mensile](docs/monthly_experiment.md) ·
[Pilota orario](docs/hourly_pilot.md) · [Estensione oraria](docs/hourly_extension.md) ·
[Calibrazione: metodo ed esito](docs/hourly_calibration_results.md)

I report dettagliati locali restano conservati; la pagina principale contiene
le metriche aggregate necessarie a valutare i risultati anche senza tali file.
Per rigenerarla dalle sorgenti locali verificate usare il comando seguente,
scegliendo prima una destinazione nuova in release_v1.output_directory:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.portfolio_report --config configs/project.yaml
```

Non esegue modelli o nuovi fit. Le CLI degli esperimenti reali proteggono gli
output esistenti e richiedono autorizzazioni nella configurazione. Non lanciarle
per cercare un risultato migliore. Le osservazioni reali, i pesi e i token
non sono incorporati nella pagina principale.

## Dati, estensioni e limiti

Produzione e carico: ENTSO-E Transparency Platform. Token locale in .env;
.env.example contiene soltanto il campo vuoto ENTSOE_API_KEY=.
La v1 pubblica soltanto statistiche aggregate dei nostri esperimenti: dati
grezzi, dataset elaborati, cache, serie di previsioni e pesi restano esclusi
da Git. Non si attribuisce una licenza aperta generale a tutte le categorie
ENTSO-E. [Perimetro e condizioni](docs/licenses/data_rights.md).

Il periodo principale acquisito è novembre 2021–ottobre 2026. L'estensione
Sud+Calabria ha 70 mesi di calendario per solare/onshore: è un'analisi distinta,
non la geografia delle prestazioni principali. Carico e residuo sono
estensioni valutate separatamente e consultabili nella presentazione completa.

Restano da dichiarare in ogni utilizzo: dati revisionati e ritardi assunti,
finestre già esaminate, dipendenza tra ore, mancanza di una verifica prospettica,
intervalli talvolta troppo ampi e nessun beneficio economico aziendale misurato.
Il motivo preciso del vantaggio su alcuni casi non è stato isolato con prove
che separino tutti i fattori. I benchmark di Mistral non sono risultati locali.

## Strumenti e dipendenze

Le versioni sotto sono quelle fissate nel progetto e verificate nell'ambiente
di lavoro il 22 novembre 2026, non una lista delle versioni più recenti.
[pyproject.toml](pyproject.toml) definisce dipendenze dirette e gruppi opzionali;
[constraints.txt](constraints.txt) vincola anche le dipendenze transitive.
[requirements.txt](requirements.txt) rimanda a questi file, senza duplicare
l'elenco. I vincoli non equivalgono a un lock file con hash di tutti i pacchetti.

### Dati, modelli e resoconti

| Dipendenza diretta | Versione fissata | Utilizzo nel codice |
| --- | --- | --- |
| Python | Richiesto >=3.12; verificato 3.12.10 | Moduli con type hint e docstring, CLI, pipeline e test. Le altre versioni di Python non sono certificate da questo collaudo. |
| NumPy | 2.5.4 | Calcolo numerico, baseline, quantili empirici, metriche e dati sintetici. |
| pandas | 3.1.0 | Serie temporali UTC, lettura CSV, allineamenti, controlli di completezza e aggregazioni MW/MWh. |
| PyArrow | 26.0.0 | Lettura e scrittura Parquet dei dataset tramite pandas. |
| PyYAML | 6.0.3 | Lettura della configurazione unica e dei parametri dei protocolli. |
| entsoe-py | 0.8.1 | Client `EntsoeRawClient` per acquisizioni reali ENTSO-E; parsing e controlli XML nel nostro adattatore. |
| python-dotenv | 1.2.4 | Lettura locale del token ENTSO-E, senza inserirlo nel codice o nel repository. |
| requests | 2.34.2 | Client HTTP del modulo Open-Meteo predisposto e testato; quel meteo non entra nei risultati pubblicati. |
| holidays | 0.107 | Festività italiane nel componente delle feature di calendario; le covariate effettive dipendono dal protocollo. |
| PyTorch (`torch`) | 2.11.0 | Esecuzione di Timestral; prova separata dei gradienti su dati sintetici. |
| Timestral | 1.0.0, commit fissato | Previsione probabilistica zero-shot con mediana e 21 quantili, tramite wrapper del progetto. |
| Matplotlib | 3.11.2 | Grafici dei resoconti su dati reali, confronti previsione/osservazioni e diagnostica degli intervalli. |

**Revisioni Timestral usate:**

- Codice: `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff`.
- Pesi 5M: `bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f`.
- Pesi 28M: `49b26409ac87b5935539a5d8ffe7f397b720db47`.

Il caricamento usa checkpoint locali e controlla versione, revisione e hash.
Tra le dipendenze transitive di Timestral figurano **huggingface-hub 2.4.0**
per recupero/cache dei checkpoint e **safetensors 0.8.0** per i pesi.
Le restanti dipendenze transitive, comprese quelle dei grafici e dei test,
sono elencate nei vincoli. Non sono tutte librerie chiamate direttamente
dal nostro codice. Le taglie 123M e 209M non fanno parte dei risultati qui riportati.
[Wrapper e API utilizzata](docs/timestral.md) ·
[Timestral ufficiale](https://github.com/mistralai/timestral) ·
[Scheda 28M](https://huggingface.co/mistralai/Timestral-28M).

Il codice usa anche la libreria standard Python: `argparse` per le CLI,
`pathlib` per i percorsi, `json` per risultati e manifest, `hashlib` per SHA-256,
`xml.etree.ElementTree` per XML e `zipfile` per verificare gli archivi Office.
Questi componenti non richiedono installazioni separate.

### Test, qualità e installazione

| Strumento | Versione/gruppo | Uso effettivo |
| --- | --- | --- |
| pytest | 9.2.0, `dev` | Test con dati sintetici, casi noti, anomalie, cutoff temporali e conservazione dei risultati. |
| Ruff | 0.17.3, `dev` | Controlli statici su import, errori comuni, docstring e annotazioni di tipo configurate. Non è un type checker completo. |
| scikit-learn | 1.9.1, `dev` | Riferimento indipendente nei test di MAE, RMSE e pinball. Non allena i modelli dei risultati pubblicati. |
| setuptools | 78.1.0, build | Costruzione del pacchetto Python e installazione delle CLI. |
| pip | 26.2.2 nel collaudo/CI | Installazione e `pip check` per la compatibilità delle dipendenze. |

La pipeline [GitHub Actions](.github/workflows/ci.yml) usa Windows e
Python 3.12.10: installa PyTorch CPU da Internet, esegue test, Ruff,
demo con baseline e audit dei file pubblicabili. Le azioni esterne sono
fissate a commit. **380 test superati, uno smoke test opzionale con pesi escluso**
nel [CI verificato](https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45051464976).
Il CI non scarica checkpoint e non riesegue i backtest sui dati energetici reali.

L'ambiente di sviluppo è Windows con **VS Code, PowerShell, Git e venv**.
Git Credential Manager è stato usato per l'accesso GitHub, senza token in chat
o nei file del progetto. La build locale è `torch 2.11.0+cu128` e la GPU
rilevata è una RTX 3060 Laptop da circa 6 GiB; gli esperimenti mensili e orari
qui riportati sono configurati su **CPU**. La presenza di CUDA non dimostra
un'accelerazione misurata o un training su GPU.

### Fonti, presentazione e pubblicazione

| Servizio/strumento | Ruolo nel progetto |
| --- | --- |
| ENTSO-E Transparency Platform | Fonte reale di produzione e carico. CSV manuali e API sono gestiti da adattatori distinti. |
| Hugging Face | Provenienza dei checkpoint 5M/28M, con revisioni fissate; nessuna inferenza ospitata usata nei risultati. |
| Open-Meteo | Modulo storico/previsioni con cache e controlli sulla disponibilità temporale. Predisposto e provato, escluso dai confronti pubblicati. |
| HTML, CSS, SVG e JavaScript | Resoconti e navigazione delle dodici slide HTML, senza server Python per la consultazione. I grafici SVG della presentazione sono generati dal codice del progetto. |
| Microsoft PowerPoint ed Excel locali | Esportazione tramite COM/PowerShell: grafici e workbook nativi modificabili; PDF esportato da PowerPoint. Office serve solo a rigenerare questi documenti. |
| GitHub e GitHub Pages | Repository, cronologia, CI e pubblicazione di PDF/PowerPoint sul sito personale. Il sito mostra documenti statici e non esegue Timestral. |
| Openpolis e imagegen | Mappa amministrativa con attribuzione CC BY 4.0 e sfondo illustrativo generato. La foto autore è stata fornita dall'utente. [Provenienza e diritti](NOTICE.md). |

### Componenti opzionali e attività rinviate

Il gruppo `analysis` dichiara **Jupyter 1.1.1, ipykernel 7.4.0 e LightGBM 4.7.0**.
Sono presenti nell'ambiente di lavoro, ma non sono necessari per la demo/CI
e non costituiscono evidenza di un confronto LightGBM: quel confronto è rinviato.
La pipeline consegnata usa moduli Python e CLI, senza dipendere da un notebook.

Anche Streamlit, altri modelli fondazionali e il fine tuning sui dati reali
restano fuori dal perimetro pubblicato. Azure Static Web Apps ha un piano
e un workflow manuale predisposti, ma **nessuna risorsa Azure è stata attivata**.
AWS, Docker e Kubernetes non sono componenti dell'esecuzione di questa versione.

## Struttura del repository

- [src/solarwindcast/](src/solarwindcast/): adattatori, dati, modelli, baseline,
  backtest, calibrazione e generazione dei resoconti.
- [tests/](tests/): test sintetici e verifiche di cutoff, metriche e conservazione dei dati.
- [configs/project.yaml](configs/project.yaml): configurazione unica; DA DECIDERE
  indica un parametro non operativo.
- [docs/portfolio/](docs/portfolio/): pagina principale e metriche aggregate portabili.
- [docs/](docs/): metodo e documentazione; [scripts/check.ps1](scripts/check.ps1): qualità locale.
- Dati e report sperimentali completi restano locali; archivio precedente conservato.

[Perimetro pubblico e archivi locali](docs/validation.md#archivi-e-dati).
Prototipi superati e output dimostrativi sono stati rimossi dalle cartelle attive;
le prove storiche necessarie sono conservate in archivi compressi locali.

## Licenze e stato del rilascio

Il codice upstream Timestral usa Apache-2.0; i pesi hanno una licenza separata
Modified MIT: il testo esclude i diritti quando il fatturato mensile globale
consolidato della società o del datore di lavoro supera **20 milioni di dollari
nel mese precedente**, anche per gli usi derivati indicati nella licenza.
I testi alle revisioni 5M/28M sono stati ricontrollati online il 22 novembre
2026 e coincidono con le copie locali. [Verifica e testi applicabili](docs/licenses/release_licenses.md).
Nessun peso è redistribuito qui. Il codice originale SolarWindCast è distribuito
con [licenza MIT](LICENSE), approvata dall'utente il 22 novembre 2026. [Materiali esterni](NOTICE.md).

Repository pubblico: [FoggettiAntonello/SolarWindCast](https://github.com/FoggettiAntonello/SolarWindCast).
Il 22 novembre 2026 la [pipeline GitHub Actions](https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45040562965)
ha superato installazione CPU da Internet, 380 test (uno opzionale escluso),
pip check, Ruff, demo senza pesi e audit del sito. Anche il clone da GitHub
è stato verificato localmente. [Verifiche tecniche](docs/validation.md#release).
La presentazione è pubblicata sul sito personale tramite GitHub Pages.
Azure è rinviato: nessuna risorsa Azure attivata.
[Release v1.0.0](https://github.com/FoggettiAntonello/SolarWindCast/releases/tag/v1.0.0) ·
[Note della versione](docs/release_v1.0.0.md).

[Controllo dei file, pacchetto del sito e autenticazione](docs/publication.md).

Il piano Azure Static Web Apps Free è [documentato ma rinviato](docs/azure_publication.md).
La pubblicazione corrente usa GitHub Pages e ospita documenti già calcolati,
senza eseguire Timestral nel cloud. [Sito e allegati](docs/validation.md#sito-e-allegati).
