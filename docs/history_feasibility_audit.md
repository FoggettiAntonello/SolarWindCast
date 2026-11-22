# Audit dello storico lungo e dell'offshore — 10 novembre 2026

[Presentazione HTML](../reports/history_feasibility_20261110/presentazione.html)
e [audit JSON con provenienza](../reports/history_feasibility_20261110/audit.json).

L'utente ha autorizzato di proseguire con la verifica di disponibilità e coerenza
prima di ulteriori acquisizioni. Sono state fatte soltanto tre richieste
giornaliere, non un download di 8–10 anni. Nessuna inferenza, modifica dei dati,
calibrazione nuova o aggiornamento dei pesi.

## Disponibilità osservata: tre campioni, non copertura continua

| Campione UTC | Solare | Eolico terra | Eolico mare |
|---|---|---|---|
| 1 novembre 2016 | 24/24 ore valide | 24/24 | Componente assente |
| 1 novembre 2018 | 24/24 | 24/24 | Componente assente |
| 1 gennaio 2021 | 24/24 | 24/24 | Componente assente |

Dominio restituito `10Y1001A1001A788`, risoluzione PT60M, decodifica A03 con
adattatore già collaudato. XML e metadati immutabili in
[history_audit_20261110](../data/raw/entsoe/history_audit_20261110/), con SHA-256.
Una componente assente non viene interpretata come zero. Una giornata disponibile
non dimostra disponibilità o assenza di anomalie nell'intero anno.

## Vincolo territoriale verificato

La [tabella 2 di ARERA 297/2020/R/eel, pp.5–6](https://www.arera.it/fileadmin/allegati/docs/20/297-20.pdf)
confronta le configurazioni fino al 31 dicembre 2020 e dal 1 gennaio 2021:
la zona Sud precedente includeva Calabria oltre a Molise, Puglia e Basilicata;
la configurazione successiva separa Calabria. Anche Umbria cambia zona, mentre
i poli di produzione sono stati oggetto di una revisione pluriennale.
Il [GME, avviso del 27 ottobre 2020](https://www.mercatoelettrico.org/it-it/Home/MediaGME/ArchivioNews?id=2431)
conferma l'efficacia della nuova configurazione dal giorno di flusso 1 gennaio 2021.

Conferme e dettagli:

- [Terna, riorganizzazione del 2021](https://lightbox.terna.it/it/insight/riorganizzazione-zone-mercato-elettrico).
- [GME, elenco zone del 18 ottobre 2023](https://gme.mercatoelettrico.org/portals/0/Documents/it-IT/20231018_ME_Zone.pdf):
  Sud comprende Molise, Puglia e Basilicata; non coincide con la sola Puglia
  e non è l'intero Mezzogiorno amministrativo.

Gli XML restituiscono il medesimo EIC, ma non certificano una rimappatura
retroattiva a territorio costante. La differenza storica è documentata;
la geografia esatta delle risposte storiche e le eventuali ricostruzioni del
fornitore richiedono verifica. Non si concatenano automaticamente 2016/2018
e 2021–2026. Una ricostruzione richiede serie compatibili per territorio,
grandezza netta/lorda, componenti, poli, frequenza e revisioni. Non basta
sottrarre una serie Calabria senza provarne la compatibilità.

## Offshore: copertura dei dati e date tecniche non coincidono

Nei Parquet già verificati:

- Primo valore offshore disponibile: **26 maggio 2022, 22:00 UTC**, pari a zero.
- Primo valore positivo: **5 giugno 2022, 10:00 UTC**.
- Ore mancanti offshore precedenti: **4.966**; sette mesi incompleti,
  novembre 2021–maggio 2022. Sono 53 mesi completi su 60.
- Solare: 59 mesi completi, una sola ora mancante il 2 aprile 2026 alle05 UTC.
  Eolico a terra: tutti i 60 mesi completi.

Questi sono confini della copertura locale, non certificati di connessione o
prima produzione dell'impianto. Due fonti primarie offrono elementi utili:

- [Renexia, 5 dicembre 2022](https://renexia.it/renexia-beleolico-e-jonian-dolphin-conservation-insieme-per-leolico-offshore/)
  descrive il primo parco offshore e colloca la produzione nell'estate 2022.
- [IEA Wind TCP Italy Report 2022, autori CNR/RSE](https://usercontent.one/wp/iea-wind.org/wp-content/uploads/2023/10/Italy_2022.pdf)
  identifica la prima capacità offshore nel 2022 e indica avvio il 21 aprile 2022.

Questi elementi sostengono la necessità di distinguere assenza fisica di
impianti e buchi di pubblicazione. Non forniscono però un'unica soglia oraria
concordante che autorizzi il riempimento globale fino al26 maggio o5 giugno.
La data di inaugurazione, quella di connessione, la prima immissione e l'inizio
della pubblicazione possono essere diverse. Nessun NaN è stato sostituito.

Un eventuale zero strutturale dovrà essere una regola esplicita e approvata,
limitata ai periodi con assenza fisica documentata, con provenienza e flag
di dato derivato. Gli originali dovranno restare intatti. Le fonti retrospettive
non provano che la medesima informazione fosse pubblicata a ogni cutoff storico.

## Opzioni consigliate dopo l'audit

1. **Definire la politica offshore** acquisendo evidenza tecnica sufficiente
   per i periodi senza capacità e per la transizione del 2022. Senza questa
   distinzione, lo storico del totale eolico resta limitato dai NaN della somma.
2. **Valutare un lotto mirato gennaio–ottobre 2021:** dieci mesi aggiuntivi
   nella configurazione zonale successiva al cambiamento, portando il calendario
   complessivo da60 a70 mesi. La completezza di quel lotto non è stata accertata;
   il campione non è il download completo. Potrebbe aiutare soprattutto solare
   e carico, ma non risolve da solo l'offshore del totale eolico.
3. **Per 8–10 anni a territorio costante**, verificare una ricostruzione con
   fonti regionali/impiantistiche o una serie ufficialmente armonizzata.
   I dati più vecchi esistono nei campioni, ma la ricostruzione è un lavoro
   metodologico aggiuntivo, non un semplice ampliamento del periodo API.

Capacità installata pubblicata al cutoff e archivi meteo mensili restano
verifiche successive. Nessuna procedura di download completo è stata autorizzata
o avviata. I parametri operativi e il protocollo congelato restano invariati.
Non è garantito che una delle opzioni migliori le prestazioni del modello.

## Verifiche e limiti

42 test dei parser ENTSO-E superati, senza modifiche al loro codice. Controllati
gli hash dei tre XML e dei Parquet originali; report con manifest dedicato.
La disponibilità qui provata riguarda produzione solare/eolica nei tre giorni,
non carico storico o covariate meteorologiche. Nessun nuovo modulo scientifico
introdotto: usati acquisitore e parser esistenti. Nessun token mostrato o
registrato nel rapporto, nessun dato originale sovrascritto, Git disattivato.

Nota sulle fonti: la vecchia pagina italiana del Porto di Taranto non era
accessibile direttamente; le conclusioni sullo stato offshore si appoggiano
alle due fonti primarie sopra effettivamente consultate, senza inventare una
data tecnica certa. Per le zone si usa la tabella territoriale ARERA, non
un'interpretazione visiva non verificata della mappa.
