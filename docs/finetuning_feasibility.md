# Verifica di fattibilità del fine tuning — 9 novembre 2026

Autorizzazione dell'utente: verifica per Timestral 5M **e** 28M prima degli altri
modelli. Questa fase non autorizza addestramento reale, ottimizzazione sul test,
download o uso di servizi esterni. Lo Step 13 resta non autorizzato.

[Presentazione HTML](../reports/finetuning_feasibility_20261109/presentazione.html)
e [audit riproducibile](../reports/finetuning_feasibility_20261109/audit.json).

## Esito tecnico misurato

I checkpoint già in cache sono caricati tramite il verificatore esistente,
con revisioni, versioni e hash registrati. Nessun checkpoint nuovo salvato.

| Taglia | Parametri totali | Testa dei quantili | Quota |
|---|---:|---:|---:|
| 5M | 5.208.960 | 792.576 | 15,22% |
| 28M | 27.821.184 | 1.880.064 | 6,76% |

La API pubblica `forecast` è decorata con `torch.inference_mode()`. La funzione
interna `_forecast_raw` mantiene il calcolo dei gradienti sulla testa e riproduce
i quantili dell'inferenza pubblica nella prova eseguita: due passi, contesto
24, un mancante sintetico, varianti solo target e calendario futuro noto.

Sono stati calcolati gradienti finiti e complessivamente non nulli con una
pinball loss sintetica sui 21 quantili del solo ultimo passo mensile.
Il mese intermedio non entra nella loss. **Zero passi di ottimizzazione**;
hash dello stato prima/dopo identici; flag `requires_grad` ripristinati.
Il passaggio pubblico resta in inference mode; il calcolo differenziabile
avviene con gradiente abilitato, senza rimuovere decoratori o modificare il pacchetto.

Questo dimostra la possibilità di ottenere gradienti nel percorso controllato,
non un miglioramento, una ricetta ufficiale di training o un training completo
collaudato. Non sono verificati optimizer, salvataggio/ricaricamento di pesi
adattati, modalità `train`/dropout, altre loss, tutte le possibili anomalie o GPU.
Usare API interne richiede mantenere bloccata la revisione e controllarne la parità.

Scheda rilevata: NVIDIA GeForce RTX 3060 **Laptop**, memoria totale indicata da
PyTorch circa 6,0 GiB. Tutte le prove di gradiente sono su CPU, un thread.
Non si dichiara che un qualsiasi training ci stia sulla GPU senza misurarlo.
Le stime FP32 nel JSON includono soltanto pesi, gradienti e due stati Adam:
16 byte/parametro per il training completo, oppure 4 byte/parametro totale
più 12 byte/parametro adattato per la sola testa. Escludono attivazioni,
buffer, workspaces e overhead: sono limiti inferiori teorici, non memoria misurata.

## Esito sui dati

Il solo sviluppo comprende 36 mesi, novembre 2021–ottobre 2024. Sono completi
36 mesi solari/carico e 29 eolici/residui. Il requisito di almeno 12 mesi validi
nel contesto rende comunque disponibili **11 origini** per ogni target,
dicembre 2023–ottobre 2024, con il contesto approvato di 24 mesi e due passi.
Le osservazioni del test non entrano nei conteggi o nelle scelte dell'audit.

Due esempi illustrativi di divisione, non impostazioni approvate:

| Training | Escluso per disponibilità | Validazione |
|---|---|---|
| 7 origini: dicembre 2023–giugno 2024 | luglio 2024 | agosto–ottobre 2024, 3 origini |
| 4 origini: dicembre 2023–marzo 2024 | aprile 2024 | maggio–ottobre 2024, 6 origini |

Alla prima emissione di validazione il mese immediatamente precedente è ancora
in corso: la sua etichetta non è ammessa nemmeno nel training. I contesti delle
finestre sono sovrapposti; è normale usare passato già noto come contesto,
ma non è corretto considerarli esempi statisticamente indipendenti.
Il residuo deriva dagli altri target, quindi non aggiunge una raccolta indipendente.
Le 11 origini non sono una soglia universale di sufficienza: motivano una valutazione
prudente rispetto alla complessità dei modelli e alla validazione limitata.

## Decisione proposta e limiti del futuro confronto

Non avviare un fine tuning completo sulla base di questi dati. Anche la sola
testa ha molti parametri rispetto alle 4–7 origini degli esempi illustrativi.
Un adattamento molto più limitato e regolarizzato potrebbe essere studiato,
ma resterebbe esplorativo; scegliere un sottoinsieme/adapter, loss, tempi,
learning rate e validazione richiede un protocollo esplicito. In alternativa
valutare più storico o altre serie coerenti; eventuali download richiedono l'ok.

Un training sulle ore avrebbe più campioni ma diversa frequenza e obiettivo:
non dimostra automaticamente qualità sul totale mensile e non consente di
sommare quantili orari per dichiarare un intervallo mensile.

I due anni di test sono già stati esaminati prima della proposta di fine tuning.
Si possono confrontare nuove varianti con zero-shot e baseline sulle medesime
finestre, dichiarando il confronto esplorativo. Una conferma indipendente richiede
nuovi periodi realmente non utilizzati nelle scelte. Nessuna impostazione viene
scelta per correggere specificamente luglio/agosto già osservati.

## Riproduzione e fonti

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.finetuning_feasibility --config configs/project.yaml
```

La cartella di output deve essere nuova; non sovrascrive risultati esistenti.
La sezione `finetuning_feasibility` mantiene `real_training_authorized=false`
e i parametri dell'eventuale training `DA DECIDERE`. Il protocollo congelato
e i risultati degli Step 11 e 12 rimangono invariati.

Documentazione ufficiale consultata e codice installato verificato:

- [Timestral: repository dedicato all'inferenza](https://github.com/mistralai/timestral)
- [Timestral 28M: architettura e pesi](https://huggingface.co/mistralai/Timestral-28M)
- [Mistral: fine tuning tramite Forge](https://mistral.ai/news/timestral/)
- [PyTorch: autograd](https://docs.pytorch.org/docs/stable/autograd.html)

Forge non è stato utilizzato e non si presume che sia disponibile gratuitamente.
Codice Apache 2.0 e pesi Modified MIT con clausola sul fatturato restano distinti,
come documentato nel README e nelle copie delle licenze alle revisioni applicabili.
