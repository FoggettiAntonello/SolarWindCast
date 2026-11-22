# Ultimo confronto eolico — protocollo proposto, 14 novembre 2026

[Presentazione con metriche prima/dopo](../reports/final_wind_protocol_20261114/presentazione.html).
Configurazione unica: `final_wind_experiment` nel YAML. Preparazione autorizzata
con «procedi con il prossimo step»; esecuzione e budget non ancora approvati.

## Domanda e candidato fissati

Il candidato eolico 28M con calendario, contesto 12 mesi e calibrazione delle
ampiezze già studiata conserva un vantaggio puntuale e probabilistico su un
periodo più lungo? Non introdurre una nuova correzione per cercare una vittoria.
Il confronto è conclusivo per questa iterazione di ricerca, non una prova
conclusiva di superiorità scientifica.

Target: energia del prossimo mese UTC della zona Sud, eolico terra + mare.
Macroarea e soli dati onshore non entrano in questo confronto. Input: stessi
dataset Sud e revisioni verificati, mancanti conservati. Pesi locali 28M,
revisione `49b26409ac87b5935539a5d8ffe7f397b720db47`, Timestral 1.0.0,
codice `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff`. Verificare nuovamente
API ufficiale e hash prima dell'eventuale esecuzione; nessun aggiornamento.

Emissione 12 ore prima del mese; escludere interamente il mese ancora in corso.
Prevedere due passi di potenza media mensile e valutare il secondo, convertendo
ogni quantile in MWh con le ore del mese. Non sommare quantili orari.
Calibrazione: stesso fattore positivo regolarizzato, minimo sei errori passati,
lookback 24 mesi, scala 0,5–1,5, penalità 0,05, 80 iterazioni; mediana invariata.
Nessun clipping, correzione della mediana, fine tuning o ricerca di griglia.

## Periodo e disponibilità causale

Un solo confronto esplorativo su novembre 2024–ottobre 2026: 24 mesi di
calendario; i forecast mancanti o le osservazioni incomplete vengono elencati,
non eliminati silenziosamente. Usare gli stessi mesi per ogni confronto.
Il vecchio test è già stato osservato e resta tale, anche dopo questo protocollo.
Nessuna nuova etichetta di «test indipendente» o promozione operativa.

Per il primo fit riusare i 16 forecast sviluppo del candidato, luglio 2023–
ottobre 2024. Per ogni origine entrano solo gli errori di mesi conclusi entro
il cutoff fissato, dal più recente meno il ritardo dichiarato: per novembre
2024 il mese massimo è settembre 2024, quindi ottobre è escluso.
Proseguendo nel tempo, errori dei mesi precedenti del confronto possono entrare
nel fit solo dopo che sarebbero disponibili allo stesso cutoff. È una
simulazione causale del calibratore, non assenza di selezione retrospettiva
dell'esperimento. Non aggiornare pesi, metodo, soglie o iperparametri.

## Riferimenti e budget chiuso

- Primario: 28M con calendario e contesto 24 mesi, fissato come prima.
- Controllo: stesso candidato 12 mesi senza calibrazione.
- Baseline: ultimo mese completo, media recente, anno precedente e distribuzione
  stagionale con errori rolling, con impostazioni originali congelate.
- Mostrare anche le altre varianti Timestral già eseguite come riferimenti
  descrittivi, senza sceglierle dopo i nuovi risultati.

Massimo proposto **24 nuove inferenze** 28M, una per mese; raw forecast riusato
per candidato calibrato e controllo. CPU un thread, solo checkpoint locali.
Zero training e download. I riferimenti a 24 mesi e le baseline sono in cache
e devono essere verificati: se incoerenti, interrompere invece di ampliare il
budget. Eventuali cache valide delle 24 nuove previsioni riducono le chiamate.
Il budget oggi approvato è zero. Non si eseguono prove in questa preparazione.

Prima dell'inferenza salvare snapshot approvato con hash di protocollo, dati,
pesi, previsioni precedenti e ambiente; registrare ogni chiamata effettiva.
Riutilizzare originali e salvare il nuovo risultato in una cartella separata.

## Criteri proposti prima dell'esecuzione

Riapplicare criteri prudenti analoghi a quelli già approvati, senza cambiare
l'esito fallito dello screening precedente. Per qualificare il nuovo confronto
come promettente solo **in senso esplorativo**, richiedere tutti:

1. Almeno 12 mesi comuni valutabili e MAE almeno 5% inferiore al riferimento
   primario e a ciascuna baseline, inclusa quella con errori rolling, sugli
   stessi mesi puntuali comuni.
2. Errori assoluti minori del riferimento in almeno il 60% dei mesi comuni;
   con 24 casi sono almeno 15 vittorie, senza contare i pareggi.
3. RMSE e pinball non peggiori del riferimento primario. Confronto probabilistico
   aggiuntivo contro la baseline rolling sugli stessi casi quantili: pinball
   non peggiore; se i casi sono meno, renderlo esplicito e non dichiarare il
   criterio superato senza dati sufficienti.
4. Copertura osservata non inferiore al riferimento a 80% e 90%, ampiezze
   non superiori al 110% del riferimento; riportare anche scarto dal nominale.

La baseline rolling può avere una mediana più forte di quelle deterministiche:
non ometterla dal criterio puntuale. Se mancano casi comuni sufficienti con
questa baseline, il criterio complessivo non è dimostrato. Il 5% non è
significatività statistica né uno standard aziendale.
Nessuna regola di copertura relativa garantisce probabilità corrette.

Se un criterio fallisce: riportare il fallimento e fermare le modifiche in
questa iterazione; nessun secondo metodo, cambio di contesto o nuove taglie.
Se tutti passano: descrivere l'evidenza esplorativa e proporre una futura
verifica con emissioni registrate prima degli esiti, non promuovere in automatico.
Date e durata prospettiche restano DA DECIDERE; non occorre fingere di avere
già tale conferma per consegnare un progetto sperimentale onesto.

## Resoconto HTML richiesto

Tabelle per tutti i modelli con MAE, RMSE, bias, pinball, coperture e ampiezze
80/90%; confronto candidato–controllo e candidato–riferimento con differenze
assolute e percentuali. Coperture anche in punti percentuali e conteggi x/n.
Variazione percentuale non definita se il riferimento è zero. Evidenziare
miglioramenti e peggioramenti; la copertura si legge rispetto al nominale,
non con la regola «più è sempre meglio».

Grafici per origine, errori mensili, bande contro osservazioni e tabella dei
criteri. Riportare mesi comuni, esclusioni, denominatori e limite del vecchio
test già visto. Non mescolare i nove mesi storici della calibrazione con i
24 mesi di questo confronto. In questa preparazione non esistono nuove
metriche: l'HTML mostra i nove mesi precedenti e segnaposto per il futuro.
