# SolarWindCast v1.0.0 — 23 novembre 2026

Prima versione del progetto portfolio per valutare previsioni probabilistiche
di produzione solare ed eolica nella zona di mercato Sud Italia. Comprende
acquisizione e controllo dei dati, Timestral 5M/28M, baseline, backtest temporale,
calibrazione e presentazione dei risultati. La zona Sud non coincide con la sola Puglia.

## Contenuto

- Pipeline Python configurabile, timestamp UTC, distinzione MW/MWh e mancanti
  conservati come NaN. Originali, metadati e hash rimangono nel percorso locale.
- Previsione dell'energia mensile e percorso sperimentale sulle successive 24 ore.
  Timestral viene usato senza riaddestrare i pesi; covariate calendario nel mensile,
  solo target nel percorso orario. Nessun meteo nei risultati pubblicati.
- Confronto con baseline sulle stesse finestre; MAE, RMSE, pinball, copertura
  e ampiezza degli intervalli. Calibrazione causale degli errori, mediana invariata.
- Demo sintetica senza token o checkpoint, test automatici e CI Windows/CPU.
- README con dipendenze e revisioni fissate, risultati aggregati e limiti.
  Presentazione HTML da dodici slide; PowerPoint/PDF da tredici con autore e foto.

## Risultati e limiti

Nel confronto orario sulle date prestabilite, il MAE del 5M è inferiore alla
migliore baseline del campione del **4,18% sul solare** (69 giornate, 1.656 ore)
e del **4,97% sull'eolico** (72 giornate, 1.728 ore). La qualità probabilistica
grezza è peggiore del riferimento probabilistico e gli intervalli sono sottocoperti.

La calibrazione oraria eolica riduce la pinball dell'**11,35%** rispetto allo
stesso modello grezzo su 54 giornate/1.296 ore. Rimane peggiore della baseline
probabilistica del **7,91%**, con intervallo al 90% più ampio del **37%**.
Sono campioni distinti: le percentuali non si sommano.

I confronti sfavorevoli sono conservati. Il candidato eolico mensile finale
peggiora MAE e pinball rispetto al riferimento a contesto più lungo.
Non è dimostrata una superiorità generale di Timestral né un beneficio
economico aziendale. Valutazione retrospettiva su dati revisionati, finestre
già esaminate, ore correlate e ritardi di pubblicazione assunti.

## Riproduzione e verifiche

Il setup da zero è in [docs/setup.md](https://github.com/FoggettiAntonello/SolarWindCast/blob/v1.0.0/docs/setup.md).
La demo `solarwindcast.backtest_demo --baselines-only` permette di verificare
la pipeline senza dati reali, token o pesi. Per rieseguire gli esperimenti
energetici occorre acquisire separatamente dati e checkpoint, rispettare
licenze e protocolli e scegliere destinazioni nuove.

Prima del rilascio vengono verificati test, Ruff, dipendenze, demo, inventario
pubblico, assenza di credenziali rilevabili e hash dei documenti. Il test con
pesi reali è opzionale e non viene eseguito dal CI ordinario.

## Distribuzione e licenze

Gli allegati della release comprendono PDF, PowerPoint, metriche aggregate
e checksum SHA-256. Il sorgente è disponibile negli archivi automatici GitHub.
Non sono inclusi dati originali/elaborati, serie complete di previsioni,
pesi, token, ambienti virtuali o archivi privati.

Codice originale MIT; codice Timestral Apache-2.0; pesi Timestral sotto
Modified MIT con clausola sul fatturato, descritta nel README. Dati, mappa,
foto e altre immagini mantengono diritti e attribuzioni separati.

La presentazione è su [GitHub Pages](https://foggettiantonello.github.io/#progetti).
Il sito ospita documenti statici e non esegue Timestral. Azure non è attivato.
Fine tuning reale, confronto LightGBM/altri modelli, Streamlit e nuovi
esperimenti sono rinviati e non fanno parte di questa versione.
