# Raccordo Sud/Rossano — 11 novembre 2026

[Presentazione](../reports/south_rossano_audit_20261111/presentazione.html) e
[audit con provenienza](../reports/south_rossano_audit_20261111/audit.json).

## Risultato e regola candidata

Il 30 dicembre 2020 la somma di Nord, Centro-Nord, Centro-Sud, Sud,
Sardegna, Sicilia e Rossano coincide con il totale nazionale in ciascuna
delle 24 ore, per solare ed eolico a terra. Senza Rossano mancano 103 MWh
solari e 1.003 MWh eolici. La tolleranza prefissata è 0,000001 MW;
il residuo osservato con Rossano è zero.

Il campione sostiene quindi che Rossano sia un contributo separato da aggiungere.
Non dimostra la correttezza della ricostruzione in ogni data: nazionale e zone
provengono dallo stesso fornitore, non da misure indipendenti.

| Periodo candidato | Somma stretta delle osservazioni |
| --- | --- |
| Dal 1 gennaio 2019 fino al 31 dicembre 2020, 23:00 UTC escluso | Sud + Rossano |
| Dal 31 dicembre 2020, 23:00 UTC | Sud + Calabria |

Tre risposte di quattro ore attorno al cambio verificano il confine:
Rossano termina alle 23:00 UTC, Calabria inizia nello stesso istante.
È mezzanotte del 1 gennaio 2021 in Europe/Rome. Dicembre 2020 UTC include
quindi un'ultima ora della nuova configurazione. Il prototipo produce quattro
ore complete senza sommare due volte il confine e senza sostituire NaN con zeri.

Il limite iniziale 2019 è una proposta prudente: prima servono verifiche
aggiuntive sugli altri poli e sulle modifiche territoriali. La copertura
integrale dal 2019 non è stata verificata o scaricata.

## Perimetro e limiti

Sei nuove risposte giornaliere, due riusate e tre nuove risposte di quattro
ore. Originali conservati con metadati; report e ricetta hanno un manifesto
con hash. Nessuna inferenza, training, acquisizione completa o modifica dei
dataset e dei risultati precedenti. La zona Sud ufficiale resta il target
degli esperimenti esistenti; la macroarea è un eventuale target distinto.

La ricetta è sostenuta dai campioni solo per solare e onshore. Non risolve
l'offshore: i mancanti restano NaN, senza applicare zeri strutturali.
Ogni eventuale lotto successivo dovrà verificare domini, griglia, unità,
revisioni e copertura. Il prototipo rifiuta intervalli sovrapposti, buchi
nei regimi e target incompatibili.

## Fonti e verifica

- [ARERA 386/2018](https://www.arera.it/fileadmin/allegati/docs/18/386-18.pdf).
- [ARERA 297/2020](https://www.arera.it/fileadmin/allegati/docs/20/297-20.pdf).
- [GME: cambio di configurazione 2021](https://www.mercatoelettrico.org/it-it/Home/MediaGME/ArchivioNews?id=2431).
- Risposte ENTSO-E A75/A16 e inventario degli originali nell'audit.

Verifica locale: `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`.
Esito: 348 test superati, uno smoke test reale facoltativo escluso; Ruff pulito.

## Prossimo passo

Definire con evidenza una politica offshore e presentare il piano di
acquisizione a lotti. Download esteso e cambio operativo del target richiedono
approvazione. Nessun miglioramento predittivo è dimostrato da questo audit.
