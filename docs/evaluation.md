# Baseline e metriche — Step 6

Lo step implementa confronti semplici e funzioni di valutazione, con prove
sintetiche. Non esegue un backtest, non usa dati reali e non dimostra prestazioni
di Timestral o degli altri modelli.

## Tre baseline configurabili

[baselines.py](../src/solarwindcast/baselines.py) legge il target dal formato comune.
Frequenza e identità (`solar`, `wind`, `load`, `residual_load`) provengono dal dataset.
Contesto, orizzonte, metodo e ritardo di pubblicazione sono espliciti.

| Metodo | Previsione | Mancanti e limiti |
|---|---|---|
| `persistence` | Ripete l'ultimo valore del contesto disponibile | Se quel valore è NaN, tutte le previsioni restano NaN; nessuna ricerca nascosta di un valore precedente |
| `seasonal_naive` | Ripete l'ultimo ciclo di lunghezza `seasonal_lag_steps` | Conserva le posizioni NaN; il ciclo non è automaticamente giornaliero |
| `historical_quantiles` | Mediana e quantili della distribuzione dei valori osservati nel contesto | Campioni NaN esclusi dal calcolo e contati; se i validi sono insufficienti restituisce NaN e stato esplicito |

La terza baseline ignora ordine temporale e covariate: è un riferimento
probabilistico semplice, non una stima sofisticata dell'incertezza. Ripete la
stessa distribuzione su tutto l'orizzonte. Non adatta la larghezza degli intervalli
al passo di previsione e **non garantisce calibrazione**. Le prime due baseline
restituiscono soltanto punti: non si inventano intervalli di ampiezza zero per
presentarle come modelli probabilistici.

Per i quantili storici occorrono livelli, metodo NumPy (`linear`, `inverted_cdf`
o `nearest`) e minimo di campioni validi espliciti. La previsione puntuale è il
quantile 0.5 stimato con lo stesso metodo; non serve che 0.5 sia tra le colonne
richieste. La selezione dei metodi degli esperimenti resta DA DECIDERE.

## Disponibilità del target e ciclo

Per un'osservazione che inizia a `t`, l'intervallo termina a `t + frequenza`.
Il contesto usa solo gli intervalli terminati e pubblicati secondo:

`t + frequenza + publication_delay <= origine`

Dal contesto disponibile si prendono gli ultimi `context_steps`, senza saltare
righe mancanti. I quantili storici dichiarano quanti campioni validi usano.
Se manca il numero di righe richiesto si rifiuta la previsione; non si estende
automaticamente il periodo per cercare altri dati.

La stagionalità è espressa in passi della griglia UTC. Se un ritardo di
pubblicazione allontana l'ultimo dato dall'origine, la ripetizione avanza della
fase corrispondente: non sposta il ciclo per farlo iniziare dall'ultimo dato.
Oltre una stagione si ripete lo stesso ciclo già osservato, senza usare valori
reali che nel frattempo si troverebbero nel periodo di test.

Il ritardo è una dichiarazione da verificare con le fonti. Le revisioni storiche
non vengono ricostruite. Lo Step 8 dovrà applicare una disponibilità coerente a
tutti i modelli, comprese le finestre di Timestral; questo step non certifica
ancora una simulazione operativa completa.

## Formato delle previsioni

`ForecastResult`, in [dataset.py](../src/solarwindcast/dataset.py), contiene:

- `point`: Series numerica con griglia UTC e nome `prediction` per le baseline;
- `quantiles`: DataFrame opzionale sulla stessa griglia, con probabilità numeriche
  ordinate e univoche come colonne;
- identità del target, frequenza e metadati di metodo, contesto e disponibilità.

NaN sono ammessi e conservati. Infiniti, quantili incrociati o timestamp
incompatibili sono rifiutati. Anche incroci separati da una colonna NaN vengono
rilevati; i valori non vengono ordinati o corretti automaticamente.
È un contratto riutilizzabile per il wrapper dello Step 7.

## Metriche con denominatori visibili

[evaluation.py](../src/solarwindcast/evaluation.py) richiede Series/DataFrame con
timestamp UTC esattamente allineati. Vettori posizionali, duplicati e infiniti
sono rifiutati. Le metriche assumono il target in MW del formato interno.

| Funzione | Risultato |
|---|---|
| `point_metrics` | MAE, RMSE e bias medio con segno previsione meno osservazione, in MW |
| `pinball_metrics` | Pinball loss per quantile e media non pesata sui livelli, in MW |
| `interval_metrics` | Copertura inclusiva, ampiezza media in MW e differenza dalla copertura nominale |
| `central_interval` | Estremi a code uguali estratti dai quantili disponibili, senza interpolazione |

MAE è la media degli errori assoluti; RMSE è la radice della media degli errori
quadratici. Per un quantile `q` ed errore `e = osservazione - previsione_q`, la
pinball loss è `max(q*e, (q-1)*e)`. Per esempio, a q=0.5 coincide con metà dell'errore
assoluto. La media sui quantili usa gli stessi casi per tutti i livelli, evitando
che un quantile con più mancanti venga valutato su righe diverse.

La copertura è la frazione di osservazioni fra limite inferiore e superiore,
estremi inclusi. Il livello nominale è richiesto esplicitamente, non è fissato
all'80%. La copertura va letta insieme all'ampiezza: intervalli larghi possono
coprire molto senza essere utili. Questo step non stima un intervallo di confidenza
per la copertura o la significatività del confronto.

Ogni funzione restituisce un `MetricReport` con punteggi, numero totale e usato,
timestamp esclusi e motivazioni. La politica dei mancanti è obbligatoria:

- `raise`: rifiuta i mancanti nei casi selezionati;
- `omit`: valuta solo i casi completi, riportando tutte le esclusioni. I dati
  originali restano NaN; non vengono riempiti.

Se nessun caso è valutabile, i punteggi sono NaN, non zero.
`common_valid_mask(actual, forecasts)` permette di costruire una maschera comune
fra più modelli, da passare alle metriche come `evaluation_mask`. Lo Step 8 dovrà
usarla per confronti sugli stessi casi, riportando anche quante previsioni ogni
modello non ha prodotto. Confrontare solo punteggi calcolati su casi diversi
potrebbe favorire un modello che manca le situazioni difficili.

Esempio sintetico verificato: osservazioni `[0, 10]` e previsioni `[2, 6]` danno
MAE 3 MW e RMSE √10 MW. Questi valori sono risultati di controllo del codice,
non prestazioni su produzione energetica reale.

## Configurazione e pulizia

`BaselineConfig.from_project_config(project, method)` legge `models.baselines`,
`forecast` e il ritardo del target in `data.publication_delay`. Per i metodi
puntuali non richiede quantili o parametri probabilistici ancora da decidere.
`EvaluationConfig.from_project_config(project)` legge la politica dei mancanti
e i livelli di quantili/intervalli. Gli intervalli centrali richiedono le colonne
dei due quantili necessari; non si approssimano livelli assenti.

Nel [YAML](../configs/project.yaml) sono stati aggiunti soltanto
`models.baselines.quantile_method`, `models.baselines.minimum_valid_samples`
ed `evaluation.missing_policy`, tutti DA DECIDERE. Non sono stati attivati metodi,
quantili, cicli o orizzonti degli esperimenti reali.

Rimosse le vecchie funzioni di baseline, le etichette fisse `coverage80` e
`uguale_a_ieri`, e il separatore del prototipo limitato a dati orari. Era usato
solo dai suoi due vecchi test, ora rimossi; le nuove prove verificano griglie,
contesti e mancata dipendenza da valori futuri. Il motore di backtest resta allo
Step 8. Nessun risultato scientifico archiviato o dato originale è stato eliminato.

## Verifica in PowerShell

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_baselines.py tests/test_evaluation.py tests/test_dataset.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m ruff check src tests --no-cache
```

I test confrontano esempi calcolati a mano e funzioni scikit-learn indipendenti,
verificano ritardi di pubblicazione e cicli, e modificano i target futuri per
dimostrare che le baseline non cambiano. Includono l'integrazione previsione e
valutazione sugli stessi timestamp. Fixture solo in memoria: nessun file fittizio
persistente, installazione, GPU, modello o token usato.

Documentazione ufficiale/primaria consultata il 4 novembre 2026:

- [MAE, scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.mean_absolute_error.html)
- [RMSE, scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.root_mean_squared_error.html)
- [Pinball loss, scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.mean_pinball_loss.html)
- [NumPy quantile](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html)
- [Metodi semplici, Forecasting: Principles and Practice](https://otexts.com/fpp3/toolbox.html)
- [pandas date_range](https://pandas.pydata.org/docs/reference/api/pandas.date_range.html)
