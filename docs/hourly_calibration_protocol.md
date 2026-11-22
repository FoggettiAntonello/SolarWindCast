# Calibrazione oraria — protocollo proposto, 15 novembre 2026

[Resoconto HTML](../reports/hourly_calibration_protocol_20261115/presentazione.html).
Configurazione unica: `hourly_calibration` nel YAML.

## Stato e domanda

Preparazione del protocollo e test sintetici autorizzati con «procedi».
Esecuzione sui dati reali ancora disabilitata, come richiesto dalle istruzioni
di progetto prima di concordare il metodo. Nessun nuovo fit reale, inferenza,
training o download. I risultati mensili e i due piloti orari restano invariati.

Domanda: possiamo ridurre la sottocopertura dei quantili orari 5M mantenendo
identiche le mediane e migliorando anche la pinball? Allargare le bande aumenta
meccanicamente la copertura sullo stesso campione, ma questo da solo non
dimostra un miglioramento utile.

## Una sola regola di correzione

Metodo ispirato ai punteggi della [Conformalized Quantile Regression,
Romano, Patterson e Candès, 2019](https://papers.neurips.cc/paper_files/paper/2019/hash/5103c3584b063c431bd1268e9b5e76fb-Abstract.html),
con soli allargamenti nonnegativi. È una variante applicata a serie temporali
correlate: non attribuirle automaticamente garanzie conformali di copertura.

Per ciascun target, a ogni emissione:

1. Raccogliere i forecast grezzi 5M delle due cartelle dei piloti, selezionando
   solo lo stesso target/modello e verificando hash, parametri e assenza di
   duplicati. Mai usare le correzioni precedenti come input del fit.
2. Tenere le origini degli ultimi 180 giorni la cui **intera giornata** è
   disponibile: `origine_storica + 24h orizzonte + 24h ritardo <= emissione`.
   Nessuna ora del giorno corrente o futuro può entrare. Rifiutare giornate
   non finite, incomplete, duplicate o con quantili incoerenti.
3. Richiedere almeno 20 giornate complete. Per ogni livello centrale L=0,8/0,9
   calcolare per ciascuna ora il punteggio
   `max(quantile_basso − osservato, osservato − quantile_alto, 0)`.
   Raggruppare le ore delle giornate ammissibili: la correlazione resta un limite,
   non sono 480 osservazioni indipendenti.
4. Su n punteggi prendere l'elemento ordinato di rango `ceil((n+1)*L)`, indice
   matematico da 1. Se il rango supera n, non calibrare. Nessuna interpolazione
   o scelta dell'estimatore dopo i risultati.
5. Imporre `correzione90 = max(correzione90, correzione80)`, per preservare
   l'annidamento delle bande; sottrarre la correzione al quantile basso e
   aggiungerla a quello alto. Una correzione per livello e target, uguale sulle
   24 ore della previsione; nessuna suddivisione per ora, stagione o orizzonte.

Restano esattamente invariati quantile0,5 e previsione puntuale: MAE, RMSE e
bias devono essere identici sui medesimi casi. Nessun clipping dei negativi,
riordinamento nascosto o modifica dei dati originali. Possibile svantaggio
da riportare: una correzione uniforme può allargare inutilmente le bande solari
notturne e peggiorare la pinball. Non introdurre eccezioni dopo averlo visto.

La trasformazione dei quantili non richiede l'osservazione futura della
giornata da prevedere. Sono necessarie etichette osservate soltanto per le
giornate storiche ammissibili al cutoff.

## Giorni di valutazione e confronti comuni

Valutazione proposta: origini **1 maggio 2025–31 ottobre 2026**, solo giorni
1,8,22 dell'estensione già calcolata. Primi sei mesi novembre2024–aprile2025
come avvio cronologico, non conteggiati come valutazione. I giorni15 del primo
pilota possono fornire errori storici dopo il cutoff ma non sono aggiunti al
campione da valutare. Anche le origini precedenti del periodo valutato possono
entrare nei fit successivi, soltanto quando sarebbero disponibili.

Nessuna nuova inferenza. Esclusioni originali e origini con meno di20giorni
disponibili vanno elencate; nessuna data sostitutiva. Una semplice pianificazione
dei casi eleggibili può avvenire prima del fit, senza calcolare punteggi reali.

Pianificazione verificata senza fit: solare36origini/864ore, eolico54origini/
1.296ore. Per il solare restano tre esclusioni originali e altre15origini
con meno di20giornate disponibili nella finestra mobile. Nessuna esclusione
eolica. Questi sono conteggi di disponibilità, non nuove prestazioni calibrate.
Conservare nell'HTML anche la distribuzione delle origini per mese: il diverso
campione solare non va presentato come valutazione uniforme di tutti i mesi.

Per ogni target confrontare **sugli identici timestamp**: 5M grezzo, 5M
calibrato e tutte le quattro baseline salvate (persistenza, lag48h, lag168h,
distribuzione della stessa ora). La baseline probabilistica è l'ultima;
le altre non possiedono intervalli e non devono ricevere pinball inventate.
Nessun confronto diretto con i riepiloghi precedenti calcolati su periodi diversi.

I periodi sono già stati esaminati e hanno orientato la scelta di calibrare.
Fit causale non equivale a test indipendente. Queste rimangono verifiche
esplorative su dati revisionati e ritardo assunto, non tempi di pubblicazione
storicamente ricostruiti. Nessun intervallo giornaliero ottenuto sommando
i quantili marginali orari.

## Criteri proposti, prima dell'esecuzione

Per chiamare il risultato promettente su un target richiedere tutti:

- almeno 30 origini valutabili dopo le esclusioni;
- previsioni puntuali, MAE/RMSE/bias invariati sui medesimi casi;
- pinball ridotta almeno del5% rispetto al 5M grezzo e non peggiore della
  distribuzione empirica oraria sugli stessi casi;
- coperture aggregate80/90 entro5punti percentuali dai nominali, riportando
  anche risultati per giornata, mese e ora prevista;
- ampiezze medie80/90 non superiori al110% di quelle della baseline
  probabilistica, per non scambiare bande arbitrariamente larghe per utilità.

I valori sono soglie pratiche proposte del progetto, non significatività,
garanzie operative o requisiti universali delle aziende. Riportare i due target
separatamente anche se solo uno passa. Non allentare le soglie se falliscono,
né scegliere un'altra finestra o metodo per questa esecuzione.

## Output e verifiche

Prima del fit reale salvare snapshot delle impostazioni approvate, hash dei
due input e elenco delle origini. Poi traccia completa: origini usate, loro
disponibilità, numero di giorni/ore, rango dei quantili e correzioni MW.
Risultati in cartella nuova, con file dei forecast trasformati e manifest.

L'HTML includerà tabelle prima/dopo con delta assoluti e percentuali, coperture
anche in punti percentuali e conteggi, ampiezze, confronto con baseline,
grafici e criteri superati/falliti. Tutti i punteggi verranno ricalcolati
indipendentemente dai forecast salvati, verificando identità delle mediane.

In questo step sono stati implementati solo i primitivi del metodo, con
docstring, type hint e cinque test sintetici: cutoff esatto48ore, indisponibilità
di presente/futuro, invarianti, annidamento, mancanti, duplicati e assenza di
clipping. Nessun risultato di calibrazione reale è ancora disponibile.
Controllo completo del progetto:362test passati,uno smoke facoltativo escluso,
dipendenze coerenti e Ruff pulito.
