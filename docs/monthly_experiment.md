# Step 11 — confronto mensile reale

[Apri il report HTML](../reports/step11_monthly_20261107/presentazione.html).
Esperimento del 7 novembre 2026, con protocollo approvato e congelato prima
dell'esecuzione. Dati ENTSO-E zona Sud, non della sola Puglia.

## Esecuzione effettiva

- Sviluppo: novembre 2021–ottobre 2024; test: novembre 2024–ottobre 2026.
- Solare ed eolico terra + mare separati. Stesse origini e stesso cutoff
  per tutti i metodi; mese UTC, emissione 12h prima del mese obiettivo.
- Contesto di 24 mesi, ultimo disponibile il penultimo rispetto al target.
  Due passi mensili previsti; solo l'ultimo valutato. Nessun valore osservato
  del mese in corso viene inserito per arrivare al secondo passo.
- Previsione diretta di potenza media mensile e conversione di punto e quantili
  in MWh con le ore del mese. Nessuna somma di quantili orari.
- Timestral 5M e 28M caricati dai checkpoint locali fissati, senza riaddestramento;
  varianti solo serie e calendario noto. CPU con un thread. Nessun download
  dei pesi, uso di token o GPU per l'esperimento.
- Tre baseline puntuali e baseline stagionale con quantili degli errori rolling
  disponibili prima del cutoff, secondo le regole congelate.
- 11 origini di sviluppo e 24 di test per target dopo il warm-up. Prodotte
  560 righe, incluse le disponibilità mancanti della baseline probabilistica;
  280 chiamate ai backend reali Timestral. Le previsioni del mese solare
  incompleto sono conservate, ma non vengono valutate senza osservazione valida.

L'adattatore mensile usa soltanto il caricatore verificato del wrapper comune;
non simula mesi come timestamp orari regolari. Il campo orario `0h` richiesto
dal validatore del caricatore non è una regola di disponibilità: il cutoff è
calcolato esclusivamente sui mesi reali.

## Risultati del test

| Target | Concorrente | MAE MWh |
|---|---|---:|
| Solare | Stagionale + errori storici | 29156,02 |
| Solare | Timestral 28M con calendario | 32544,11 |
| Solare | Stesso mese anno prima | 37415,99 |
| Solare | Timestral 28M solo serie | 39279,30 |
| Eolico | Media mesi recenti | 199707,77 |
| Eolico | Timestral 5M con calendario | 181868,21 |
| Eolico | Timestral 28M con calendario | 189628,62 |
| Eolico | Stesso mese anno prima | 225001,90 |

La tabella evidenzia anche confronti sfavorevoli: il miglior MAE solare è della
baseline corretta; 28M solo serie perde anche contro la baseline annuale non
corretta. Sull'eolico 5M con calendario ha circa 9% di MAE in meno della
baseline con errore più basso nel campione. Queste sono descrizioni del test,
non scelte di nuovi iperparametri o prova statistica di superiorità generale.
Il report e i JSON conservano tutte le varianti, non soltanto le migliori.

## Affidabilità degli intervalli

Gli intervalli mensili non sono stati ricalibrati dopo aver visto il test.
Per il solare 28M con calendario copre 17/23 casi nell'intervallo nominale 80%
e 19/23 nel 90%; le ampiezze medie sono circa 92 e 130 GWh. La baseline
probabilistica copre 19/23 e 20/23, con bande più larghe (114 e 142 GWh).
28M con calendario ha però pinball media inferiore alla baseline: circa
7521 contro 7943 MWh sui cinque quantili comuni. Errore puntuale, copertura
e nitidezza non raccontano la stessa cosa.

Per l'eolico 5M con calendario copre 20/24 casi nell'80% e 22/24 nel 90%,
con ampiezze medie circa 620 e 845 GWh. Un valore vicino alla copertura nominale
su 24 mesi non garantisce calibrazione futura; i mesi possono essere correlati.

Dodici righe previsive del test hanno almeno un quantile negativo sulla griglia
salvata. I valori non fisici sono conservati e segnalati, senza clipping come
previsto. La diagnostica non confronta direttamente griglie di diversa
numerosità: Timestral salva 21 livelli, la baseline ne salva cinque.

## Casi comuni ed esclusioni

Le metriche puntuali usano un'intersezione esplicita dei casi validi tra tutti
i concorrenti. La parte probabilistica usa una propria maschera comune sui
modelli con quantili, ai livelli 0,05/0,10/0,50/0,90/0,95.

Nel test: 23 mesi solari e 24 eolici. In sviluppo: 11 mesi solari ma solo quattro
eolici comuni a tutti i metodi, perché la baseline probabilistica deve avere
almeno 12 coppie storiche valide. Le previsioni di Timestral degli altri mesi
non vengono cancellate: restano nel file completo. Questo campione di sviluppo
eolico molto piccolo non supporta conclusioni forti.

Ogni confronto perso da Timestral contro la baseline annuale è elencato
nel report, oltre ai conteggi di vittorie, sconfitte e pareggi. L'errore è
mostrato per mese dell'anno, con uno o due casi per barra; non per ora del giorno,
perché il target confermato è un totale mensile.

## Riproduzione

Prima eseguire i controlli, poi usare una directory nuova:

```powershell
.\scripts\check.ps1
.\.venv\Scripts\python.exe -B -m solarwindcast.monthly_experiment `
  --config configs/project.yaml --output reports/nuovo_backtest_mensile
```

Servono `monthly_execution.authorized=true`, dati e pesi locali e snapshot
congelato integro. Il campo `monthly_protocol.experiment_enabled=false` rimane
parte dello snapshot storico; non va modificato per eseguire, perché cambierebbe
il protocollo. L'autorizzazione separata abilita soltanto il comando mensile.

Il comando confronta hash delle impostazioni, dati preparati e checkpoint,
esegue lo sviluppo prima del test, salva checkpoint di avanzamento e fallisce
esplicitamente su anomalie. Non elimina risultati precedenti o ritenta una
variante con impostazioni diverse. Nessuna taratura sul test finale effettuata.

`predictions.json` conserva punti MWh, tutti i quantili nativi, dati osservati
anche quando mancanti, mesi del contesto, cutoff, mesi decodificati, coppie di
calibrazione e variante. `results.json` conserva score, denominatori, esclusioni,
versioni, revisioni e hash dei pesi; il manifest verifica i tre file consegnati.
I nomi `_mwh` sono espliciti nell'adattamento delle metriche comuni, che
numericamente lavorano nell'unità dei valori ricevuti.

## Limiti e scope

Confronto retrospettivo su dati revisionati: prima pubblicazione, capacità
installata e versione storica non sono ricostruite. Non è certificata l'assenza
di sovrapposizione col pretraining. Il test è separato dalle decisioni del
progetto; non diventa una prova di accuratezza operativa.

La prima esecuzione mensile approvata esclude meteo: le varianti con covariate
meteo passate e future non sono state eseguite e restano rinviate alla verifica
degli archivi e dell'orizzonte. Lo Step 11 è concluso nel perimetro mensile
congelato, non con l'intero disegno meteorologico del primo piano orario.

Codice Apache 2.0, pesi Modified MIT. Testi applicabili ai checkpoint recuperati
e verificati direttamente, conservati con attribuzione:
[5M](licenses/Timestral-5M_bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f_LICENSE.txt),
[28M](licenses/Timestral-28M_49b26409ac87b5935539a5d8ffe7f397b720db47_LICENSE.txt).
Clausola sui 20 milioni di dollari di fatturato consolidato mensile descritta nel README.

Fonti ufficiali verificate prima dell'uso:
[Timestral](https://github.com/mistralai/timestral),
[checkpoint 28M](https://huggingface.co/mistralai/Timestral-28M),
[quantili NumPy](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html),
[grafici degli intervalli](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.fill_between.html).
