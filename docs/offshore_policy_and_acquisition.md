# Offshore e piano dello storico esteso — proposta dell'11 novembre 2026

Stato: audit e piano conclusi; applicazione degli zeri, download e nuovo target
ancora da approvare. [Presentazione](../reports/offshore_policy_20261111/presentazione.html)
e [piano delle singole richieste](../reports/offshore_policy_20261111/acquisition_plan.json).

## Evidenze verificate e inferenze

[Renexia, 1 febbraio 2022](https://renexia.it/parco-eolico-ecco-la-prima-turbina/)
descrive l'avvio del posizionamento della prima turbina del primo parco offshore
italiano. Il [rapporto IEA Wind TCP 2022, autori CNR/RSE](https://usercontent.one/wp/iea-wind.org/wp-content/uploads/2023/10/Italy_2022.pdf)
colloca la prima capacità offshore nazionale, 30 MW a Taranto, nel 2022 e indica
produzione dal 21 aprile. La notizia dell'operatore e il rapporto sostengono
l'assenza di produzione offshore commerciale nel 2019–2021. Proponiamo il
limite prudente del 1 gennaio 2022 UTC, senza dedurre una soglia oraria dalla
cerimonia di inaugurazione.

Il [rapporto IEA Wind TCP 2025](https://iea-wind.org/annual-report-2025-italy/)
indica capacità offshore nazionale invariata a 30 MW dal 2022. Insieme alla
localizzazione a Taranto, questo sostiene **per inferenza** l'assenza di parchi
commerciali in Calabria nel 2022–2025. Non è una certificazione oraria del
dominio ENTSO-E, né una verifica esaustiva di impianti sperimentali o revisioni
della classificazione. Per il 2026 non estendiamo automaticamente l'inferenza.

Le fonti sono retrospettive: la loro consultazione oggi non prova che tutte
queste informazioni fossero disponibili ai cutoff del backtest storico.
La ricostruzione va dichiarata come hindcast su dati revisionati, non come
ricostruzione perfetta delle informazioni operative di allora.

I documenti del Porto di Taranto 2026 sono emersi nella ricerca con indicazione
di un unico parco, ma le aperture dirette hanno restituito 404. Non vengono
usati per certificare il 2026. Richieste di connessione e autorizzazioni non
equivalgono a impianti produttivi.

## Politica candidata, non applicata

| Dominio/periodo | Proposta | Limite |
| --- | --- | --- |
| Aree attive della macroarea nel 2019–2021 | Zero strutturale solo dove B18 manca | Evidenza nazionale; flag derivato e fonte obbligatori |
| Sud dal 1 gennaio 2022 | Conservare B18 osservato, lasciare NaN nei buchi | Nessuno zero fino al primo dato o positivo |
| Calabria nel 2022–2025 | Zero strutturale candidato dove B18 manca | Inferenza da validare sul dominio prima dell'applicazione |
| Calabria nel 2026 | Lasciare NaN | Serve riscontro tecnico aggiornato |

Non sovrascrivere originali né valori osservati, nemmeno se zero o negativi.
Qualsiasi valore B18 positivo dentro un intervallo candidato a capacità nulla
blocca la regola e richiede un'indagine; non si cancella il dato per farlo
coincidere con la fonte. Il derivato conserverà valore originale, valore
ricostruito, flag `structural_zero`, dominio, periodo di validità, fonte e
data di consultazione. Non riempire altri target o intervalli esterni.

Restano separate due viste: osservazioni strette e ricostruzione documentata.
Confrontare copertura e risultati su finestre comuni; non attribuire alla
calibrazione un miglioramento prodotto solo dal cambiamento dei mesi valutati.
La politica non elimina i buchi di avvio Sud nel 2022 né quelli Calabria 2026.

## Piano concreto di acquisizione

Periodo proposto: gennaio 2019–ottobre 2026, **94 mesi**, cioè 7 anni e 10 mesi.
Sono 34 mesi di calendario in più rispetto ai 60 già presenti, ma cambia anche
la geografia: macroarea Sud + Calabria, distinta dal vecchio target Sud.
La completezza e l'utilità predittiva non sono ancora dimostrate.

Regimi: Sud + Rossano fino al 31 dicembre 2020 alle 23 UTC escluso;
Sud + Calabria dopo. Dicembre 2020 ha un segmento Calabria di un'ora.
Il piano JSON enumera gli intervalli esatti e distingue riusi locali verificati
tramite SHA-256 e richieste potenziali. Nessun token viene letto dal pianificatore.

Proposta in lotti, con arresto fra i lotti:

1. **Pilota gennaio 2021:** Sud e Calabria, B16/B19, massimo quattro richieste
   senza ritentativi automatici. Controllare dominio, unità MW, segni, revisioni,
   risoluzione e tutte le ore UTC attese. Verificare la compatibilità con il
   prototipo; una risposta presente non prova che il mese sia completo.
2. **Estensione solare/onshore:** completare il piano solo dopo il controllo
   del pilota. Nessuna richiesta concorrente: scaricare in
   sequenza, salvare ogni risposta, riprendere dai riusi validi e fermarsi sugli
   errori senza cicli di tentativi. Budget: 378 richieste lorde, 72 riusi esatti
   con hash verificato, massimo 306 nuove. Il tetto B18 separato è 189 lorde,
   30 riusi e massimo 159 nuove. Riusi parziali possono ridurre questi tetti;
   sono esclusi dai conteggi conservativi.
3. **Offshore:** budget separato e subordinato alla politica approvata; non
   spendere richieste indiscriminate per sostituire con zero risposte assenti.
   Il piano include un tetto conservativo B18 per tutti i segmenti, riducibile
   dopo decisione della politica e controllo della cache.

Richieste mensili parziali, paginazione o altri segmenti richiesti dal fornitore
non sono automaticamente autorizzati oltre il tetto. Durata e dimensione dei
download non sono stimate senza misurarle sul pilota.

## Valutazione successiva

Nessun nuovo training o backtest in questo passaggio. Prima congelare dataset,
qualità, nuova geografia e piano di valutazione. Mantenere baseline e 5M/28M
con impostazioni comparabili; non aggiungere griglie mentre si osservano gli
esiti. Le finestre storiche già esaminate saranno esplorative. Serve anche una
verifica futura registrata prima degli esiti per una prova più credibile.
Più dati possono aiutare, ma 94 totali mensili non equivalgono a migliaia di
esempi indipendenti per il fine tuning.

Nessun modulo scientifico modificato: verifica del piano con controlli di
intervalli, conteggi e hash, più controllo HTML. I 348 test superati nel passo
precedente non sono stati rieseguiti per questa sola proposta documentale.
