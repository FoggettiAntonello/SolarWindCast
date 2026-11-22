# Macroarea Sud + Calabria: 70 mesi di calendario

[Presentazione HTML](../reports/macroarea_70months_20261111/presentazione.html),
[audit](../reports/macroarea_70months_20261111/audit.json) e
[dataset separato](../data/processed/macroarea_70months_20261111/).

## Acquisizione autorizzata e risultato

Con «procedi pure» l'utente ha approvato Calabria, novembre 2021–ottobre 2026,
solare B16 ed eolico a terra B19: 120 richieste mensili, tutte riuscite senza
retry automatici. Nessun riuso mensile esatto era disponibile per questo lotto;
non sono stati scaricati nuovamente Sud o i dieci mesi già acquisiti del 2021.
Il perimetro è nel blocco `calabria_five_year_extension` del YAML.

Tutte le 120 serie calabresi sono complete alla frequenza oraria richiesta:
zero buchi, valori negativi o segnalazioni diagnostiche rilevanti.
I domini restituiti, i documenti A75/A16 e l'unità MW sono verificati.
Le risoluzioni native sono 60 e 15 minuti; dicembre 2024 contiene un cambio
interno al mese, al 31 dicembre 00:00 UTC. Segmenti e diagnostica per ogni
richiesta sono conservati nel rapporto.

Combinando Calabria, Sud già verificato e macroarea gennaio–ottobre 2021:

| Componente della macroarea | Ore valide / attese | Mesi completi / calendario |
| --- | --- | --- |
| Solare | 51.119 / 51.120 | 69 / 70 |
| Eolico a terra | 51.120 / 51.120 | 70 / 70 |

Periodo `[2021-01-01T00:00:00Z, 2026-11-01T00:00:00Z)`.
L'unico buco è quello solare Sud già noto: **2 aprile 2026, 05:00 UTC**.
Il contributo Calabria è presente, ma il totale della macroarea resta NaN
in quell'ora. Aprile 2026 non ha un totale solare completo: il rapporto mostra
«Incompleto», non un'energia parziale spacciata per totale.

## Metodo e riproducibilità

Usati i componenti esistenti e testati: acquisizione XML immutabile, parser
rigoroso, segmentazione della risoluzione nativa, media di soli intervalli
completi e somma stretta delle aree. Le curve A03 vengono decodificate secondo
la fonte, senza interpolare buchi. La media oraria richiede tutti i quattro
quarti d'ora quando la risoluzione nativa è 15 minuti. Gli originali restano
in [raw Calabria](../data/raw/entsoe/calabria_five_year_20261111/).

Il dataset Parquet separato contiene il target orario in MW; il relativo
manifesto dichiara macroarea e sola componente onshore. I MWh mensili sono
la somma delle medie orarie MW moltiplicate per un'ora, solo su mesi completi.
Non sono quantili previsti né previsioni Timestral.

Verifiche indipendenti sui risultati salvati: hash dei 120 originali, hash
del Sud riutilizzato e dei primi dieci mesi, griglia UTC esatta, tutte le somme
Sud + Calabria anche in presenza di NaN, conteggi e MWh di ciascun mese.
39 test sintetici di parser, frequenze e aggregazione superati. Nessun nuovo
modulo scientifico introdotto. Il report HTML funziona offline e permette
di filtrare anno e componente; mesi incompleti distinti dai valori zero.

## Limiti e passo successivo

La macroarea è diversa dalla zona Sud ufficiale dei risultati precedenti,
che restano invariati. L'eolico è solo a terra: non sostituisce il target
approvato terra + mare. Nessun B18 richiesto o zero strutturale applicato.
Sono dati revisionati scaricati oggi: ritardi di pubblicazione e disponibilità
delle revisioni ai cutoff storici non sono ricostruiti.

Questo passaggio dimostra la copertura dei dati, non un miglioramento
predittivo. Nessun training, inferenza o selezione di modello è avvenuto.
Prima di altri download o backtest, concordare il protocollo della macroarea
e come gestire l'offshore, mantenendo il confronto su finestre comuni e
dichiarando esplorative quelle già esaminate. L'eventuale estensione al
2019–2020 resta separata e non autorizzata.
