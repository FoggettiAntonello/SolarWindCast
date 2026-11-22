# Primo esperimento Timestral — protocollo proposto

**Aggiornamento:** protocollo successivamente approvato dall'utente ed eseguito.
La proposta e l'anteprima originali sono conservate come registro precedente
all'esecuzione. [Risultati e limiti](timestral_improvement_results.md),
[presentazione reale](../reports/timestral_improvement_results_20261110/presentazione.html).

Stato: **DA DECIDERE — proposta da approvare, nessuna nuova inferenza eseguita**.
L'ultimo «procedi» autorizza la definizione dell'esperimento proposta nel messaggio
precedente. Questo documento rende concrete le impostazioni prima dell'esecuzione.
La sezione `timestral_improvement.proposal` della configurazione unica contiene
i candidati; `execution_authorized=false`, `training_authorized=false`.
Lo snapshot dello Step 10 e i risultati degli Step 11/12 restano invariati.

## Domanda e budget limitato

Un contesto di un anno, anziché due, migliora il totale mensile previsto da
Timestral? Il confronto comprende entrambe le taglie e le varianti già presenti.

| Parametro | Proposta |
|---|---|
| Target | Solare ed eolico terra + mare, separati |
| Taglie | 5M e 28M, revisioni già congelate |
| Contesto | 12 oppure 24 mesi |
| Covariate | Solo target oppure mese-seno/mese-coseno già verificati |
| Varianti | 2 × 2 × 2 = 8 per target, comprese le quattro originali |
| Origini di selezione | Intersezione delle origini ammissibili nello sviluppo |
| Orizzonte/emissione | Due passi mensili, solo ultimo valutato, 12h prima del mese |
| Unità | MW medi mensili previsti, quantili trasformati direttamente in MWh |
| Calcolo | CPU un thread, solo pesi locali; nessun training o download |

Non introduciamo contemporaneamente festività, altre feature, calibrazione o
fine tuning: saranno eventuali esperimenti separati e non ricerche automatiche
per ottenere una percentuale positiva. Non è esclusa a priori nessuna delle
due taglie. Il contesto 12 è soltanto un candidato: non è dichiarato migliore.

## Periodi e confronti equi

La selezione usa soltanto lo sviluppo novembre 2021–ottobre 2024. Con i vincoli
già approvati sono comuni 11 origini, dicembre 2023–ottobre 2024. I 12 mesi
possono consentire più origini, ma non vengono usate per avvantaggiarli nel
confronto diretto con i 24 mesi. Tutte le previsioni ricevono solo dati disponibili
al medesimo cutoff; il mese immediatamente precedente ancora in corso è escluso.
Nessun parametro è adattato alle etichette in questo esperimento zero-shot.

Le quattro varianti a 24 mesi hanno già 88 previsioni di sviluppo sui due target:
si possono riusare dopo verifica di manifest, protocollo, revisioni e mesi del
contesto. Le quattro a 12 mesi richiedono al massimo **88 nuove inferenze**.
Questi sono conteggi preventivi, non inferenze già eseguite o stime di durata.
Se la cache non è coerente, interrompere; nessun ricalcolo fuori budget implicito.

Tre baseline deterministiche restano fisse, con le impostazioni originarie,
e sono valutate sugli stessi mesi comuni. Il riferimento probabilistico rolling
ha meno casi ammissibili per l'eolico: i suoi confronti usano un sottoinsieme
esplicito separato e non riducono a quattro mesi l'intera selezione puntuale.
Le metriche probabilistiche tra varianti Timestral usano tutti i mesi comuni.

## Regola proposta per chiamare promettente un candidato

Per ciascun target il riferimento Timestral è la migliore delle quattro
varianti originali a 24 mesi, determinata sui medesimi 11 mesi di sviluppo,
non il vincitore del test. Si conservano sempre tutti i risultati originali.

Un candidato può essere promosso solo se soddisfa **tutti** questi criteri:

- MAE inferiore di almeno il 5% rispetto al riferimento Timestral e alla migliore
  delle tre baseline deterministiche sullo stesso insieme di mesi;
- errore assoluto inferiore al riferimento Timestral in almeno il 60% dei mesi,
  cioè almeno sette su undici; i pareggi non contano come vittorie;
- RMSE e pinball non peggiori del riferimento Timestral;
- copertura osservata non peggiore a entrambi i livelli 80/90%, con ampiezza
  media non superiore al 110% di quella del riferimento a ciascun livello.

Il 5% è una proposta di utilità pratica, non una soglia di significatività.
Undici mesi, finestre correlate e selezione tra varianti non dimostrano una
superiorità generale. I punteggi vanno pubblicati anche se i criteri falliscono;
una copertura relativa migliore può comunque essere insufficiente in assoluto.

Se più candidati passano: minore MAE, poi pinball, poi taglia minore, contesto
maggiore e solo target, in quest'ordine. Nessuna nuova variante per sciogliere
un risultato sgradito. Se nessuno passa, mantenere il riferimento originale
e fermare la ricerca; questo non garantisce una soluzione operativa validata.

## Confronto successivo e limite del test già osservato

Congelare al massimo un candidato per target prima di rileggere le prestazioni
nel periodo novembre 2024–ottobre 2026. Se un candidato viene promosso, fare
un solo confronto esplorativo con riferimenti e baseline, senza ulteriori scelte.
Al massimo 24 emissioni × 2 target = **48 nuove inferenze**; zero se nessuno
passa o se le previsioni selezionate sono già nella cache verificata.
Budget massimo complessivo: **136 nuove inferenze**, senza estensioni automatiche.
Anche i mesi con osservazione incompleta restano previsti ma esclusi dagli score.

Il vecchio test è già stato esaminato: non è una conferma indipendente, anche
se le nuove scelte vengono fatte sullo sviluppo. Un candidato che migliora
solo nel vecchio test non viene scelto retroattivamente. Per un'affermazione
più forte serviranno nuove previsioni registrate prima dei valori osservati.
Le future date e la durata di tale verifica restano DA DECIDERE.

## Risultati attesi come formato, non come prestazioni promesse

Report HTML con tutte le varianti, errore per origine, copertura e ampiezza,
tabella dei criteri superati/falliti e motivazione dell'eventuale mancata promozione.
JSON con previsioni, score, origini, revisioni, maschere e hash. Nessun numero
di miglioramento viene inventato o promesso; nessun valore difficile rimosso.

Il confronto con altri modelli e il training reale restano rinviati.
