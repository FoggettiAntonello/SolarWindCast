# SolarWindCast — istruzioni per gli agenti

Leggere AGENTS.md e PROGRESS.md all'inizio di ogni sessione.

## Obiettivo

Prevedere nel breve periodo la produzione solare ed eolica della zona
di mercato Sud, con intervalli di incertezza. Confrontare Timestral
con baseline e valutare onestamente errori e affidabilità.

Aggiornamento dell'utente del 7 novembre 2026: il risultato principale richiesto
è l'energia totale del prossimo mese di calendario, in MWh, per solare ed eolico
separatamente. Le serie orarie in MW restano la base; la proposta di orizzonte
24 ore è superata. Protocollo confermato: mese UTC, eolico terra + mare,
24 mesi di contesto, emissione 12h prima del mese, previsione mensile diretta
di potenza media e conversione in MWh. Configurazione in monthly_protocol
nel YAML; Step 10 concluso. Step 11 mensile eseguito con target/calendario;
varianti meteo rinviate alla verifica degli archivi. Step 12 autorizzato il
9 novembre: download quinquennale autorizzato e completato, backtest reale
concluso. Carico: 60 mesi completi; residuo: 52. Test comune: 24/23 mesi.
Report in reports/step12_monthly_20261109/. Sul MAE carico sostanziale parità;
residuo 5M/calendario -13,13% rispetto alla migliore baseline, solo nel campione.
Step 13 non autorizzato.
Il 10 novembre l'utente chiede di dare priorità al miglioramento di Timestral
e all'utilità reale prima degli altri modelli. Piano in
docs/timestral_improvement_plan.md; nuovi parametri, budget e training non
ancora approvati. Conservare protocollo congelato e riferimenti precedenti.
Successivo «procedi»: definito protocollo proposto in
docs/timestral_improvement_protocol.md e timestral_improvement nel YAML.
Contesti 12/24, 5M/28M, solo target/calendario, 11 origini comuni; budget
proposto 88 inferenze sviluppo + massimo 48 esplorative. Nessuna nuova
inferenza eseguita. Soglie e impostazioni da approvare prima dell'esecuzione.
Con «procedi pure con il protocollo» l'utente approva griglia, soglie e budget.
Esperimento eseguito: 88 nuove inferenze sviluppo, 88 riusi, nessuna promozione;
report in reports/timestral_improvement_results_20261110/. Eolico 28M/calendario/12
migliora MAE sviluppo del 19,88% ma peggiora pinball/ampiezze oltre i limiti;
solare peggiora con 12 mesi. Nessun confronto esplorativo successivo, training
o ampliamento della ricerca. Nuovi esperimenti da concordare.
Successiva calibrazione eolica controllata autorizzata e conclusa:
reports/wind_calibration_20261110/, metodo in docs/wind_calibration.md.
Un fattore positivo regolarizzato, mediana invariata; soli errori passati al
cutoff, minimo sei. Quattro mesi valutabili: pinball -4,82%, ampiezze -21,6%,
copertura80 4/4→3/4, copertura90 4/4. Nessuna promozione, inferenza nuova o
fine tuning. Suggerite cinque origini aggiuntive già nei dati e successive
verifiche di storico/capacità/meteo; non ancora autorizzate o eseguite.
Successivo «procedi pure»: recuperate le cinque origini luglio–novembre 2023,
stesso 28M/calendario/12 e calibrazione invariata. Report in
reports/wind_calibration_extended_20261110/: nove mesi valutabili febbraio–ottobre
2024, pinball -3,83% vs non calibrato, bande -6,89%, mediana invariata.
Sul vecchio sottoinsieme di quattro mesi nuova pinball +1,82% rispetto alla
prima calibrazione: non tutto migliora con più dati. Nessuna promozione o
uso del vecchio test. Audit di storico lungo/capacità/meteo ancora da autorizzare.
Successivo «procedi»: audit storico lungo autorizzato e concluso, report in
reports/history_feasibility_20261110/ e docs/history_feasibility_audit.md.
Tre campioni2016/2018/gennaio2021: solare/onshore24ore validi, offshore assente.
ARERA documenta il cambio Sud/Calabria dal2021: niente concatenazione cieca
di8–10anni. Offshore: copertura locale dal26maggio2022, primo positivo5giugno;
fonti indicano date di avvio diverse, nessun NaN convertito in zero.
Eventuale lotto gennaio–ottobre2021 e politica di zeri strutturali da approvare.
Nessun download massivo, modifica dei dataset o nuova inferenza eseguiti nell'audit.
Successivo «procedi»: verificata fattibilità macroarea Sud + Calabria con
quattro campioni e somma stretta di osservazioni, report in
reports/macroarea_feasibility_20261110/ e docs/macroarea_feasibility.md.
Solare/onshore aggregabili nei campioni2021/2026; totale eolico incompleto
per offshore Calabria assente. Rossano2020 restituisce rinnovabili positive:
raccordo dei poli e rischio doppio conteggio da verificare prima del pre-2021.
Target ufficiale e risultati precedenti invariati. Download completo, regole
offshore/raccordo e cambio geografico operativo non ancora approvati.
Verifica aggiuntiva fine tuning 5M/28M autorizzata e conclusa: audit in
reports/finetuning_feasibility_20261109/. Gradiente sintetico sulla testa
possibile, nessun aggiornamento pesi o training reale. Solo 11 origini di
sviluppo per target; protocollo di eventuale adattamento ancora da concordare.
Non sommare quantili orari per dichiarare intervalli del totale mensile.
L'utente ha poi autorizzato cinque anni di produzione, novembre 2021–ottobre
2026, con tre anni di sviluppo e due di test. Verificare la copertura effettiva;
la disponibilità delle previsioni meteo per l'intero storico resta da accertare.

Consumi elettrici e carico residuo sono estensioni successive.
La zona Sud non coincide con la sola Puglia.

Il progetto è un portfolio: rigore, riproducibilità e chiarezza
contano più di risultati spettacolari.

## Metodo di lavoro

22 novembre, successiva richiesta esplicita: slide autore spostata dalla
posizione13 alla1 e foto fornita dall’utente incorporata senza ritagli né
deformazioni.13slide totali,12scientifiche nello stesso ordine.9grafici e
9workbook identici byte per byte; testi scientifici invariati. PowerPoint/PDF
rigenerati e copertina renderizzata con Office, verificata visivamente.
Nuovo SHA256PPT: 5cc00e8d0505b729fe1d2cbee7652b78a79fc9b5496d1a5542abe3c2a5a3dd77.
Pubblicazione delle sole due copie documento in corso; homepage non modificata.
Metriche invariate,zero inferenze/fit. Release finale ancora da chiudere.


22 novembre: utente conferma antonello.foggetti@gmail.com e autorizza la
slide autore e l’inserimento sul sito personale. PowerPoint aggiornato a
13 slide (12 di progetto + contatti), PDF esportato da Office. Nuovo SHA256:
dfdb85878d753b0c8671493712954b86795964d37bc5dd59131371fb82c74298.
Nove XML dei grafici e nove workbook identici all’originale; testi scientifici
invariati,solo contatori aggiornati. Metriche JSON intatte. PowerPoint e PDF
riaperti/esportati con Office; slide autore verificata visivamente.
Sito personale: quarta scheda SolarWindCast, senza sostituire Sports. Solo
44 righe aggiunte e due documenti; rimuovendo il nuovo blocco si recupera
l’HTML precedente byte per byte. Commit sito e6fec31; Pages superato:
https://github.com/FoggettiAntonello/FoggettiAntonello.github.io/actions/runs/45047981562
Homepage e documenti pubblici HTTP200; hash PDF/PPT coincidono con le copie
locali. Verifiche layout desktop e mobile390px senza overflow, link leggibili.
Azure non attivato per verifica carta; nessuna risorsa cloud Azure creata.
GitHub Pages usato per la presentazione, senza inferenze cloud.380 test passati,
uno escluso,pip/Ruff puliti. Nessuna nuova inferenza o fit. Resoconto:
docs/portfolio_site_update_20261122.html/.json. CI commit65949e7 superata:
https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45048301632
PDF pubblico verificato visivamente alla pagina13; server locale arrestato.
Release finale ancora da chiudere.


22 novembre: primo push pubblico concluso (c22d2be), clone GitHub verificato:
380 test passati,uno opzionale escluso,pip/Ruff puliti,audit e sito validi.
Prima CI Windows/Python3.12.10/PyTorchCPU da Internet SUPERATA; log confermano
380 test passati,uno escluso,demo baseline e audit sito superati. Esito reale:
https://github.com/FoggettiAntonello/SolarWindCast/actions/runs/45040562965
Git utilizzabile dall'utente Windows,senza eccezioni globali safe.directory.
Nessun segreto,dato grezzo,peso o archivio privato pubblicato. Metriche e
PowerPoint invariati. Restano account/sottoscrizione Azure,deploy Free,verifica
URL pubblici,aggiornamento PowerPoint autorizzato dopo v1 e release finale.
Resoconto docs/github_publication_20261122.html/.json.


22 novembre: identità FoggettiAntonello verificata tramite API autenticata;
repository pubblico SolarWindCast creato. Nessuna credenziale stampata o
salvata nel progetto. Git locale inizializzato su main, autore con indirizzo
noreply;158 file ammessi preparati, audit MIT/hash/segreti superato.
380 test superati,uno opzionale escluso,pip/Ruff puliti. Primo push e CI
ancora da eseguire. PowerPoint invariato.


22 novembre, successivo «procedi»: approvati repository pubblico
FoggettiAntonello/SolarWindCast e licenza MIT del codice originale. LICENSE
creato; pubblicazione GitHub autorizzata dopo audit. PowerPoint invariato
fino al completamento Azure. Autenticazione e CI remote da verificare.


22 novembre, utente fornisce https://github.com/FoggettiAntonello come account
GitHub di destinazione. Autenticazione non ancora eseguita;nome repository,
visibilità e licenza MIT proposta ancora da confermare. Chiede esplicitamente
che il PowerPoint sia aggiornato DOPO tutti i passaggi v1.0 per includere la
pubblicazione Azure reale. Fino ad allora mantenere il file congelato e il suo
hash corrente. Al termine usare URL ed esiti effettivamente verificati,
restando entro13slide,senza dichiarare anticipatamente il cloud operativo.

22novembre:utente autorizza controlli e tenta chiusura oggi.380test passati,
uno escluso,pip/Ruff puliti sulla copia pubblica;zero inferenze/fit/download
energetici. publication.py+5test:allowlist,credenziali note/pattern anche dentro
Office,hashPPT/manifest,staging sito e link/ancore.Nessuna credenziale trovata.
Con Git attivo blocca file tracciati fuori dall'allowlist,verificato su clone.
8categorieGitignore verificate;repo/commit/clone solo in temp,Git originale
ancora disattivato. .gitattributes preserva hash portfolio/licenze CRLF/LF;
cloneLF e sito ricostruito passano.Sito10file~5,1MB,link0rotti,browserlocale
e PPT HTTP200;server poi arrestato.PowerPoint e metriche intatti.
CIWindowsCPU e deployAzure manuale predisposti con azioni a SHA verificati;
nessuna CIremota o pubblicazione già eseguita.CPUwheelHEAD200,non scaricata:
installazione CPU daInternet da verificare col primo runnerGitHub.
Licenze pesi5M/28M ricontrollateonline e identiche;READMEesplicita ModifiedMIT
e soglia20MUSD fatturatomensileprecedente.CodiceupstreamApache2 distinto.
Nessuna licenzaCCBYgenerale per datiENTSOE:pubblicare indicatori propri,
non originali/serie.MITcodiceproposta e domandaall'utente ancora pendente;
LICENSE non creato,gate --require-license attivo prima del rilascio.
Resoconto docs/release_checks_20261122.html/.json;procedura docs/publication.md.
Serve account/visibilitàGitHub e confermalicenza,loginbrowserGCM senza segreti
inchat.Poi push,CIreale,cloneGitHub,AzureFree.Obiettivo22novembre oggi.

22 novembre: utente conferma PowerPoint com'è e chiede roadmap di chiusura.
Congelare docs/portfolio/PresentazioneSolarWindCast.pptx;non modificarlo senza
richiesta esplicita.SHA256 83873a7601eb404501acca0d5c0bca4aa8edfa766678a7a0056a0e4f71bbabdb.
Git disattivato,CI/licenza progetto ancora assenti;blocchi4/5da completare.
Obiettivo controlli22–23,GitHub+clone24,Azure+release25,margine26;non dichiarare
conclusi controlli o pubblicazioni prima della verifica effettiva.

21 novembre,copiaPowerPoint richiesta e conclusa:
docs/portfolio/PresentazioneSolarWindCast.pptx,12slide16:9,Sole e turbine di
sfondo generati con imagegen e incorporati anche nell'HTML. Asset PNG incluso
nel pacchetto;prompt/provenienza docs/licenses/presentation_background.md.
9grafici nativi con workbook,3tabelle,testi modificabili;illustrazioni immagini.
Numeri completi estratti dall'HTML con powerpoint_outline.py;esportatore
scripts/export_powerpoint.ps1 usa PowerPoint/Excel locali;istruzioni in
docs/powerpoint_export.md. Runtimeartifact-tool assente,nessun sostituto
installato;usati Office e controlli OOXML. File riaperto e12slide renderizzate
con PowerPoint;dati e celle confrontati con HTML;struttura/geometria pulite,
nessun percorso privato nei XML.375test passati,uno escluso,pip/Ruff puliti.
Nessun dato energetico,inferenza o fit nuovi;metrics.json invariato.
Metadati autore e formati decimali normalizzati senza cambiare valori.
La copiaPPTX non viene sovrascritta dall'esportatore;usare una nuova destinazione.
Prossimo blocco4 invariato;nessuna pubblicazione GitHub/Azure effettuata.

21 novembre, richiesta di miglioramento estetico:stesse12slide con sfondo
sabbia/verde,accenti oro,mappa amministrativa Italia/Puglia/Calabria e
illustrazioni originali delle fonti ENTSO-E/Open-Meteo.Non sono loghi ufficiali;
meteo escluso dai risultati e geografia di mercato distinta dalla mappa.
SVG regionale da Openpolis CC BY4.0 in src/solarwindcast/assets/italy_regions.svg,
incluso tramite package-data e incorporato nell'HTML. Attribuzione/hash della
fonte in docs/licenses/geographic_visual.md. Sorgente2,75MB solo in temp;
nessun nuovo dato energetico,peso,inferenza o fit.metrics.json invariato.
373test passati,uno escluso,pip/Ruff puliti;wheel costruita e mappa leggibile
da wheel isolata.Desktop12slide senza scroll,mobile senza overflow orizzontale.
Prossimo blocco4 ancora da autorizzare:licenze/segreti/dati/CI;poi5pubblicazione.

21 novembre, utente richiede massimo13slide con grafico/dati affiancati:
Blocco3concluso. docs/portfolio/index.html ora12slide HTML autonome,navigazione
con frecce/pulsanti;testo a sinistra,SVG/tabella a destra. details.html separato
con tutti8studi/varianti/risultati persi. Metriche invariate,corrette solo etichette
dei periodi UTF-8 nel JSON;nessuna nuova
inferenza/fit. Generatore portfolio_slides.py integrato in portfolio_report,
due test sintetici nuovi;372test passati,uno escluso,pip/Ruff puliti,più4test
mirati dopo ritocchi. Tutte12schermate ispezionate,desktop1038x648 senza scroll
e mobile390px senza overflow orizzontale. README e manifest aggiornati.
Prossimo blocco4:segreti/licenze/dati/CI;poi5GitHub+clone+release+Azure.
Non pubblicare o dichiarare pronta la distribuzione prima di questi controlli.
Restare nel blocco autorizzato e fermarsi al riepilogo in attesa dell'ok.

21 novembre, pulizia approfondita autorizzata da «procedi» e conclusa:
sette cartelle principali rimosse (tre alberi archive,due demo reports,due
cartelle dati vuote).188file tolti dalle posizioni precedenti:26eliminati,
162conservati in due ZIP locali verificati SHA-256. archive contiene ora solo
README,historical_evidence_20261121.zip,git_metadata_disabled_20261121.zip.
Non estrarre sopra il progetto;Git disattivato. Risultati storici anche negativi
conservati;originali,datasetattuali,risultati reali e test utili intatti.
27report restano per risultati,audit e protocolli ancora usati dai comandi.
Registro/resoconto docs/cleanup_20261121.json/.html;link attivi aggiornati.
370test passati,uno escluso,pip/Ruff puliti;8sorgenti portfolio verificate,
bundle ricostruito identico;zero inferenze/fit. Prossimo blocco3 invariato.

21 novembre, successivo «ok procedi»: autorizzati sito Azure Static Web Apps Free
e pulizia. Blocco2 concluso: venv nuova isolata Windows/Python3.12.10,
dipendenze da wheel locali con torch2.11.0+cu128; setuptools78.1.0 scaricato1,3MB.
Wheel Timestral da commit fissato verificata; wheel SolarWindCast installata,
importazione isolata e CLI fuori repo riuscite.370test passati,uno opzionale
escluso,pip/Ruff puliti;13metriche demo identiche. Nessuna nuova inferenza.
Report docs/release_setup_validation.html/.json; CPU e installazione interamente
da Internet non ripetute. Rimossi segnaposto notebooks con istruzioni obsolete;
requirements ora rimanda a TOML/vincoli,vecchia lista GPU nell'archivio locale.
Test utili,originali e risultati conservati. docs/azure_publication.md e config
statica preparati; nessun cloud creato,accountAzure da identificare.
Prossimo blocco3:presentazione/grafici;poi4licenze/segreti/dati/CI;
5GitHub+clone+release+sitoAzure. Git ancora disattivato. Non pubblicare tutta
la cartella; predisporre bundle statico con lista esplicita e controllare i link.
Fermarsi al riepilogo e attendere l'ok prima del blocco successivo.

21 novembre: utente approva chiusura v1 entro cinque giorni e pubblicazione
finale GitHub. Obiettivo25novembre,limite26novembre. Perimetro:mensile e24ore
già valutati,risultati positivi in primo piano e confronti completi/fallimenti
accessibili;nessun nuovo esperimento,download,modello,training o meteo.
Streamlit e Step13 rinviati. Blocco1 concluso:README riscritto,backup originale
in archive/README_before_v1_20261121.md;docs/portfolio/index.html e metrics.json
autonomi con8studi e3claim scoped. Modulo portfolio_report,test e demo
backtest_demo --baselines-only senza pesi/token/rete,collaudata.
370test passati,uno opzionale escluso,pip/Ruff puliti,più ricontrolli mirati.
Prossimo blocco2:installazione pulita e comandi;poi3presentazione/grafici,
4segreti/licenze/dati/CI,5GitHub+clone+release1.0.0. Git ancora disattivato.
Non dichiarare setup pulito,pubblicazione o redistribuibilità già verificati.
Pubblicazione finale autorizzata dall'utente;effettuarla dopo i controlli,
chiarendo account/visibilità se non ricavabili dal contesto. Restare entro
il blocco autorizzato e fermarsi al riepilogo prima del successivo.

15 novembre successivo «procedi pure»: approvato ed eseguito replay orario,
reports/hourly_calibration_results_20261115/ e docs/hourly_calibration_results.md.
Zero nuove inferenze/training/download;36giorni solari864ore e54eolici1296ore.
Mediane e punti invariati. Pinball solare-0,63%,eolica-11,35%;coperture80/90
solari78,24%/89,58%,eoliche79,32%/90,28%. Criteri non tutti superati:pinball
vsbaseline +20,68%/+7,91%,riduzione solare insufficiente,ampiezza90 eolica
37%oltrebaseline (limite10%). Nessuna promozione;non cambiare le soglie.
367test passati,uno opzionale escluso,pip/Ruff puliti;controlli indipendenti
su metriche,correzioni,cutoff,mediane e hash. YAML esecuzione disabilitata.
Confrontarsi con utente prima di ulteriori esperimenti o portfolio:coperture
corrette in gran parte,superiorità complessiva ancora non dimostrata.

15novembre, successivo «procedi»: protocollo calibrazione oraria preparato in
docs/hourly_calibration_protocol.md e reports/hourly_calibration_protocol_20261115/.
Primitivi e5test sintetici implementati,nessun fit su dati reali. Metodo proposto:
allargamenti additivi nonnegativi80/90,mediana invariata,annidamento garantito,
lookback180giorni,minimo20giornate interamente disponibili (fine+ritardo24ore).
Replay proposto maggio2025–ottobre2026,origini1/8/22;giorno15 solo storico.
Pianificazione senza fit:solare36origini864ore,eolico54origini1296ore;solare
15esclusioni per storico e3originali.362test passati,uno opzionale escluso,
pip/Ruff puliti. Nessuna nuova metrica calibrata. Config hourly_calibration:
execution_authorized=false;budget0inferenze/training/download. Metodo e gate
da approvare prima del replay reale;non avviare fit automaticamente.

Successivo «Procedi»14novembre: estensione oraria conclusa su giorni1,8,22
prefissati, stesso5M/672ore/ritardo24ore,141nuove inferenze. Report
reports/hourly_extension_20261114/, metodo docs/hourly_extension.md.
Solare69giorni1656ore,eolico72giorni1728ore. MAE vs migliore baseline
-4,18%/-4,97%;pinball vs riferimento probabilistico+18,70%/+24,02%.
Copertura80 68,60%/45,89%,90 78,56%/58,22%,nessuna promozione.
Tre esclusioni solari(8/22aprile,1maggio2026)per contesto incompleto.
Vecchio pilota giorno15 separato e immutato;stessi mesi già osservati,
non test indipendente.357test passati,uno opzionale escluso,pip/Ruff puliti.
Nessuna calibrazione eseguita. Prossimo protocollo calibrazione oraria
da concordare,non avviare fit automaticamente.

14novembre successivo: utente autorizza test sull'orizzonte24ore. Pilota eseguito
in reports/hourly_pilot_20261114/, metodo docs/hourly_pilot.md. 5M target-only,
672ore contesto,ritardo assunto24ore,origine giorno15alle00UTC di24mesi.
47inferenze locali,zero download/training/meteo. Solare23origini552ore,
eolico24origini576ore;aprile2026solare escluso per contesto incompleto.
Contro migliore baseline stessa ora: MAE-5,36%solare/-7,73%eolico, ma pinball
+20,94%/+34,06%. Coperture80 71,20%/39,93%,90 79,89%/53,30%: nessuna
promozione. Solo pilota esplorativo, target mensile non sostituito. Estensione
oraria e nuovi interventi non autorizzati automaticamente. HTML metriche presente.

Successivo «procedi» del14novembre approva protocollo finale e budget24:
esperimento concluso in reports/final_wind_results_20261114/ e
docs/final_wind_results.md. 24 nuove inferenze,192 riusi,zero training/download.
Su24mesi candidato28M/calendario/12 calibrato peggiora MAE19,11% e pinball
24,43% contro riferimento24mesi; MAE13,10% peggiore della media recente.
Solo7vittorie/24 (richieste15). Calibrazione migliora pinball0,81% sullo
stesso candidato,mediana invariata,bande circa6,4% più strette;copertura90
22/24→21/24. Criteri non superati: fermare questa iterazione, nessuna nuova
variante o promozione. Vecchio test già visto,esplorativo. 354 test passati,
uno opzionale escluso,pip/Ruff puliti;metriche e cutoff verificati indipendentemente.
YAML execution_authorized=false dopo conclusione. Prima del portfolio fare
il punto con utente sull'esito negativo,senza promettere superiorità.

Successivo «procedi con il prossimo step» del 14 novembre: preparato protocollo
finale eolico in docs/final_wind_protocol.md e reports/final_wind_protocol_20261114/.
Unico candidato 28M/calendario/12 + calibratore invariato, riferimento a 24 mesi
e quattro baseline. Proposti 24 mesi novembre 2024–ottobre 2026 e massimo 24
nuove inferenze, CPU locale, zero training/download/nuovi metodi. Fit causale
degli errori, nessun uso del mese ancora aperto. Vecchio test già visto:
esplorativo, nessuna promozione automatica. Gate espliciti prima di eseguire,
MAE -5% anche vs baseline rolling, pinball/RMSE non peggiori, vittorie60%,
coperture/ampiezze e almeno12casi. HTML mostra solo metriche storiche sui nove
mesi comuni, nessun nuovo risultato. Esecuzione e budget NON ancora approvati;
YAML final_wind_experiment.execution_authorized=false, budget approvato0.

Richiesta dell'utente del 14 novembre: per i prossimi step fornire un resoconto
HTML delle metriche per verificare miglioramenti e peggioramenti. Includere
valori prima/dopo, variazioni assolute e percentuali dove definite, baseline e
riferimento espliciti, mesi comuni e numerosità, esclusioni e limiti. Riportare
MAE/RMSE, pinball, copertura e ampiezza degli intervalli quando disponibili,
spiegando la direzione desiderata. Non confrontare come equivalenti periodi,
target o geografie diversi. Se uno step non produce nuove metriche, dichiararlo
senza inventare miglioramenti o rieseguire esperimenti non autorizzati.

14 novembre: utente approva chiusura semplificata ma chiede risultati credibili
prima del portfolio. Audit in docs/readiness_review.md e
reports/readiness_review_20261114/: nessuna superiorità generale stabile
dimostrata; distinguere migliori nel test da scelte sullo sviluppo.
348 test passati, uno opzionale escluso, pip/Ruff puliti. Nessun nuovo modello
eseguito; conferma operativa e setup pulito ancora da dimostrare.
Versione principale Sud mensile solare/eolico terra + mare, macroarea come
estensione. Step 13, nuovi dati, fine tuning/meteo rinviati; HTML nella chiusura,
Streamlit rinviato. Portfolio dopo riesame. Prossimo passo consigliato:
protocollo finale eolico con candidato/riferimenti già studiati, criteri e
budget prima di eventuali correzioni. Nessuna nuova inferenza autorizzata.

Successivo «procedi pure» dell'11 novembre: Calabria novembre 2021–ottobre
2026 B16/B19 autorizzata e conclusa, 120 richieste riuscite senza retry.
Calabria completa, zero mancanti/negativi/segnalazioni rilevanti. Native 60/15
minuti segmentate e convertite solo per ore complete. Dataset separato in
data/processed/macroarea_70months_20261111/, report omonimo sotto reports/,
metodo docs/macroarea_70months.md. Gennaio 2021–ottobre 2026: 51.120 ore,
69 mesi solari e 70 onshore completi. Unico buco solare Sud: 2026-04-02 05 UTC,
resta NaN. 39 test mirati superati, hash e aggregati verificati indipendentemente.
Vecchi dataset e risultati invariati. Nessun B18, zero strutturale, inferenza,
training o nuovo target operativo. Protocollo macroarea/offshore e nuovi
esperimenti da concordare; pre-2021 non autorizzato.

Successivo «procedi pure» dell'11 novembre: lotto febbraio–ottobre 2021
concluso, 36 richieste Sud/Calabria B16/B19 tutte riuscite senza retry.
36 serie complete e nessuna anomalia segnalata. Con gennaio riusato:
7.296 ore complete per componente, 10 mesi solari e 10 onshore.
Report reports/macroarea_2021_extension_20261111/ e metodo
docs/macroarea_2021_extension.md. 24 test mirati superati, hash e totali
verificati. Nessun offshore, zero applicato, modello o vecchio dataset modificato.
Proposta successiva non autorizzata: Calabria novembre 2021–ottobre 2026
B16/B19, massimo 120 richieste prima di eventuali riusi, per una macroarea
fino a 70 mesi con il Sud esistente (copertura da verificare, solare Sud aprile
2026 già incompleto). Pre-2021 e politica offshore ancora separati.

Successivo «procedi» dell'11 novembre: pilota gennaio 2021 autorizzato e
concluso. Quattro richieste Sud/Calabria B16/B19, nessun retry, 744/744 ore
valide per ogni serie, nessuna anomalia segnalata. Somma macroarea osservata:
solare 206.775 MWh, onshore 1.247.706 MWh; primo giorno coincide con i vecchi
campioni. Report reports/macroarea_pilot_20261111/ e originali omonimi sotto
data/raw/entsoe/. 24 test mirati superati, nessun nuovo modulo scientifico.
Nessun offshore richiesto, zero applicato o modello eseguito; vecchi target
e risultati invariati. Lotto febbraio–ottobre 2021 (massimo 36 richieste,
Sud/Calabria B16/B19) proposto, non autorizzato. Storico completo e politica
offshore restano da approvare.

Successivo «procedi» dell'11 novembre: conclusi audit offshore e piano in
reports/offshore_policy_20261111/ e docs/offshore_policy_and_acquisition.md.
Proposte non applicate: zeri B18 mancanti 2019–2021; Calabria 2022–2025 per
inferenza, da validare sul dominio; Sud dal 2022 e Calabria 2026 restano NaN
dove mancanti. Fonti Renexia 2022 e IEA Wind TCP 2022/2025, retrospettive.
Piano 94 mesi: B16/B19 massimo 306 nuove richieste dopo 72 riusi esatti;
B18 separato massimo 159 dopo 30 riusi. Pilota proposto gennaio 2021,
Sud/Calabria B16/B19, massimo quattro richieste, nessun retry automatico.
Nessun download ENTSO-E, zero applicato o modello eseguito. Pilota e download
esteso non ancora autorizzati. Configurazione offshore_history_proposal.

Aggiornamento 11 novembre 2026: audit Sud/Rossano concluso in
reports/south_rossano_audit_20261111/ e docs/south_rossano_reconciliation.md.
Il bilancio nazionale del 30 dicembre 2020 chiude per solare/onshore solo
includendo Rossano, in tutte le 24 ore. Confine osservato con tre campioni
di quattro ore: 2020-12-31 23:00 UTC (mezzanotte italiana).
Ricetta candidata dal 2019: Sud + Rossano prima, Sud + Calabria dopo.
Supportata sui campioni, copertura storica completa non certificata.
Offshore irrisolto, nessuno zero applicato. Target operativo e risultati
precedenti invariati; nessun download completo o modello eseguito.
Politica offshore e acquisizione estesa ancora da autorizzare.
348 test superati, uno facoltativo escluso; Ruff pulito.

- Rispondere in italiano semplice e spiegare cosa si fa e perché.
- Usare PowerShell.
- Seguire gli step 0–14 descritti in PROGRESS.md.
- Eseguire soltanto lo step autorizzato.
- Alla fine fermarsi e riportare:
  "Cosa ho fatto", "Come puoi verificarlo", "Prossimo step".
- Aspettare l'ok dell'utente prima dello step successivo.
- Aggiornare PROGRESS.md a ogni step.
- Chiedere conferma prima di comandi pesanti, eliminazioni
  e sovrascritture.

## Codice e configurazione

- Ogni modulo deve avere docstring, type hint e almeno un test
  con dati sintetici.
- Target, frequenza, periodo, contesto, orizzonte, finestre,
  modelli e dispositivo devono essere configurabili.
- Il target può essere solare, eolico, carico o carico residuo.
- La configurazione unica YAML sarà introdotta allo Step 1.
- I parametri non approvati devono essere marcati "DA DECIDERE".
- Le impostazioni dei prototipi non sono decisioni definitive.

## Dati e sicurezza

- Usare timestamp UTC e distinguere potenza MW da energia MWh.
- Conservare originali e provenienza; segnalare buchi e anomalie.
- I mancanti restano NaN: nessuna correzione nascosta.
- Le covariate future devono essere conoscibili al momento
  della previsione.
- Distinguere previsioni operative, hindcast e meteo ricostruito.
- Considerare ritardi di pubblicazione e revisioni dei dati.
- Mai stampare o tracciare segreti. ENTSOE_API_KEY va in .env.
- .env.example deve contenere soltanto il campo vuoto.

## Librerie e Timestral

Verificare online la documentazione attuale prima di usare
librerie o API.

Prima di usare Timestral consultare:
- https://github.com/mistralai/timestral
- https://huggingface.co/mistralai/Timestral-28M

Documentare versione e revisione dei pesi.
Distinguere la licenza del codice da quella dei pesi:
riportare nel README la Modified MIT dei pesi e la clausola
sul fatturato, verificandone il testo applicabile.

Non presentare i benchmark dichiarati da Mistral come risultati
verificati su SolarWindCast. Riportare anche i confronti persi.

## Stato esistente

Sono presenti prototipi, dati e un esperimento dimostrativo.
Non eliminarli o sovrascriverli senza conferma.
Verificarne la conformità al nuovo piano prima di riutilizzarli.
