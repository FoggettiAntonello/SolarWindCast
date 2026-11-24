# Verifiche tecniche della versione 1.0.0

## Release

La [release v1.0.0](https://github.com/FoggettiAntonello/SolarWindCast/releases/tag/v1.0.0)
è stata pubblicata sul commit `7f10b1e4d7fcaa650c04eb9cbe73883c01ee92e1`.
Il [CI di quel commit](https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45245205817)
ha superato 380 test, con uno smoke test opzionale escluso, controlli Ruff,
compatibilità delle dipendenze, demo sintetica con baseline e audit del sito.
Questi sono gli esiti del rilascio originale, non il conteggio di eventuali
verifiche successive. Le [note di versione](release_v1.0.0.md) descrivono il perimetro.

## Setup

Il collaudo locale ha verificato una nuova venv Windows/Python 3.12.10,
dipendenze reinstallate da wheel e PyTorch 2.11.0+cu128. La wheel del progetto
è stata installata e provata fuori dalla cartella dei sorgenti, con importazione
isolata e demo sintetica senza pesi. La verifica CPU con installazione da
Internet è stata eseguita separatamente nel runner GitHub Actions.
I comandi riproducibili sono in [setup.md](setup.md).

## Archivi e dati

Il repository distribuisce codice, test, configurazione, documentazione,
metriche aggregate e presentazioni. Originali energetici, dataset elaborati,
pesi, cache e archivi storici completi restano locali. Gli output sintetici
dimostrativi possono essere rigenerati con la demo; non sono risultati reali.
La documentazione scientifica e i confronti sfavorevoli restano disponibili
nei [risultati completi](portfolio/details.html#complete).

## Sito e allegati

Il [sito personale](https://foggettiantonello.github.io/#progetti) ospita
PDF e PowerPoint statici, senza eseguire Timestral nel cloud. La release
contiene PDF, PowerPoint, metriche aggregate e checksum SHA-256; i quattro
allegati sono stati scaricati pubblicamente e verificati dopo il rilascio.
Azure non è stato attivato.

## Limiti delle verifiche

Test e audit non dimostrano una superiorità generale del modello, una
validazione prospettica o un beneficio economico operativo. L'audit dei file
controlla il perimetro pubblico e alcuni tipi di credenziali: non certifica
l'assenza di ogni possibile informazione riservata nella cronologia Git.
