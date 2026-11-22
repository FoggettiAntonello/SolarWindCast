# Esperimento contesto Timestral — risultati del 10 novembre 2026

[Presentazione HTML](../reports/timestral_improvement_results_20261110/presentazione.html).
[Protocollo approvato](timestral_improvement_protocol.md).

L'utente ha autorizzato l'esecuzione esatta con «procedi pure con il protocollo».
Sono state eseguite 88 nuove inferenze reali a 12 mesi e riutilizzate 88 previsioni
a 24 mesi dopo verifica di hash, protocollo, contesti e valori osservati.
CPU un thread, checkpoint locali 5M/28M, nessun training, download o rete.

## Esito principale

**Nessuna variante supera tutti i criteri approvati.** Non sono state avviate
le eventuali 48 inferenze esplorative sul vecchio test né ampliata la griglia.
Non si sono modificate soglie dopo aver visto il risultato.

Tutte le valutazioni principali qui sono sullo **sviluppo comune di 11 mesi**,
dicembre 2023–ottobre 2024, non sui due anni già usati per il vecchio test.

| Target | Migliore originale a 24 mesi | MAE MWh | Migliore a 12 mesi per MAE | MAE MWh |
|---|---|---:|---|---:|
| Solare | 28M con calendario | 29.625,48 | 5M con calendario | 66.398,75 |
| Eolico | 28M con calendario | 129.271,06 | 28M con calendario | 103.570,41 |

Il contesto ridotto peggiora il solare. Sull'eolico 28M/calendario/12 riduce
il MAE del 19,88%, batte l'originale in nove mesi su undici e migliora anche RMSE,
ma peggiora la valutazione probabilistica:

| Eolico 28M/calendario | Contesto 24 | Contesto 12 |
|---|---:|---:|
| RMSE MWh | 148.266,89 | 136.826,15 |
| Pinball MWh, meno è meglio | 32.328,47 | 33.610,04 |
| Copertura 80% | 10/11 | 11/11 |
| Ampiezza media 80%, MWh | 552.546,52 | 683.226,26 |
| Copertura 90% | 11/11 | 11/11 |
| Ampiezza media 90%, MWh | 743.158,23 | 958.847,76 |

La pinball peggiora del 3,96%; le ampiezze crescono di circa 23,65% e 29,02%,
oltre il +10% ammesso. La copertura maggiore viene quindi accompagnata da
bande sensibilmente più larghe. Il risultato puntuale è interessante,
ma non dimostra il miglioramento complessivo richiesto dal protocollo.
Undici casi e selezione tra varianti non certificano superiorità generale.

La baseline deterministica migliore sullo sviluppo comune è anno prima per
solare (38.441 MWh) e ultimo mese valido per eolico (174.162,42 MWh).
Il riferimento probabilistico rolling ha 11 casi solari e quattro eolici:
il suo confronto è separato, senza ridurre gli 11 mesi della selezione principale.
Non confrontare direttamente i suoi punteggi a quattro mesi con quelli a undici.

## Implementazione e garanzie controllate

`monthly_improvement.py` verifica proposta immutabile, approvazione, budget,
snapshot e cache. Usa lo stesso adapter mensile Timestral e non altera i pesi.
Le baseline mantengono il contesto originario. La selezione viene salvata in
`selection_before_test.json` prima di eventuali confronti esplorativi; l'hash
viene ricontrollato dopo. I dati del vecchio test non entrano nei criteri.

La cache di input contiene anche i vecchi risultati del test già noti:
non si pretende di ripristinare un test indipendente. Nessun confronto o
nuova selezione su tali risultati è avvenuto in questa esecuzione.

Se in una futura esecuzione approvata il contesto minimo non fosse disponibile,
la previsione risulterebbe assente con motivazione, senza imputazioni o riduzione
nascosta del requisito di mesi validi. Confronti e denominatori sarebbero espliciti.
Questo percorso non è stato necessario nello sviluppo comune effettivo.

## Output e riproduzione

La cartella risultati contiene:

- `approval_snapshot.json`: proposta e autorizzazione separate dallo snapshot originale;
- `development_predictions.json`: tutte le previsioni principali e tre baseline;
- `probabilistic_baseline_predictions.json`: riferimento probabilistico separato;
- `selection_before_test.json`: tutti i criteri e decisioni congelate;
- `exploratory_predictions.json`: lista vuota, perché non ci sono promozioni;
- `results.json`: punteggi, versioni/revisioni dei backend e contatori;
- `presentazione.html` e `manifest.json`: visualizzazione e SHA-256.

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.monthly_improvement --config configs/project.yaml
```

Il comando rifiuta un output già esistente: per riprodurre occorre una nuova
cartella risultati nella configurazione, senza cambiare la proposta approvata.
Non ripeterlo per cercare un esito migliore; l'inferenza è quella dichiarata.

Verifica finale: 329 test superati, uno smoke opzionale escluso, dipendenze
coerenti, Ruff pulito, metriche verificate indipendentemente dai forecast salvati.
HTML provato con cambio variante e viewport stretto; nessuna risorsa esterna.
Originali, pesi e risultati precedenti conservati; Git/GitHub restano disattivati.
