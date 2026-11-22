# Priorità: migliorare l'utilità di Timestral — proposta del 10 novembre 2026

L'utente chiede di dare priorità al miglioramento di Timestral e all'utilità
reale del progetto, prima del confronto con altre famiglie di modelli.
Questa scelta cambia la priorità; non stabilisce nuovi parametri sperimentali,
non autorizza training pesante o download e non modifica il protocollo congelato.

## Problema pratico e risultato da dimostrare

Stimare l'energia del prossimo mese UTC della zona Sud, in MWh, per solare
ed eolico separatamente, con un intervallo d'incertezza verificabile.
Carico e residuo restano estensioni: non si sceglie il solo target che offre
la percentuale di miglioramento più favorevole sul test già osservato.

Un'utilità possibile è supportare una prima stima mensile di disponibilità
energetica. Non abbiamo ancora dimostrato risparmio economico, vantaggi
di dispacciamento o impatto sulla rete: richiederebbero un caso d'uso,
decisioni e costi espliciti. Il portfolio deve distinguere prototipo di
previsione, confronto retrospettivo e sistema operativo validato.

## Percorso proposto, da trasformare in un protocollo prima delle prove

1. **Verificare i dati e gli errori.** Distinguere buchi, variazioni plausibili
   e anomalie del fornitore; controllare unità, durata dei mesi e allineamento.
   Dati completi non significano necessariamente dati esatti. Non cancellare
   i mesi difficili e non correggere valori senza una regola documentata.
2. **Migliorare l'uso zero-shot.** Confrontare un numero piccolo e dichiarato
   di contesti e feature note all'emissione, con entrambe le taglie. Esempi
   da valutare sono contesti di 12 e 24 mesi, calendario mensile più esplicito
   e numero di giorni lavorativi/festivi. Sono candidati, non valori approvati.
   Un contesto di 36 mesi non ha finestre di sviluppo valutabili con soli
   36 mesi di sviluppo e due passi futuri: richiederebbe più storico.
   Usare le stesse origini ammissibili per i confronti diretti.
3. **Valutare un adattamento molto piccolo.** L'audit ha verificato gradienti,
   non la sufficienza statistica. Una correzione di livello/ampiezza con pochi
   parametri e vincolo verso la previsione originale può essere candidata.
   Se applicata dopo l'output è calibrazione, non fine tuning dei pesi:
   va etichettata correttamente. Un adattamento interno o fine tuning ristretto
   è una fase diversa, con propria giustificazione, test e autorizzazione.
4. **Congelare e verificare la soluzione.** Conservare zero-shot e baseline
   come riferimenti. Confrontare MAE, RMSE, pinball, copertura e ampiezza,
   includendo mesi/target in cui si peggiora e una diagnostica stagionale.
   Evitare di cercare varianti finché una percentuale diventa positiva.
   Per una conferma indipendente servono nuove emissioni e mesi non ancora
   esaminati, con previsione e versione salvate prima dell'osservazione.

Non assumere meteo futuro perfetto. L'archivio meteo verificato per una previsione
giornaliera non certifica un prodotto disponibile al nostro cutoff che copra
tutto il mese. Prima di introdurlo, verificarne orizzonte, disponibilità e vintage.

## Regole di valutazione

- Tutte le scelte vanno effettuate nel solo sviluppo con validazione temporale,
  rispettando la disponibilità delle etichette all'emissione. Il mese in corso
  non è ammesso nemmeno nelle etichette usate per adattare il modello.
- I 24 mesi di test sono già stati esaminati, anche per motivare questi cambiamenti.
  I nuovi risultati su quel periodo sono confronti esplorativi, non una nuova
  verifica indipendente. Ulteriori split retroattivi non cancellano questa storia.
- Un miglioramento minuscolo non è automaticamente reale: riportare differenze
  per mese e loro variabilità, con limiti dovuti a pochi dati e dipendenze temporali.
  Le soglie di accettazione e il budget di prove vanno fissati prima dell'esecuzione.
- Nessuna garanzia che Timestral superi la baseline per ogni target. Una regola
  di scelta o combinazione con baseline può essere utile, ma dev'essere valutata
  e distinta dal miglioramento del solo modello Timestral.
- Non sommare quantili orari, non sottrarre quantili indipendenti, non ridurre
  artificialmente gli intervalli per migliorarne l'aspetto.

## Decisioni da concordare

Il primo esperimento è ora dettagliato nel
[protocollo proposto](timestral_improvement_protocol.md), con
[anteprima HTML e budget verificato](../reports/timestral_improvement_protocol_20261110/presentazione.html).
Le impostazioni sono proposte, non approvate o eseguite.

Budget massimo delle prove, target pilota, contesti e feature candidati,
validazione, obiettivo principale e soglie di accettazione: **DA DECIDERE**.
Il confronto con altre famiglie dello Step 13 resta rinviato. Nessuna inferenza,
calibrazione o sessione di training nuova è stata eseguita per scrivere questo piano.

## Fonti e riferimenti

- [Audit locale del fine tuning](finetuning_feasibility.md): 11 origini di sviluppo,
  7 o 4 per training nei due split illustrativi, forti limiti alla complessità.
- [Repository Timestral](https://github.com/mistralai/timestral) e
  [scheda 28M](https://huggingface.co/mistralai/Timestral-28M): contesto e covariate.
- [Forecasting: Principles and Practice — valutazione temporale](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation):
  valutazione con origini progressive e dati disponibili prima della previsione.
