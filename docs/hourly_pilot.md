# Pilota 24 ore — 14 novembre 2026

[Report HTML](../reports/hourly_pilot_20261114/presentazione.html).
L'utente ha autorizzato un test su orizzonte breve. Scelte del pilota salvate
prima dell'inferenza nel YAML e nello snapshot: 5M solo target, contesto672ore,
orizzonte24ore, ritardo assunto24ore, CPU un thread, soli pesi locali.
Si decodificano48ore per coprire il ritardo e si valutano le ultime24.
Il ritardo è un'ipotesi prudenziale, non una disponibilità storica certificata.

Origini fissate al15di ogni mese alle00UTC, novembre2024–ottobre2026:
24giorni per target, non campionamento esaustivo. Zona Sud, solare e somma
stretta eolico terra+mare. Nessuna nuova acquisizione, meteo o training.
La prova è distinta dall'obiettivo mensile, che non è sostituito automaticamente.

## Risultati

47 inferenze effettive su massimo48. Escluso solare15aprile2026, perché il
contesto contiene l'ora mancante nota; escluse le medesime origini per tutte
le baseline. 23giorni/552ore solari e24giorni/576ore eoliche.

| Target | MAE migliore baseline MW | MAE5M MW | Delta MAE | Delta pinball |
| --- | ---: | ---: | ---: | ---: |
| Solare | 118,51 | 112,16 | -5,36% | +20,94% |
| Eolico terra+mare | 912,47 | 841,95 | -7,73% | +34,06% |

La migliore baseline descrittiva in entrambi i casi è la distribuzione della
stessa ora sui28giorni passati: mediana come punto, quantili empirici come
intervalli. Non è una baseline calibrata sugli errori. Altri confronti:
persistenza dell'ultimo valore, stessa ora48ore prima (24ore prima non sarebbe
disponibile con il ritardo scelto), stessa ora settimana precedente.

Copertura80 Timestral: solare71,20%, eolico39,93%; copertura90:
solare79,89%, eolico53,30%. La baseline probabilistica ha rispettivamente
84,60%/90,40% sul solare e67,36%/78,99% sull'eolico. Anche la baseline
eolica è sottocoperta. Timestral ha bande molto più strette: il miglioramento
puntuale non dimostra affidabilità probabilistica. MAE/RMSE/pinball in MW
non si confrontano direttamente con quelli del totale mensile in MWh.
Non si sommano i quantili orari per formare intervalli sull'energia giornaliera.

## Verifica e limiti

Moduli esistenti per caricamento verificato dei pesi e previsione con ritardo;
nuovo modulo con CLI, docstring e type hint, test sintetici di cutoff e metriche.
Metriche ricalcolate indipendentemente dai forecast salvati, medesime origini
per tutti i modelli. Source manifest verificato; versione e hash pesi nel report.

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.hourly_pilot --config configs/project.yaml
```

Il comando rifiuta l'output esistente ed è disabilitato dopo la conclusione.
Non rieseguirlo per cercare un esito favorevole. Nessun clipping dei negativi.
Dati revisionati, mesi già osservati, ore correlate, poche giornate: esplorativo.
I risultati giustificano considerare una verifica più estesa dell'orizzonte
orario, non una promozione automatica o la promessa di superiorità sul mensile.
Prossima eventuale fase da concordare: protocollo orario con molte più origini
prefissate e verifica dell'incertezza, senza aggiungere contemporaneamente
modelli, meteo e nuovi iperparametri.
