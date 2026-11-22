# Estensione Sud + Calabria, febbraio–ottobre 2021

[Presentazione HTML](../reports/macroarea_2021_extension_20261111/presentazione.html)
e [audit](../reports/macroarea_2021_extension_20261111/audit.json).

L'utente ha autorizzato il lotto dopo il pilota di gennaio: 36 richieste
mensili, due aree (Sud e Calabria), due componenti (B16 solare e B19 eolico
a terra), nove mesi. Tutte riuscite, nessun retry. Configurazione nel blocco
`macroarea_2021_extension` del YAML. Nessuna richiesta B18, applicazione di
zeri strutturali o nuova inferenza Timestral.

## Esito verificato

- Tutte le 36 serie nuove sono complete sulla griglia oraria UTC attesa.
- Zero valori mancanti o negativi; nessuna segnalazione del parser.
- Risoluzione nativa oraria, domini EIC e unità MW controllati.
- Gennaio riusato dal pilota, senza nuovo download.
- Gennaio–ottobre: 7.296 ore complete per componente aggregata e 20 totali
  mensili completi (dieci solari e dieci onshore).
- Somme orarie strette delle aree; totali mensili ricontrollati sui file
  orari salvati, griglia continua senza duplicati, hash degli originali verificati.
- 24 test sintetici esistenti dei parser e dell'aggregazione superati.

Il periodo complessivo è `[2021-01-01T00:00:00Z, 2021-11-01T00:00:00Z)`.
Si usano mesi UTC: le transizioni dell'ora legale locale non aggiungono né
tolgono ore dalla griglia UTC. Le curve A03 sono decodificate come da fonte,
senza interpolare veri buchi. I MWh sono la somma delle medie orarie MW
moltiplicate per un'ora, non la somma di quantili previsivi.

Originali in [data/raw/entsoe/macroarea_2021_extension_20261111/](../data/raw/entsoe/macroarea_2021_extension_20261111/).
Il report contiene diagnostica per ogni richiesta, dati orari per area e
componente, aggregati mensili e due serie gennaio–ottobre; il manifesto
registra gli SHA-256. Non sono stati sovrascritti dataset o report precedenti.
La pagina HTML mostra totali mensili e grafici con scale indipendenti.

## Limiti e prossimo lotto

Sono osservazioni revisionate scaricate oggi, non ricostruzioni delle versioni
disponibili ai cutoff storici. L'eolico è solo onshore: non sostituisce il
target approvato terra + mare. La macroarea è distinta dalla zona Sud ufficiale.
Nessuna prestazione predittiva migliorata o dimostrata da questa acquisizione.
La completezza dei dieci mesi non certifica il resto dello storico.

Consigliato, ma non autorizzato: Calabria novembre 2021–ottobre 2026,
B16/B19, massimo 120 richieste mensili senza retry, riducibili dopo eventuali
riusi verificati. Unendola al Sud già disponibile si potrebbe costruire una
macroarea di 70 mesi, con verifica della copertura e dei mancanti effettivi
(il solare Sud ha già un buco noto nell'aprile 2026). Il pre-2021 e l'offshore
restano separati. Nessun nuovo protocollo o cambio operativo del target è
autorizzato automaticamente.
