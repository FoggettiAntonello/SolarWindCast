# Protocollo mensile — approvato e congelato

Step 10 concluso il 7 novembre 2026. L'utente ha confermato mese UTC ed eolico
terra + mare come ultime scelte del protocollo presentato.
[Protocollo HTML congelato](../reports/step10_monthly_protocol_frozen_20261107/presentazione.html).
Configurazione nel solo YAML, sezione `monthly_protocol`, con `approved: true`
ed `experiment_enabled: false`. Lo Step 11 resta da autorizzare.
Non sono stati calcolati errori, previsioni o coperture.

## Risultato e calendario

Un valore di energia in MWh per il prossimo mese di calendario, separatamente
per solare ed eolico della zona Sud. Sono confermati:

- mesi UTC, coerenti con l'audit;
- eolico uguale alla somma terra + mare, solo quando entrambe le componenti sono presenti.

L'assenza iniziale dell'offshore non sarà trasformata in zero. Un mese eolico
è completo solo se entrambe le componenti sono interamente disponibili.

## Una distribuzione direttamente mensile

Per ogni mese completo calcoliamo la potenza media mensile:

`potenza_media_mese_MW = energia_mese_MWh / ore_del_mese`.

Timestral prevede questa sequenza di valori mensili, senza riaddestramento.
Per il mese obiettivo, mediana e ciascun quantile sono moltiplicati per le ore
del mese. La durata è una quantità positiva nota dal calendario: questa
trasformazione preserva l'ordine e il significato dei quantili del singolo mese.
**Non si sommano quantili orari o giornalieri.**

La normalizzazione per durata evita di trattare automaticamente un febbraio
più corto come un calo di potenza. Non corregge crescita della capacità,
cambiamenti tecnologici o revisioni della fonte.

L'API ufficiale riceve sequenze numeriche e non impone timestamp orari: il
calendario mensile va mantenuto nei metadati. Il wrapper attuale dei dataset
orari non va riutilizzato assegnando ai mesi frequenze orarie fittizie. L'adattatore
calendario/output MWh sarà lavoro dello Step 11, dopo l'approvazione.

## Emissione e informazioni disponibili

Emissione concordata: **12 ore prima dell'inizio del mese obiettivo**.
Usiamo **24 mesi di contesto**, fino al penultimo mese rispetto al target.
Il mese immediatamente precedente è ancora in corso all'emissione e viene
escluso interamente dal primo protocollo.

Esempio UTC: per novembre 2024 si emette il 31 ottobre alle 12:00.
Il contesto comprende ottobre 2022–settembre 2024. Timestral prevede due passi
mensili, ottobre e novembre; si valuta solo novembre. Non si inserisce il
valore osservato di ottobre per arrivare al secondo passo.

Questo è un confronto **retrospettivo con dati revisionati**. La scelta evita
di usare un mese non ancora concluso, ma non ricostruisce la versione dei dati
o la prima pubblicazione disponibili allora. Non dimostra prestazioni operative.
L'eventuale uso delle osservazioni parziali del mese in corso sarà un altro
protocollo, da dichiarare e confrontare separatamente.

## Modelli e impostazioni fissate

Timestral 1.0.0, codice `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff`:

| Taglia | Revisione pesi locale |
|---|---|
| 5M | `bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f` |
| 28M | `49b26409ac87b5935539a5d8ffe7f397b720db47` |

Entrambi i file dei pesi e i relativi config sono presenti in cache. Nessun
modello è stato caricato o scaricato in questo step. Dispositivo proposto CPU,
lettura solo locale, nessun fallback o aggiornamento automatico.
I checkpoint consentono contesti sotto una patch; il codice installato applica
padding non osservato e maschere. Questo non certifica accuratezza su 24 mesi.

Varianti proposte: solo target; target con seno/coseno del mese come covariate
future note. Il meteo è rinviato finché archivio, orizzonte mensile e disponibilità
non saranno verificati. La variante con meteo passato non è dichiarata eseguita.
I mancanti sono passati con maschere native, senza imputare gli originali;
il preprocessing interno del backend resta documentato. Nessun clipping delle
previsioni negative nel primo confronto: valori negativi segnalati e conservati.

## Baseline

Le baseline utilizzano la stessa informazione disponibile prima dell'emissione:

1. Ultimo mese completo e valido disponibile, espresso in potenza media, poi
   moltiplicato per le ore del mese obiettivo.
2. Stesso mese dell'anno precedente, corretto nello stesso modo per la durata.
3. Potenza media sui tre mesi completi validi più recenti nel contesto, pesata
   per le ore effettive, poi estesa alla durata del mese obiettivo. I mesi
   selezionati devono essere registrati: non è un riempimento dei mesi mancanti.

Riferimento probabilistico proposto: baseline stagionale più quantili empirici
dei suoi errori rolling in potenza media mensile. La finestra di calibrazione
è di 24 mesi di calendario già disponibili, con almeno 12 coppie valide tra
osservazione e stesso mese dell'anno precedente. Nessuna coppia oltre il cutoff.
Metodo di quantile `linear`, fissato prima del test. La previsione puntuale di
questa variante è il suo quantile 0,5; la baseline stagionale non corretta resta
un concorrente distinto. Se mancano coppie sufficienti, il risultato resta
indisponibile e il conteggio è esplicito. Non si inventano intervalli.

L'anteprima conta coppie eleggibili, ma non ha calcolato né calibrato previsioni.
All'origine del primo test UTC sono disponibili 23 coppie solari e 16 eoliche
con le componenti sommate; la loro numerosità resta limitata per le code.

## Valutazione e separazione temporale

- Sviluppo: novembre 2021–ottobre 2024; test finale: novembre 2024–ottobre 2026.
- Il contesto e l'emissione proposti lasciano 11 origini di sviluppo con la
  storia richiesta: dicembre 2023–ottobre 2024. Non sono 36 prove complete.
- Test: fino a 24 origini, con 23 target solari completi e 24 eolici nell'ipotesi UTC/somma.
- MAE e RMSE dei totali in MWh; pinball sui livelli comuni 0,05/0,10/0,50/0,90/0,95;
  copertura e ampiezza degli intervalli centrali 80% e 90%. Tutti i 21 quantili
  nativi Timestral vanno comunque conservati.
- Stesse origini e stessi casi validi nei confronti accoppiati; riportare anche
  copertura dei dati, fallimenti e quanti casi perde ciascun metodo.
- Le osservazioni passate del test possono entrare nei contesti e negli errori
  rolling successivi solo dopo il cutoff previsto dalla regola fissa.
  Nessuna nuova scelta di metodo o iperparametro dopo l'esame dei risultati finali.
- Non dichiarare differenze piccole come certe: pochi mesi, correlazione temporale
  e cambi di capacità limitano soprattutto la valutazione degli intervalli.

Il test è separato dalle scelte del progetto, ma i dati sono anteriori al rilascio
del modello: dalle informazioni consultate non si certifica l'assenza di
sovrapposizioni con il pretraining. Una futura valutazione prospettica con pesi
fissi sarà distinta da questo confronto storico.

## Verifiche svolte e stato

Verificati sinteticamente: trasformazione positiva dei quantili, cutoff che
esclude il mese ancora in corso, contesto insufficiente non inventato, somma
eolica che conserva i NaN, hash degli input e anteprima non eseguibile.
Sono stati letti i config locali e controllata la presenza dei pesi, senza inferenza.

Il protocollo è congelato con snapshot, SHA-256 delle impostazioni e hash del
manifest dei dati preparati. Le modifiche future richiederanno una nuova versione
esplicita; non si cambieranno le impostazioni dopo aver visto i risultati finali.
Lo Step 10 è concluso. Lo Step 11 è stato poi autorizzato ed eseguito senza
modificare questo protocollo: [risultati e limiti](monthly_experiment.md).
L'autorizzazione separata è in monthly_execution; lo snapshot resta invariato.

Fonti primarie verificate il 7 novembre 2026:

- [API ufficiale Timestral](https://github.com/mistralai/timestral).
- [Scheda Timestral-28M](https://huggingface.co/mistralai/Timestral-28M).
- [Licenza corrente dei pesi](https://huggingface.co/mistralai/Timestral-28M/blob/main/LICENSE);
  codice Apache 2.0, pesi Modified MIT con clausola di fatturato già riportata
  nel [README](../README.md) con link alle revisioni scelte. I link delle licenze
  alle revisioni fissate non sono stati nuovamente recuperabili dal browser
  automatico in questo passaggio; nello Step 11 sono stati invece verificati
  direttamente via HTTP200 e conservati localmente in docs/licenses/.
- [Intervalli e aggregati, principi di valutazione](https://otexts.com/fpp3/practical.html).
