# Estensione oraria — 14 novembre 2026

[Report HTML](../reports/hourly_extension_20261114/presentazione.html).

L'utente ha autorizzato più giornate con lo stesso modello. Fissati prima
del calcolo i giorni1,8,22 di ogni mese novembre2024–ottobre2026, alle00UTC.
Il giorno15 del pilota resta separato. Nessun cambiamento scientifico:
5M target-only, contesto672ore, ritardo assunto24ore, orizzonte24ore dopo
il gap; stessi dati Sud, pesi, baseline e quantili. Nessun meteo o download.
Snapshot prima delle inferenze; confronto delle impostazioni e provenienza
con il pilota. Massimo144 inferenze, effettive141.

## Esito sulle sole nuove date

| Target | Giorni / ore | MAE5M MW | MAE migliore baseline MW | Delta MAE | Delta pinball vs distribuzione stessa ora |
| --- | --- | ---: | ---: | ---: | ---: |
| Solare | 69 / 1656 | 131,70 | 137,45 | -4,18% | +18,70% |
| Eolico terra + mare | 72 / 1728 | 725,26 | 763,18 | -4,97% | +24,02% |

Baseline migliore descrittiva: distribuzione stessa ora per solare,
persistenza per eolico. La persistenza non ha intervalli: il confronto
probabilistico usa separatamente la distribuzione stessa ora, senza
attribuire alla persistenza punteggi che non possiede.

Copertura80 Timestral: solare68,60%, eolico45,89%; copertura90:
solare78,56%, eolico58,22%. Sottocopertura importante, nessuna promozione.
Le nuove date ripetono un vantaggio puntuale modesto sulle baseline del
campione, ma non migliorano la qualità probabilistica rispetto al riferimento.

Tre esclusioni solari: 8aprile,22aprile e1maggio2026, per l'ora mancante del
2aprile inclusa nei28giorni di contesto disponibile. Stesse esclusioni per
tutte le baseline. Nessuna giornata sostitutiva scelta dopo aver visto l'esito.

Il primo pilota rimane 23giorni solari/24eolici, con MAE relativo -5,36%/-7,73%.
Il confronto tra questi numeri e -4,18%/-4,97% cambia giornate e, per l'eolico,
baseline migliore: non è un peggioramento del modello nel tempo o l'effetto
di una modifica. L'HTML separa i due campioni e mostra tutti i modelli.

## Controlli, riproduzione e limiti

357 test superati, uno smoke facoltativo escluso; pip/Ruff puliti.
Test sintetici per calendario disgiunto, parametri invariati e cutoff.
Metriche, intervalli, origini comuni e hash vecchi/nuovi ricontrollati
indipendentemente. Nessun vecchio forecast modificato o rieseguito.

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.hourly_extension --config configs/project.yaml
```

Comando disabilitato dopo conclusione; output esistente protetto. Il dataset
è revisionato, il ritardo24ore è ipotizzato, non ricostruito dai tempi effettivi
di pubblicazione. I mesi erano già studiati e i contesti si sovrappongono:
nuove giornate non equivalgono a una conferma indipendente. Ore correlate,
campione non esaustivo. Nessun confronto diretto con MAE mensile in MWh.

Prossimo passo proposto: un protocollo di calibrazione oraria causale con
mediana fissa, finestra di fit e periodo di valutazione dichiarati prima
del calcolo. Valutare pinball, copertura e ampiezza sugli stessi casi; non
ottimizzare sul periodo completo. Nessuna calibrazione è stata eseguita
o autorizzata automaticamente in questa estensione.
