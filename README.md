# SolarWindCast

Previsioni probabilistiche della produzione solare ed eolica della zona di
mercato **Sud Italia**, con Timestral e baseline semplici. La zona Sud non
coincide con la sola Puglia.

**Versione 1.0 in preparazione.** Il progetto comprende una valutazione mensile
in MWh e un percorso sperimentale sulle prossime 24 ore in MW. I risultati
sono retrospettivi, su dati revisionati: non una soluzione operativa certificata.

[Apri la presentazione principale](docs/portfolio/index.html) ·
[Copia PowerPoint](docs/portfolio/PresentazioneSolarWindCast.pptx) ·
[Metriche aggregate complete](docs/portfolio/metrics.json) ·
[Configurazione](configs/project.yaml) · [Avanzamento](PROGRESS.md)

La presentazione HTML comprende **12 slide**, con testo e grafico o tabella
affiancati. Le frecce permettono di avanzare; i confronti completi sono in un
[approfondimento separato](docs/portfolio/details.html#complete).
Mappa regionale, sfondo sobrio e illustrazioni delle fonti sono incorporati:
non servono immagini remote. [Provenienza e licenza della mappa](docs/licenses/geographic_visual.md).
La copia PowerPoint usa le stesse dodici slide, con sole e pale eoliche sullo
sfondo e grafici/tabelle modificabili. [Come rigenerarla](docs/powerpoint_export.md).
La pagina è autonoma e si può aprire localmente nel browser. I file HTML
su GitHub vanno scaricati/aperti localmente; la pubblicazione di un sito non
è ancora stata eseguita.

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
usa una nuova venv Windows/Python 3.12, dipendenze reinstallate da wheel locali
e PyTorch cu128. Importazione fuori dal repository e demo installata riuscite.
La variante CPU e il recupero completo da Internet non sono stati ripetuti.
[Dettagli del collaudo](docs/release_setup_validation.html).

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

## Struttura e strumenti

- [src/solarwindcast/](src/solarwindcast/): adattatori, dati, modelli, baseline,
  backtest, calibrazione e generazione dei resoconti.
- [tests/](tests/): test sintetici e verifiche di cutoff, metriche e conservazione dei dati.
- [configs/project.yaml](configs/project.yaml): configurazione unica; DA DECIDERE
  indica un parametro non operativo.
- [docs/portfolio/](docs/portfolio/): pagina principale e metriche aggregate portabili.
- [docs/](docs/): metodo e documentazione; [scripts/check.ps1](scripts/check.ps1): qualità locale.
- Dati e report sperimentali completi restano locali; archivio precedente conservato.

[Pulizia finale e motivi delle cartelle conservate](docs/cleanup_20261121.html).
Prototipi superati e output dimostrativi sono stati rimossi dalle cartelle attive;
le prove storiche necessarie sono conservate in archivi compressi locali.

Python 3.12, pandas, NumPy, PyTorch, Timestral, pytest e Ruff. Configurazioni
CPU e CUDA documentate; il percorso rapido di prova usa soltanto baseline.

## Licenze e stato del rilascio

Il codice upstream Timestral usa Apache-2.0; i pesi hanno una licenza separata
Modified MIT: il testo esclude i diritti quando il fatturato mensile globale
consolidato della società o del datore di lavoro supera **20 milioni di dollari
nel mese precedente**, anche per gli usi derivati indicati nella licenza.
I testi alle revisioni 5M/28M sono stati ricontrollati online il 22 novembre
2026 e coincidono con le copie locali. [Verifica e testi applicabili](docs/licenses/release_licenses.md).
Nessun peso è redistribuito qui. Il codice originale SolarWindCast è distribuito
con [licenza MIT](LICENSE), approvata dall'utente il 22 novembre 2026. [Materiali esterni](NOTICE.md).

Repository pubblico concordato: [FoggettiAntonello/SolarWindCast](https://github.com/FoggettiAntonello/SolarWindCast). Obiettivo
aggiornato dall'utente: pubblicazione il 22 novembre 2026, dopo i controlli.
La scansione dei file pubblici e i workflow CI/distribuzione sono predisposti.
Restano pubblicazione del codice, primo esito reale di
GitHub Actions, pubblicazione e prova del clone. La presenza dei workflow non
certifica un'esecuzione remota già riuscita.

[Controllo dei file, pacchetto del sito e autenticazione](docs/publication.md).

L'utente ha scelto la pubblicazione della presentazione su Azure Static Web Apps
Free: [piano di pubblicazione](docs/azure_publication.md). Sito non ancora online;
il cloud ospiterà risultati già calcolati, senza eseguire Timestral.
