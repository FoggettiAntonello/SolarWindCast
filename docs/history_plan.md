# Step 10 — proposta dello storico e della valutazione

Piano aggiornato al 7 novembre 2026. L'utente ha approvato l'estensione a cinque
anni dopo aver chiarito l'obiettivo di energia totale del prossimo mese.
I due anni già acquisiti vengono riutilizzati; si scaricano soltanto i mesi
mancanti, preceduti da campioni. Lo Step 10 resta in corso.

## Periodo approvato: 60 mesi

Dal **1 novembre 2021 alle 00:00 UTC** al **1 novembre 2026 alle 00:00 UTC escluso**.
L'ampliamento permette più cicli annuali per l'obiettivo mensile e una prova
finale su due anni. Non è una soglia statistica che garantisce affidabilità.

| Uso proposto | Inizio UTC incluso | Fine UTC esclusa |
|---|---|---|
| Sviluppo, scelta delle impostazioni e calibrazione eventuale | 2021-11-01 | 2024-11-01 |
| Valutazione finale separata | 2024-11-01 | 2026-11-01 |

Il periodo di sviluppo non è interamente passato come contesto a Timestral. Serve per
prove temporali, scelta di contesto/feature e taratura dei metodi che lo
richiedono. Timestral resta senza riaddestramento. Per ogni previsione si usa
solo il contesto configurato, realmente disponibile prima della sua origine.

Durante il test, osservazioni di date già trascorse possono entrare nel
contesto delle origini successive, rispettando i ritardi di disponibilità.
Non si cambiano le scelte dopo aver visto i risultati finali: se lo facciamo,
quel periodo diventa sviluppo e serve una nuova prova separata.
Gli istanti previsti devono restare interamente nel periodo di test.

I dati più vecchi possono riflettere una diversa capacità installata. Non
è ancora stata ricostruita una serie coerente delle capacità: confrontare
i risultati tra anni richiederà di dichiarare questo limite.

## Cosa rende credibile la valutazione

- Test cronologico a origini scorrevoli, identiche per tutti i modelli, con
  orizzonte, contesto, passo ed emissione concordati prima della prova finale.
- Errori MAE/RMSE e pinball loss, copertura e ampiezza degli intervalli insieme:
  intervalli molto larghi possono coprire bene ma essere poco utili.
- Per il risultato mensile, errori e intervalli vanno verificati sui totali
  mensili, separando stagione e anno. Una buona metrica oraria non dimostra
  automaticamente affidabilità del totale o dell'intervallo mensile.
- Confronti con baseline e incertezza delle differenze. I quarti d'ora vicini
  e le finestre sovrapposte non sono osservazioni indipendenti: usare analisi
  per blocchi temporali con lunghezza giustificata, non contare ogni punto come
  una prova indipendente. Anche una previsione emessa ogni giorno produce
  errori correlati tra giorni.
- Dichiarare quante origini e quanti casi validi entrano nei risultati, esclusioni,
  eventi estremi poco rappresentati, cambi di capacità e revisioni della fonte.

Il successo non consiste nel raggiungere un numero prefissato di mesi: dopo
l'acquisizione si giudicano copertura, varietà dei casi e precisione delle
stime. Nessun numero di mesi assicura da solo una copertura corretta in futuro.

## Dati da acquisire e dimensione prevista

ENTSO-E, zona Sud: solare, eolico a terra e in mare mantenuti separati negli
originali. La definizione del target eolico finale resta da concordare.
Conservare la risoluzione nativa; non assumere che tutti i mesi abbiano 15 minuti.
Non ricavare quarti d'ora artificiali da dati orari.

Il periodo approvato comprende 1826 giorni: **43.824 intervalli orari per
componente**, solo se la griglia fosse uniforme e completa. Sono conteggi
teorici: assenze e risoluzioni effettive vanno verificate nei dati.
La memoria di contesto è una decisione distinta dalla lunghezza dell'archivio.

Prima fase di acquisizione proposta: campioni brevi distribuiti tra inizio,
metà e fine del periodo per controllare disponibilità, risoluzione, codifica,
componenti e provenienza. Poi acquisizione completa in lotti con pausa,
cache e hash; il numero di richieste dipenderà dai limiti effettivi del servizio.
Nessuna stima inventata di tempi, dimensioni dei file o qualità.
Il parser locale A03 è disponibile, ma il percorso API ordinario è ancora
stretto su A01: l'estensione deve essere esplicita e testata prima di usarlo.

## Meteo e disponibilità storica

Open-Meteo dichiara Single Runs ECMWF IFS HRES da marzo 2024, mentre per la
maggior parte degli altri modelli l'archivio parte dal 2 aprile 2026.
L'intero periodo 2021–2026 NON è quindi coperto automaticamente da Single Runs
IFS. Variabili, modelli e disponibilità di previsioni per un mese intero
richiedono una verifica separata. Nessun archivio meteo esteso è autorizzato
o acquisito con questa estensione di produzione.

Il prodotto Historical Forecast, che concatena le prime ore di run successivi,
non sostituisce le previsioni disponibili a una precisa origine. Per le future
covariate scegliere run inizializzati e pubblicati prima dell'emissione,
documentando il ritardo; non usare meteo ricostruito futuro come se fosse noto.
Un archivio disponibile oggi non dimostra da solo cosa fosse disponibile allora.

## Stato dell'acquisizione autorizzata

Il periodo e i limiti operativi sono registrati in `planning.step10` della
configurazione unica; il comando dedicato verifica l'autorizzazione esplicita.
I normali comandi API restano disattivati. La griglia oraria e il mantenimento
dei NaN sono approvati; il risultato richiesto è il totale del prossimo mese.
Contesto, emissione, covariate, modelli e intervalli mensili restano DA DECIDERE.

I campioni dell'estensione coprono 2021-11-01, 2023-05-01 e 2024-10-31, con
frequenza oraria. Nel primo campione la fonte non restituisce l'offshore:
la mancata risposta è registrata e i valori restano NaN. Nel precedente audit
i campioni 2025/2026 erano a 15 minuti. Il cambio di risoluzione è rilevato il 31 dicembre
2024 alle 00:00 UTC. Gli XML restano immutati; la lettura separa i Period
con diversa risoluzione, senza creare dati più fini o riempire mancanti.

Comando PowerShell per acquisire o riprendere lo storico autorizzato:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.history_acquisition `
  --config configs/project.yaml --phase history --output reports/nuovo_rapporto_storico
```

Gli originali già presenti vengono riutilizzati solo se hash, periodo, zona e
componente corrispondono; un file incoerente o una richiesta fallita interrompono
il lavoro, senza riacquisizioni o sovrascritture nascoste. I limiti sono 31 giorni
per lotto, timeout 30 secondi, un tentativo e pausa di un secondo tra richieste.
Un lotto può produrre più segmenti quando cambia la risoluzione nativa.
L'HTML finale mostra medie giornaliere descrittive solo per giorni completi;
nei JSON restano le serie native. Non è una scelta della frequenza sperimentale.

Alcune risposte includono anche serie di consumo degli impianti:
`outBiddingZone_Domain` identifica il consumo, `inBiddingZone_Domain` la produzione.
Il lettore storico esclude esplicitamente le prime, le conta nei metadati e
le conserva negli originali; non le sottrae alla produzione. La modalità ordinaria
del parser resta stretta e rifiuta tali serie senza consenso esplicito.
Non si tratta dell'estensione al carico elettrico, prevista nello Step 12.

Un'assenza esplicita (`NoMatchingDataError`) è distinta da un guasto di rete.
Il client non consegna il corpo della risposta in questo caso: sono conservati
metadati sanitizzati della richiesta e dell'eccezione, senza inventare un XML.
Tali metadati hanno SHA-256 nel manifest e non autorizzano valori zero.

## Fonti verificate il 6 novembre 2026

- [Hyndman e Athanasopoulos, valutazione cronologica e rolling origin](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation).
  La separazione temporale segue questo metodo; i cinque anni sono una nostra
  scelta progettuale approvata dall'utente, non una soglia teorica universale.
- [Open-Meteo Single Runs: copertura per modello](https://open-meteo.com/en/docs/single-runs-api).
- [Open-Meteo Historical Forecast: serie composta e differenze tra prodotti](https://open-meteo.com/en/docs/historical-forecast-api).
- [entsoe-py: distinzione tra produzione e consumo delle unità](https://github.com/EnergieID/entsoe-py/blob/master/entsoe/parsers.py), verificata anche nel codice installato.
