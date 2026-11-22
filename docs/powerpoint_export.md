# Copia PowerPoint della presentazione

La copia richiesta e' [PresentazioneSolarWindCast.pptx](portfolio/PresentazioneSolarWindCast.pptx).
Mantiene le dodici slide dell'[HTML](portfolio/index.html), con lo stesso
sfondo decorativo di sole e pale eoliche. Testi, tabelle e grafici sono nativi
e modificabili; mappa e illustrazioni delle fonti sono immagini incorporate.
Per le coperture, il PowerPoint usa una serie grigia nominale al posto dei
tratteggi dell'HTML. Dati e significato del confronto restano uguali.

## Rigenerazione su Windows

Richiede Microsoft PowerPoint con il componente Excel dei grafici disponibile.
Non e' richiesto per i test ordinari o per consultare le slide HTML.
Il runtime Artifact Tool della skill non e' disponibile in questo ambiente:
l'esportazione usa il modello a oggetti ufficiale del PowerPoint locale,
senza installare librerie alternative di authoring.

Dalla radice, scegliere directory temporanee e file di output **nuovi**:

```powershell
.\.venv\Scripts\python.exe -B -m solarwindcast.powerpoint_outline `
  --input docs/portfolio/index.html --output "$env:TEMP/solarwindcast-outline-new"
.\scripts\export_powerpoint.ps1 `
  -OutlineDirectory "$env:TEMP/solarwindcast-outline-new" `
  -OutputPath "$env:TEMP/PresentazioneSolarWindCast-new.pptx" `
  -PreviewDirectory "$env:TEMP/solarwindcast-previews-new"
```

Il comando rifiuta di sovrascrivere il PowerPoint. PowerPoint resta ridotto a
icona mentre costruisce i grafici e produce una PNG per ogni slide nella
cartella delle anteprime. Lo script chiude solo la presentazione che ha creato.
La cartella del progetto non riceve file intermedi di build.

L'outline conserva i numeri completi degli aggregati: i dati del grafico non
vengono ricostruiti dai valori arrotondati visibili. Nessun nuovo modello,
download energetico o fit e' coinvolto.

Provenienza delle immagini: [mappa regionale](licenses/geographic_visual.md)
e [sfondo generato](licenses/presentation_background.md). Citazioni e limiti
sono conservati anche nelle note del relatore.
