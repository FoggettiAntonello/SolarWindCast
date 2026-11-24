# Pubblicazione di SolarWindCast

## Controlli locali

Il modulo `solarwindcast.publication` usa una lista esplicita di file ammessi.
Esclude ambienti, segreti, dati grezzi/elaborati, output sperimentali e archivi
compressi. Le uniche voci delle cartelle locali `data`, `reports` e `archive`
ammesse nel repository sono le rispettive istruzioni README.

La scansione cerca i valori presenti nell'ambiente locale e alcuni formati
di credenziali, anche dentro XML e workbook incorporati nel PowerPoint.
Il report mostra soltanto percorso e regola; non stampa i valori individuati.
È un controllo preventivo, non una garanzia di rilevare qualsiasi segreto.
Il PowerPoint congelato e i file della presentazione sono verificati tramite hash.

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.publication --require-license
```

Il parametro `--require-license` impedisce il rilascio se la licenza del codice
non è ancora stata scelta e aggiunta alla radice.

## Sito statico

Scegliere una directory nuova; il comando non pubblica nulla:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.publication `
  --require-license --site-output "$env:TEMP/solarwindcast-site-new" `
  --source-repo-url "https://github.com/OWNER/REPOSITORY"
```

Sostituire OWNER/REPOSITORY con il repository effettivo. Il pacchetto contiene
slide, approfondimento, metriche aggregate, PowerPoint, configurazione e guida
pubblica. I collegamenti che prima risalivano alla cartella del progetto sono
riscritti verso file presenti nel sito. Ogni riferimento e ancora HTML viene
controllato; gli hash del pacchetto sono registrati in un manifest separato.
Il PowerPoint viene copiato senza modificarne neppure un byte.
Le regole `.gitattributes` preservano i file del portfolio e le licenze fissate
byte per byte: il cambio Windows/Linux non invalida gli hash tramite CRLF/LF.

## GitHub e autenticazione

Servono il **nome utente o URL del profilo GitHub**, il nome del repository
e la scelta pubblico/privato. Password, codici 2FA e token non vanno comunicati
in chat o salvati nel progetto. Git Credential Manager è installato qui e
supporta accesso via browser e dispositivo.

Dopo aver identificato l'account, avviare il login assistito:

```powershell
git credential-manager github login --username NOME_UTENTE --browser
```

L'utente completa l'accesso sul sito ufficiale GitHub. Il programma conserva
la credenziale nel gestore locale del sistema, non in un file del repository.
Se necessario, l'alternativa `--device` permette di completare l'accesso con
il flusso indicato nel browser. Non serve inviare il token all'agente.

Git del progetto resta disattivato durante il collaudo: sarà inizializzato
con ramo `main` per la pubblicazione concordata, dopo i controlli e la scelta
della licenza. L'archivio Git precedente resta conservato separatamente.

## Controlli GitHub Actions

La pipeline `ci.yml` usa Python 3.12.10 su Windows, installazione PyTorch CPU,
pytest, Ruff, demo senza pesi e controllo del pacchetto pubblico. Non usa
token ENTSO-E né scarica checkpoint. Il test reale con pesi resta escluso.
Azioni checkout/setup-python fissate ai commit ufficiali verificati.

La presenza del workflow non dimostra che sia già passato sui server GitHub:
il primo risultato remoto verrà verificato dopo il push. Il download delle
dipendenze CPU avviene nel runner; la prova locale precedente da wheel CUDA
non lo sostituisce.

## Azure

`azure-static.yml` è ad avvio manuale sul ramo main. Richiede una risorsa
**Static Web Apps Free** e il secret di repository `AZURE_STATIC_WEB_APPS_API_TOKEN`.
Il secret si configura nelle impostazioni GitHub, mai in chat. Il workflow
prepara il pacchetto verificato e carica solo quel contenuto, senza backend API.
Non crea macchine virtuali, database o servizi Timestral nel cloud.

Fonti ufficiali consultate il 22 novembre 2026:

- [GitHub: test Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
- [GitHub: autenticazione](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)
- [Git Credential Manager](https://github.com/git-ecosystem/git-credential-manager)
- [Azure: configurazione build](https://learn.microsoft.com/en-us/azure/static-web-apps/build-configuration)

## Esito effettivo del 22 novembre

Repository pubblico [FoggettiAntonello/SolarWindCast](https://github.com/FoggettiAntonello/SolarWindCast), licenza MIT approvata. Primo [CI CPU da Internet](https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45040562965) superato: 380 test passati, uno escluso, demo/audit/sito validi. Anche il clone GitHub supera i controlli. Azure ancora da pubblicare.

## Release ufficiale del 23 novembre

[v1.0.0](https://github.com/FoggettiAntonello/SolarWindCast/releases/tag/v1.0.0)
è pubblicata sul commit `7f10b1e4d7fcaa650c04eb9cbe73883c01ee92e1`, dopo il
CI esatto superato e la verifica del clone. Allegati PDF, PPTX, metriche e
checksum scaricati pubblicamente e verificati. [Verifiche tecniche](validation.md#release).
GitHub Pages resta l’hosting dei documenti; Azure è rinviato. Gli aggiornamenti
documentali successivi al tag registrano l’esito effettivo della pubblicazione.
