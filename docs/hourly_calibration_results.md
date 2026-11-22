# Calibrazione oraria — risultati del 15 novembre 2026

[Resoconto HTML](../reports/hourly_calibration_results_20261115/presentazione.html),
[metriche e tracce](../reports/hourly_calibration_results_20261115/results.json),
[protocollo approvato](hourly_calibration_protocol.md).

Con «procedi pure» l'utente ha approvato metodo, finestra, campione e criteri.
Il replay è concluso: **zero nuove inferenze, training o download**. Sono state
riusate le previsioni grezze dei due piloti, senza modificarle. Mediana e punti
sono identici, quindi MAE, RMSE e bias rimangono esattamente invariati sui casi comuni.

## Solare: 36 giornate, 864 ore comuni

| Metrica | Grezzo | Calibrato | Baseline probabilistica |
| --- | ---: | ---: | ---: |
| MAE MW | 141,82 | 141,82 | 136,41 |
| RMSE MW | 289,20 | 289,20 | 291,24 |
| Pinball MW | 41,86 | 41,59 | 34,47 |
| Copertura80 | 67,25% | 78,24% | 82,52% |
| Ampiezza80 MW | 222,10 | 265,87 | 364,00 |
| Copertura90 | 78,36% | 89,58% | 85,76% |
| Ampiezza90 MW | 301,64 | 476,51 | 444,89 |

Pinball **-0,63%** rispetto al grezzo, meno del -5% richiesto e ancora
**+20,68%** rispetto alla baseline probabilistica. Coperture vicine ai nominali;
ampiezze nei limiti rispetto alla baseline, ma i criteri pinball falliscono.
**Nessuna promozione.**

Il MAE sul sottoinsieme è peggiore del 3,96% rispetto alla baseline migliore,
mentre sul campione più ampio dell'estensione era migliore. Questo dipende
dalle giornate confrontate: non è un cambiamento della previsione dovuto alla
calibrazione e va conservato come evidenza di variabilità dei risultati.

## Eolico terra + mare: 54 giornate, 1.296 ore comuni

| Metrica | Grezzo | Calibrato | Baseline probabilistica |
| --- | ---: | ---: | ---: |
| MAE MW | 707,34 | 707,34 | 768,62 |
| RMSE MW | 942,91 | 942,91 | 1.028,58 |
| Pinball MW | 213,25 | 189,04 | 175,18 |
| Copertura80 | 48,23% | 79,32% | 72,99% |
| Ampiezza80 MW | 1.225,46 | 2.349,93 | 2.153,75 |
| Copertura90 | 60,65% | 90,28% | 83,02% |
| Ampiezza90 MW | 1.614,00 | 3.456,52 | 2.522,94 |

Pinball **-11,35%** rispetto al grezzo; coperture molto più vicine ai nominali,
senza perdere il vantaggio puntuale sullo stesso sottoinsieme (MAE **-7,97%**
rispetto alla migliore baseline puntuale del campione, distribuzione stessa ora).
Tuttavia pinball ancora **+7,91%** rispetto alla baseline probabilistica e
ampiezza90 **+37,00%** rispetto a essa, contro il +10% ammesso.
Questi due criteri falliscono: **nessuna promozione complessiva**.

## Metodo e casi comuni

Un solo metodo approvato: allargamenti additivi nonnegativi80/90, separati
per target e con correzione90 almeno pari alla80. Stessa correzione su tutte
le ore del giorno, senza clipping, ricerca di parametri o correzioni dei punti.
Finestra180giorni, almeno20giornate complete e disponibilità soltanto dopo la
fine dell'orizzonte24ore più ritardo assunto24ore.

Origini1/8/22 tra maggio2025 e ottobre2026. Il giorno15 entra soltanto nello
storico quando disponibile. Solare:15 esclusioni per storico insufficiente,
più3 esclusioni originali per il buco nel contesto. Eolico:nessuna esclusione.
Piano e casi effettivi coincidono. Le origini escluse non sono state sostituite.

Tutte le sei varianti per target (grezzo, calibrato e quattro baseline) sono
valutate sugli stessi timestamp. I riferimenti deterministici non hanno
pinball o intervalli; la baseline probabilistica è la distribuzione della
stessa ora. Diagnostiche per giorno, mese e ora prevista nel JSON e nell'HTML.

## Verifiche e riproducibilità

Snapshot prima del fit: configurazione, hash delle sorgenti, versione del
modulo e piano delle origini. Traccia di ogni fit con origini usate, orari
di disponibilità, numero di giorni/ore, ranghi e correzioni in MW.
Nessun vecchio file riscritto. Risultati, forecast trasformati, due grafici SVG
autonomi e manifesto sono nella nuova cartella dei risultati.

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.hourly_calibration --config configs/project.yaml
```

L'esecuzione è disabilitata dopo la conclusione e il comando protegge l'output
esistente. Una riproduzione del replay richiede riapprovare la destinazione;
la lettura e verifica delle metriche salvate non richiede nuove inferenze.

Controllo completo: **367 test passati, uno smoke facoltativo escluso**, pip
coerente e Ruff pulito. Dieci test sintetici del modulo verificano cutoff,
assenza di influenza delle etichette future, mediane e sorgenti invariate,
casi comuni e criteri che non premiano indiscriminatamente la copertura.
Dopo le sole modifiche di presentazione, test mirati e Ruff ricontrollati.

Verifica indipendente dai forecast: MAE, RMSE, bias, pinball, coperture,
ampiezze, tutti i casi comuni, ordinamento dei quantili e identità dei punti.
Ogni correzione ricostruita tramite ordinamento completo dei punteggi,
separato dalla selezione tramite `numpy.partition` usata nel fit. Hash di
sorgenti e snapshot verificati; nessun secondo esperimento scientifico.

## Cosa possiamo affermare e cosa resta aperto

La calibrazione ha corretto molta della sottocopertura, soprattutto eolica,
ma non supera tutti i criteri di qualità probabilistica e ampiezza rispetto
alla baseline. Non allentare tali criteri o scegliere un'altra finestra a
posteriori. I risultati supportano questa affermazione limitata, non una
superiorità operativa generale di Timestral.

Le ore sono correlate, le giornate sparse, i periodi già esaminati e i dati
revisionati. Il ritardo di pubblicazione è assunto. Fit causale non rende
indipendente il test né garantisce coperture conformali su queste serie.
Non sommare quantili orari per formare intervalli sull'energia giornaliera.

Prima di altri esperimenti fare il punto con l'utente: si può documentare
il vantaggio puntuale eolico e il compromesso sugli intervalli, mantenendo
la baseline come riferimento. Nessuna nuova variante, calibrazione, raccolta
dati o pubblicazione è avviata automaticamente dopo questo risultato.
