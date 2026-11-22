# Dati

- `raw/`: originali già acquisiti, con parametri e rapporti conservati.
- `processed/`: dataset elaborati usati dagli esperimenti.
- `cache/`: risposte meteo dimostrative conservate con provenienza.

Le cartelle vuote `interim` e `synthetic` sono state rimosse nella pulizia finale;
gli output vengono creati quando necessari. Il vecchio campione elaborato del
prototipo, sostituito dai dataset verificati, è stato eliminato. Gli originali
non sono stati eliminati. Non aggiungere dati o segreti a Git senza verificare
esclusioni e licenze. Nuovi esperimenti restano soggetti ad autorizzazione.

Prima ispezione Step 10: acquisizione ENTSO-E `20261103T100207Z_64b0ec85`,
tre giorni UTC (31 ottobre–2 novembre 2026), frequenza nativa 15 minuti,
solare ed eolico onshore/offshore. Originali verificati tramite hash, senza
modificarli. [Presentazione e limiti](../docs/real_data.md).
La frequenza rilevata non approva i parametri degli esperimenti.

Acquisizione successiva approvata: `raw/entsoe/history_20241101_20261101/`,
24 mesi novembre 2024–ottobre 2026, con frequenza oraria e poi di 15 minuti
dal 31 dicembre 2024. Originali immutabili per richiesta, campioni separati,
metadati e hash; 1 intervallo solare mancante, eolico completo.
La presentazione iniziale e le pagine dei campioni sono sostituite dall'HTML
dei due anni; i loro dati sorgente restano conservati.

Estensione attiva: novembre 2021–ottobre 2026. I 36 mesi aggiunti sono in
`raw/entsoe/history_20211101_20261101/`; i precedenti 24 restano nella loro
cartella e sono riutilizzati, senza duplicazione o modifica degli XML.
Serie orarie in `processed/step10_five_year_hourly_20261107/`: 43.824 ore per
serie, 1 mancante solare e 4.966 offshore. L'assenza offshore nei primi mesi
non è stata trasformata in produzione zero. [Audit mensile](../docs/monthly_summary.md).
