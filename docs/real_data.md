# Step 10 — analisi locale dei dati reali

[Apri la presentazione HTML dei totali mensili osservati](../reports/step10_monthly_five_year_20261107/presentazione.html).
Contiene osservazioni ENTSO-E della zona Sud, non previsioni di Timestral.
Non sono stati riutilizzati i risultati del vecchio prototipo.

## Copertura verificata

Originali aggiunti: `data/raw/entsoe/history_20211101_20261101/`;
i precedenti 24 mesi restano in `data/raw/entsoe/history_20241101_20261101/` e
sono riutilizzati senza duplicare gli XML. Periodo UTC: dal 1 novembre 2021
alle 00:00 al 1 novembre 2026 alle 00:00 escluso, 60 mesi e 1826 giorni.
Sono stati aggiunti 36 mesi (108 richieste) e nove richieste campione.
I dati sono orari fino al 31 dicembre 2024 alle 00:00 UTC, poi a 15 minuti.
Sono 61 segmenti a frequenza nativa costante, non dati ricampionati.

| Componente | Validi / attesi | Mancanti | Negativi | Energia completa MWh |
|---|---:|---:|---:|---:|
| Solare | 92063 / 92064 | 1 | 0 | non dichiarata |
| Eolico a terra | 92064 / 92064 | 0 | 0 | 47140639,00 |
| Eolico in mare | 87098 / 92064 | 4966 | 0 | non dichiarata |

Il dato solare del 2 aprile 2026 alle 05:00 UTC resta NaN.
L'offshore è assente nelle risposte da novembre 2021 ad aprile 2022 e ha un
prefisso mancante a maggio 2022. I sette mesi restano incompleti, non zero.
La base oraria ha 43824 ore per serie: 43823 valide solari, 43824 onshore,
38858 offshore. Il report mensile dichiara 59, 60 e 53 mesi completi rispettivamente.
Nei due anni di test proposti sono disponibili 23 mesi solari e 24 per entrambe
le componenti eoliche. Sono conteggi osservati, non risultati dei modelli.
L'energia è la somma delle potenze medie in MW per la rispettiva durata nativa.
Con mancanti il totale del periodo non viene dichiarato completo.
Assenza di buchi e negativi non certifica assenza di anomalie fisiche.

## Lettura dei blocchi A03

I documenti originali usano curve A03: ciascun punto indica l'inizio di un
blocco a valore costante, valido fino al punto successivo o alla fine del Period.
Le posizioni non ripetute nel blocco non sono buchi: si decodifica il formato
della fonte, senza interpolare. Quantità assenti restano NaN, prefissi assenti
restano mancanti e nessun valore viene propagato tra Period separati.

Il parser condiviso richiede l'opzione esplicita `allow_a03=True`.
Il percorso API ordinario resta stretto su A01; l'analisi locale abilita A03
tramite `inspection.step10.decode_a03` nella configurazione YAML.
Hash errati, posizioni fuori ordine e documenti sovrapposti bloccano l'analisi.
Lo storico abilita anche la selezione esplicita dei Period a frequenza costante.
Una serie di consumo degli impianti nel documento solare di aprile 2026 viene
esclusa esplicitamente e registrata: non è sottratta alla produzione.

## Riproduzione

Dalla radice, in PowerShell, usando una nuova cartella di destinazione:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.history_acquisition `
  --config configs/project.yaml --phase history --output reports/nuova_analisi_reale
```

Con lo storico completo presente il comando riutilizza gli XML verificati,
senza nuove richieste. Se manca una risposta può acquisirla nel perimetro approvato.
Non esegue inferenze del modello. [Piano e limiti delle richieste](history_plan.md).
La configurazione unica resta [project.yaml](../configs/project.yaml).
I file originali e le cartelle di risultati già esistenti non vengono sovrascritti.
L'HTML incorpora grafici SVG e funziona offline; offre andamento per componente,
copertura per periodo, provenienza e limiti. I grafici mostrano medie giornaliere
solo per giorni completi; non fissano la frequenza degli esperimenti.
I JSON affiancati riportano serie native e analisi; il manifest contiene
gli SHA-256. I metadati pubblicati escludono le richieste e i loro parametri.

## Decisioni ancora aperte

[Piano dello storico e del test](history_plan.md), 6 novembre 2026:
cinque anni approvati e acquisiti, tre per sviluppo e due per test separato.

Cinque anni consentono una valutazione stagionale più ampia, ma la robustezza
va misurata: nessuna conclusione sulle prestazioni è ancora stata calcolata.
La griglia oraria è approvata e l'utente richiede ora il totale del prossimo
mese in MWh. Servono decisioni su contesto, finestre, componenti eoliche,
modelli, covariate e intervalli aggregati: [obiettivo mensile](monthly_objective.md).
I ritardi di pubblicazione e le revisioni disponibili all'origine non sono
ricostruiti: l'ora di acquisizione non prova la disponibilità nel passato.
Lo Step 10 resta in corso; lo Step 11 non è stato eseguito.

## Documentazione verificata il 5 novembre 2026

- [ENTSO-E: curve A01 e A03](https://transparencyplatform.zendesk.com/hc/en-us/articles/30262342482961-CurveType-A01-vs-CurveType-A03)
- [ENTSO-E: specifica delle curve, sezione 4.3 e intervalli mancanti](https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/cim_based/Introduction_of_different_Timeseries_possibilities__curvetypes__with_ENTSO-E_electronic_document_v1.4.pdf)
- [Python ElementTree](https://docs.python.org/3.12/library/xml.etree.elementtree.html)
- [pandas: statistiche descrittive](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.describe.html)
- [Matplotlib: salvataggio di figure SVG](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.savefig.html)
