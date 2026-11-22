# Pubblicazione del portfolio su Azure

Scelta approvata dall'utente il 21 novembre 2026: sito statico su **Azure
Static Web Apps, piano Free**, dopo il collaudo del progetto e i controlli
di pubblicazione. Nessuna risorsa Azure è stata ancora creata.

## Cosa sarà online

La [presentazione](portfolio/index.html) e le [metriche aggregate](portfolio/metrics.json)
mostrano risultati già calcolati. Python e Timestral continueranno a essere
eseguiti localmente; il sito non richiede GPU, server Python o database.

Il piano Free include HTTPS, 250 MB per ambiente e 100 GB/mese di traffico
per sottoscrizione. Non costituisce una promessa di gratuità di altri servizi:
non attivare Functions, macchine virtuali o piani a pagamento per questa pubblicazione.
Usare l'indirizzo fornito da Azure senza acquistare un dominio.

## Sequenza di rilascio

1. Completare installazione, test e revisione di licenze, segreti e contenuti.
2. Pubblicare il repository GitHub concordato e verificarne un clone pulito.
3. Preparare un pacchetto statico con il modulo `solarwindcast.publication`,
   verificando tutti i collegamenti. Non caricare l'intera cartella del progetto.
4. Creare una Static Web App con piano **Free**, nell'account dell'utente,
   e collegare il repository. Il workflow manuale predisposto usa il ramo main
   e prepara la cartella `build/site` prima di caricarla.
5. Conservare l'eventuale token di distribuzione nei secret di GitHub Actions,
   mai nel codice. Non incollarlo nella chat.
6. Verificare dall'indirizzo pubblico pagina, grafici, metriche e collegamenti;
   aggiungere il link al README solo dopo questa prova.

Repository GitHub pubblico verificato: FoggettiAntonello/SolarWindCast.
Account e sottoscrizione Azure restano da identificare.
L'autorizzazione alla pubblicazione non implica l'attivazione di servizi a pagamento.

## Fonti ufficiali verificate il 21 novembre 2026

- [Piani Static Web Apps](https://learn.microsoft.com/en-us/azure/static-web-apps/plans)
- [Quote e limiti](https://learn.microsoft.com/en-us/azure/static-web-apps/quotas)
- [Configurazione del sito](https://learn.microsoft.com/en-us/azure/static-web-apps/configuration)

Questo passaggio non produce nuove previsioni o metriche dei modelli.

[Comandi, controllo dei file e autenticazione](publication.md).
