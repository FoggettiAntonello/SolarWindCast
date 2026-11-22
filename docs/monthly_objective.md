# Obiettivo confermato: energia del prossimo mese

Chiarimento dell'utente, 7 novembre 2026: prevedere **il totale mensile**,
separatamente per solare ed eolico della zona Sud, con intervalli di incertezza.
La proposta precedente di 24 ore con sette giorni di contesto è superata.

## Cosa significa

Una previsione emessa prima del mese obiettivo deve stimare l'energia di
**tutto il mese di calendario successivo** usando soltanto informazioni
disponibili all'emissione. Non equivale a sommare previsioni giornaliere
aggiornate durante quel mese. Il risultato si esprime in MWh.

I mesi hanno durate diverse. Occorre concordare se il calendario sia UTC o
Europe/Rome; in quest'ultimo caso anche il cambio d'ora influisce sui confini.
I timestamp delle osservazioni restano UTC in entrambi i casi.

Le serie orarie MW già preparate restano valide. Per calcolare l'energia
osservata si sommano potenze medie moltiplicate per la durata in ore.
Un mese con dati mancanti non diventa completo usando una somma che ignora NaN.
Aprile 2026 solare resta incompleto; nessuna imputazione autorizzata.

## Storico esteso autorizzato

Lo storico iniziale di due anni conteneva solo 24 totali mensili. L'utente ha
quindi autorizzato cinque anni, **novembre 2021–ottobre 2026**: 60 mesi teorici,
con tre anni di sviluppo e due di test separato. La copertura effettiva va
verificata: una risposta assente della fonte non si trasforma in produzione zero.
Più origini sovrapposte sullo stesso mese non creano nuovi mesi indipendenti.
Anche 24 mesi di test impongono prudenza sulle coperture degli intervalli.

L'estensione di produzione è conclusa: 59 mesi solari completi, 60 onshore e
53 offshore. Gli ultimi due anni hanno 23 mesi solari completi e 24 per ciascuna
componente eolica. [Riepilogo osservato](../reports/step10_monthly_five_year_20261107/presentazione.html).
Nessuna previsione è stata eseguita. I dati meteo
non sono automaticamente coperti per tutti i cinque anni. Restano da controllare
variazioni di capacità installata, qualità e ritardi. Nessuna durata prefissata
garantisce da sola robustezza.

## Metodo da confrontare nel periodo di sviluppo

- Produrre previsioni a frequenza oraria o giornaliera per tutto il mese,
  poi ricavare il totale. Frequenza e contesto del modello da scegliere.
- Valutare un metodo diretto sul totale mensile, considerando che anche
  60 punti sono pochi per scegliere e verificare modelli complessi.
- Baseline mensili possibili: energia del mese precedente corretta per la
  durata, stesso mese dell'anno precedente, media giornaliera recente estesa
  ai giorni del mese obiettivo. Anche queste scelte vanno dichiarate prima del test.

Il totale di una previsione puntuale e l'intervallo del totale sono problemi
distinti. **Non si sommano i quantili marginali delle singole ore per ottenere
i quantili del mese.** Occorre trattare la dipendenza tra ore/giorni, ad esempio
con scenari congiunti o un metodo di calibrazione del totale valutato su mesi
precedenti. Non presentare un aggregato di mediane orarie come mediana mensile
senza una giustificazione. Nessun metodo è già stato collaudato sul caso reale.

I normali archivi meteo a breve termine non vanno considerati automaticamente
previsioni note per l'intero mese. La scelta di covariate e archivi compatibili
con il nuovo orizzonte richiede una verifica specifica.

## Stato

La definizione del risultato è confermata in
`planning.step10.evaluation_proposal`. Contesto, modello, confini del mese,
emissione e intervalli restano DA DECIDERE. Non sono state eseguite previsioni.
Lo Step 10 è concluso e lo Step 11 è stato autorizzato ed eseguito secondo il
protocollo congelato. [Risultati reali e limiti](monthly_experiment.md).

Riferimento metodologico consultato:
[valutazione temporale e intervalli di previsione](https://otexts.com/fpp3/toolbox.html).
