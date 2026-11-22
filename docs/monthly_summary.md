# Step 10 — totali mensili osservati

Il modulo `monthly_summary.py` riassume le osservazioni preparate. Non esegue
previsioni, calibrazione o confronto tra modelli.

La configurazione `monthly_inspection` seleziona i dati preparati e il fuso
del calendario. L'ispezione usa UTC, mentre i confini del futuro obiettivo
previsionale restano da concordare. Il componente gestisce anche Europe/Rome:
sono verificati mesi bisestili e cambi d'ora con test sintetici.

## Regola

Per ogni mese si costruisce la griglia attesa tra inizio incluso e fine esclusa,
secondo il calendario scelto. Il totale è dichiarato solo se tutti gli intervalli
sono rappresentati e validi. Potenza media in MW moltiplicata per la durata in
ore dà energia in MWh. Un valore mancante rende il mese incompleto; non si
sommano soltanto i valori disponibili e non si sostituiscono con zero.

I valori negativi, se presenti, sono segnalati e conservati. La completezza
non dimostra da sola l'assenza di anomalie fisiche o revisioni.

Solare, eolico a terra e in mare restano separati. Una somma delle componenti
eoliche richiederà la loro presenza e una scelta esplicita del target.

## Comando riproducibile

Dalla radice, in PowerShell, con una cartella nuova:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.monthly_summary `
  --config configs/project.yaml --output reports/nuovo_audit_mensile
```

Prima della lettura vengono verificati tutti gli hash dei dati preparati.
La nuova directory contiene HTML con SVG incorporati, `monthly_energy.json`
e un manifest SHA-256. Nessun accesso alla rete o lettura di segreti.

Il periodo di test indicato proviene dalla proposta nel YAML. Il report conta
i mesi osservati completi inclusi in quel periodo: **non** misura accuratezza
o affidabilità di previsioni mai eseguite. Ventiquattro mesi di test rimangono
un campione limitato per le coperture degli intervalli.

Per gli intervalli del totale mensile vanno trattate le dipendenze temporali:
non si sommano quantili orari. Metodo, contesto, emissione e disponibilità dei
dati restano allo sviluppo del protocollo mensile.

Riferimenti consultati: [pandas resampling](https://pandas.pydata.org/docs/reference/resampling.html)
e [contratto temporale del progetto](dataset.md).
