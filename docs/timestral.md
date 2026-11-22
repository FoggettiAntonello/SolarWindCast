# Wrapper Timestral — Step 7

[timestral_model.py](../src/solarwindcast/timestral_model.py) collega il formato
interno all'API ufficiale. Restituisce il [ForecastResult](../src/solarwindcast/dataset.py)
comune alle baseline: mediana, tutti i quantili nativi, indice UTC, identità del
target, frequenza e metadati. Non esegue addestramento o backtest.

## API verificata e versioni

Consultati il 4 novembre 2026 il [repository ufficiale](https://github.com/mistralai/timestral)
e la [scheda Timestral-28M](https://huggingface.co/mistralai/Timestral-28M), oltre
al codice installato. L'adattatore è verificato per Timestral 1.0.0, installato
dal commit `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff`, già fissato nelle dipendenze.
Non è stata aggiornata alcuna libreria. Versione e commit installati devono
corrispondere a quelli configurati prima di caricare il modello.

La famiglia usa 21 quantili nativi: 0.01, 0.05, 0.10, 0.15, …, 0.90, 0.95, 0.99.
Il wrapper conserva questi livelli; non interpola quantili mancanti per creare
intervalli arbitrari. `central_interval` dello Step 6 estrae i livelli disponibili.
Le dimensioni dell'API sono verificate dal wrapper:

| Input/output | Forma per un singolo target |
|---|---|
| Contesto | `(1, 1, context_steps)` |
| Covariate passate | `(1, numero_covariate_passate, context_steps)` |
| Covariate note | `(1, numero_covariate_note, context_steps + passi_decodificati)` |
| Quantili restituiti dall'API | `(1, 1, passi_decodificati, 21)` |
| Quantili nel formato interno | `(horizon_steps, 21)` |

## Configurazione e caricamento

`TimestralSettings.from_project_config(project, variant)` legge il
[YAML unico](../configs/project.yaml). Taglia, repository, dispositivo, revisioni,
contesto, orizzonte, ritardo del target e opzioni di inferenza sono espliciti.
Taglie ammesse: 5M, 28M, 123M, 209M. Dispositivi: `cpu`, `cuda` o `cuda:indice`;
nessuna selezione automatica o ripiego silenzioso su CPU.

Il checkpoint è identificato da un commit completo dei pesi, non da `main`.
La revisione effettiva viene controllata e i file `config.json` e
`model.safetensors` hanno SHA-256 nei metadati. Il caricamento usa
`local_files_only=True` nel percorso ordinario e non legge token di autenticazione.
Per abilitare un futuro download non bastano i pesi assenti: occorrono una scelta
esplicita di rete e il parametro `download_authorized=True`, da usare solo dopo
l'approvazione delle acquisizioni pesanti. Nessun download effettuato nello Step 7.

Il contesto richiesto deve rientrare nel limite addestrato e il blocco di
decodifica in quello del checkpoint. Si rifiutano impostazioni che la libreria
ridurrebbe automaticamente. `max_context` è uguale al contesto configurato.

## Varianti, covariate e disponibilità

- `target_only`: passa soltanto il target disponibile.
- `past`: aggiunge le covariate passate dichiarate; ne richiede almeno una.
- `past_known`: aggiunge le covariate passate dichiarate, se presenti, e le
  future note; richiede almeno una futura nota.

Le covariate richiedono un `FeatureResult` dello Step 5 preparato per la stessa
origine. Un semplice nome di colonna dichiarato futuro noto non basta.
Il report delle feature è conservato nel risultato. Le colonne sono scelte dai
ruoli dichiarati; i target futuri e le osservazioni future non entrano negli input.
Questa versione passa covariate **numeriche**; non introduce un'interpretazione
categorica automatica delle ore o di altri codici calendario.

Il contesto del target segue lo stesso criterio delle baseline:
`inizio_intervallo + frequenza + ritardo_pubblicazione <= origine`.
Se l'ultimo intervallo disponibile precede l'origine, il modello prevede anche
i passi del divario. Questi passi aggiuntivi vengono rimossi dall'output finale,
che inizia all'origine richiesta. Non vengono inseriti valori reali per colmare
il divario. Le covariate note devono coprire anche i passi aggiuntivi; eventuali
mancanti restano espliciti. Revisioni storiche e correttezza dei ritardi dichiarati
richiedono ancora verifica prima di un backtest operativo.

## Mancanti e trasformazioni interne del modello

Gli originali e gli array costruiti dal wrapper non vengono imputati. Si sceglie:

- `reject`: rifiuta qualsiasi NaN negli input selezionati;
- `native_mask`: passa i NaN all'API e ne registra i conteggi. Un contesto target
  interamente mancante è comunque rifiutato.

La libreria Timestral 1.0.0 applica **internamente** maschere, forward-fill,
zeri iniziali e padding delle patch. Non è un riempimento del dataset salvato,
ma fa parte dell'inferenza e va dichiarato. Il wrapper lo registra nei metadati.
Anche normalizzazione e stabilizzazione numerica interne restano quelle della
revisione installata: il wrapper non le riscrive.

Le altre opzioni sono obbligatorie in `inference_options`:

| Opzione | Effetto |
|---|---|
| `symmetric_averaging` | Media con una seconda previsione speculare |
| `clip_nonnegative` | Eventuale limite a zero secondo il contesto, applicato dal modello |
| `quantile_real_cap_k` | Limite all'escursione dei quantili rispetto al contesto; 0 lo disattiva |
| `per_shot_horizon_patches` | Dimensione del blocco di previsione |
| `extreme_value_threshold` | Soglia interna per sostituire mediane estreme usate nei blocchi successivi |

Non si adottano implicitamente i valori della libreria. Per la sola prova sotto:
simmetria e limite a zero disattivati, cap=0, un patch per blocco e soglia `1e30`.
Queste impostazioni non sono decisioni per gli esperimenti reali. Il wrapper
converte gli input in float32, rifiutando overflow; restituisce solo output finiti,
con forma e quantili coerenti, senza riordinarli o correggerli.

## Prova reale con pesi già in cache

Eseguita su CPU una piccola inferenza con:

- Timestral-5M, pesi alla revisione `bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f`;
- codice 1.0.0 al commit sopra e PyTorch `2.11.0+cu128`;
- serie sintetica di 72 ore, contesto 64, orizzonte 8, ritardo target dimostrativo `0h`;
- tre mancanti nel target di contesto, gestiti con `native_mask`;
- una temperatura passata sintetica e l'ora UTC come futura nota, unite dallo Step 5.

Risultato: 8 righe × 21 quantili, tutti finiti e ordinati. Prime tre mediane:
87.325386, 86.397362, 86.152298 MW **sintetici**. Non sono risultati di accuratezza,
misure di velocità, stime di produzione reale o un confronto con le baseline.

Hash verificati della prova:

| File | SHA-256 |
|---|---|
| Configurazione dei pesi | `b5f27f61513f8fd1a3aa996f3720d3679cb40bce5bcb08eb3dc320ce726e7c2f` |
| Pesi 5M | `7ace108c4987e7f2a99a75a445240019d1d31c2117139d1bd05ffdfd25aca738` |

Sono presenti in cache anche i pesi 28M alla revisione
`49b26409ac87b5935539a5d8ffe7f397b720db47`: non sono stati usati per questa prova.
La verifica su CPU non certifica prestazioni o comportamento su GPU o su tutte
le taglie. Taglia, dispositivo e revisioni del progetto restano DA DECIDERE.

## Licenze verificate

Il codice è Apache-2.0. I pesi sono Modified MIT, separati dalla licenza del codice.
Sono stati letti online i testi alle revisioni dei pesi 5M e 28M già presenti,
non dedotti soltanto dalla scheda del modello. Il riepilogo della clausola sul
fatturato e i collegamenti alle revisioni applicabili sono nel [README](../README.md).
I benchmark pubblicati da Mistral non sono verifiche su SolarWindCast.

## Test e ripetizione

Le prove ordinarie usano un backend simulato, esplicitamente etichettato tale
nei metadati. Non caricano pesi, non accedono alla rete e non attestano prestazioni
del modello reale. La prova con pesi è separata e richiede attivazione esplicita.

```powershell
# Suite ordinaria: la prova con pesi resta esclusa
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider

# Piccola prova reale: solo cache locale, CPU, nessun download
$env:SOLARWINDCAST_RUN_CACHED_TIMESTRAL = "1"
.\.venv\Scripts\python.exe -B -m pytest tests/test_timestral_model.py -k cached_timestral_smoke -s -q -p no:cacheprovider
Remove-Item Env:SOLARWINDCAST_RUN_CACHED_TIMESTRAL
```

Le fixture rimangono in memoria. Nessun dataset fittizio o risultato intermedio
permanente aggiunto; i test ancora utili sono conservati. Pesi e dati precedenti
non vengono eliminati. Il YAML resta disattivato e mantiene i parametri non
approvati come DA DECIDERE; sono aggiunti soltanto package_version e code_revision.

Fonti consultate il 4 novembre 2026:

- [Timestral: repository e API](https://github.com/mistralai/timestral)
- [Timestral-28M: scheda ufficiale](https://huggingface.co/mistralai/Timestral-28M)
- [Download e revisioni Hugging Face](https://huggingface.co/docs/huggingface_hub/guides/download)
- [Conversione tensor NumPy, PyTorch 2.11](https://docs.pytorch.org/docs/2.11/generated/torch.Tensor.numpy.html)

L'API è stata verificata anche leggendo i sorgenti installati e con l'inferenza
reale sopra, non soltanto ricopiando un esempio online.
