# Ultimo confronto eolico — esito del 14 novembre 2026

[Resoconto HTML completo](../reports/final_wind_results_20261114/presentazione.html)
e [risultati JSON](../reports/final_wind_results_20261114/results.json).
[Protocollo approvato](final_wind_protocol.md).

## Decisione

**Criteri non superati: il candidato 28M/calendario/12 calibrato non viene
promosso e questa iterazione di modifiche si ferma.** L'utente ha approvato
protocollo e budget con «procedi». Nessuna soglia o impostazione scientifica
è stata cambiata dopo l'esito. Il risultato negativo resta visibile.

Sono state eseguite esattamente 24 nuove inferenze locali 28M, senza training
o download, e riusate 192 previsioni dei quattro modelli precedenti e delle
quattro baseline. CPU un thread, medesimi dati e revisioni congelati. API
ricontrollata su [GitHub ufficiale](https://github.com/mistralai/timestral)
e [scheda 28M](https://huggingface.co/mistralai/Timestral-28M) prima di eseguire.
Versione, revisione del codice e SHA-256 dei pesi sono nel risultato.

## Metriche su 24 mesi comuni, novembre 2024–ottobre 2026

| Metrica | 12 mesi non calibrato | 12 mesi calibrato | Riferimento 24 mesi |
| --- | ---: | ---: | ---: |
| MAE MWh | 225.871,72 | 225.871,72 | 189.628,62 |
| RMSE MWh | 267.767,12 | 267.767,12 | 228.967,65 |
| Pinball MWh | 55.849,66 | 55.398,49 | 44.520,27 |
| Copertura80 | 21/24 | 21/24 | 19/24 |
| Ampiezza80 MWh | 759.420,95 | 710.369,92 | 550.598,88 |
| Copertura90 | 22/24 | 21/24 | 21/24 |
| Ampiezza90 MWh | 1.100.984,66 | 1.030.130,05 | 747.115,38 |

La calibrazione migliora la pinball dello stesso candidato dello 0,81%,
restringe le bande di circa 6,4%, lascia MAE/RMSE invariati e perde una
osservazione nella copertura90. Non è un miglioramento uniforme.

Contro il riferimento a 24 mesi: MAE **+19,11%**, RMSE **+16,95%**, pinball
**+24,43%**, ampiezze80 **+29,02%** e90 **+37,88%**. Solo **7 vittorie mensili
su 24**, contro le 15 richieste. La migliore baseline puntuale su questo
campione, media recente, ha MAE 199.707,77 MWh: candidato peggiore del **13,10%**.
La baseline probabilistica rolling ha invece pinball peggiore del candidato;
questo criterio passa, ma non basta a promuoverlo.

La variante 5M/calendario/24 già esistente mantiene il MAE descrittivo più
basso nel campione (181.868,21 MWh). Non diventa automaticamente una scelta
prima del test e non viene promossa retroattivamente in questo esperimento.

## Controlli e riproduzione

Nuovo modulo con CLI e test sintetici: `solarwindcast.final_wind_experiment`.
Il comando eseguito è:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.final_wind_experiment --config configs/project.yaml
```

Ora l'esecuzione è disabilitata nel YAML; il risultato esistente non viene
sovrascritto. Il comando non va ripetuto per cercare un esito diverso.
Snapshot prima delle inferenze, ogni forecast grezzo, previsioni combinate,
traccia del calibratore e manifesto sono nella cartella risultati.

I fit usano soltanto etichette entro il cutoff: novembre 2024 usa al massimo
settembre 2024. Gli errori passati disponibili vanno da 15 a 24. Quantili
ordinati e mediana invariata; fasi sviluppo/test mantenute distinte.
Verificati indipendentemente dai forecast: MAE, RMSE, pinball sui cinque
quantili di confronto, coperture e ampiezze di tutti i dieci modelli,
cutoff, contatore di 24 chiamate e integrità dello snapshot.

Controllo locale completo: **354 test passati, uno smoke facoltativo escluso**,
dipendenze coerenti e Ruff pulito. L'HTML contiene confronti prima/dopo con
delta assoluti e percentuali, errori per mese, tre grafici di previsione,
tutti i criteri superati/falliti e traccia dei fit. Grafici in GWh,
tabelle in MWh, conversione esplicitata; nessun dato scientifico alterato
durante le sole revisioni di presentazione.

## Limiti e chiusura

Questo è il vecchio test già osservato: confronto esplorativo, non conferma
indipendente o operativa. Le osservazioni sono revisionate e non si ricostruisce
la loro disponibilità originaria. Nessun dato mancante è stato inventato;
su questo target e periodo tutti i 24 mesi sono valutabili.

Non adottare il candidato ridotto calibrato come miglioramento del riferimento.
Conservare il confronto perso come evidenza dell'instabilità del vantaggio
osservato su pochi mesi di sviluppo. Il prossimo passo è concordare una
versione finale con affermazioni proporzionate ai risultati, non avviare altre
taglie, finestre o correzioni automaticamente. La preparazione del portfolio
resta subordinata al confronto con l'utente su questi risultati.
