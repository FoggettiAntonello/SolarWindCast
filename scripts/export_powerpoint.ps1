#Requires -Version 5.1
<#
.SYNOPSIS
Crea una copia PowerPoint modificabile dall'outline delle slide HTML.
.DESCRIPTION
Richiede Microsoft PowerPoint locale. Mantiene 12 slide, usa grafici/tabelle
nativi e incorpora le immagini. Non scarica dati, pesi o librerie.
Preparare l'outline con python -m solarwindcast.powerpoint_outline.
.PARAMETER OutlineDirectory
Cartella temporanea nuova contenente outline.json e sources.svg.
.PARAMETER OutputPath
File PPTX di destinazione, che non deve esistere.
.PARAMETER PreviewDirectory
Cartella temporanea delle 12 immagini renderizzate da PowerPoint.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutlineDirectory,
    [Parameter(Mandatory)][string]$OutputPath,
    [Parameter(Mandatory)][string]$PreviewDirectory
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$assetRoot = Join-Path $projectRoot 'src/solarwindcast/assets'
$slidesData = Get-Content -LiteralPath (Join-Path $OutlineDirectory 'outline.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($slidesData.Count -ne 12) { throw 'Sono richieste esattamente 12 slide.' }
if (Test-Path -LiteralPath $OutputPath) { throw 'Il PowerPoint esiste già: nessuna sovrascrittura implicita.' }
if (Test-Path -LiteralPath $PreviewDirectory) { throw 'La cartella anteprime esiste già.' }
New-Item -ItemType Directory -Path $PreviewDirectory | Out-Null

function Convert-Color([string]$HexColor) {
    $h = $HexColor.TrimStart('#')
    return [Convert]::ToInt32($h.Substring(0,2),16) + 256 * [Convert]::ToInt32($h.Substring(2,2),16) + 65536 * [Convert]::ToInt32($h.Substring(4,2),16)
}
function Add-Text($Slide,[string]$Text,[double]$Left,[double]$Top,[double]$Width,[double]$Height,[double]$Size,[bool]$Bold=$false,[string]$Color='#193f36') {
    $shape = $Slide.Shapes.AddTextbox(1,$Left,$Top,$Width,$Height)
    $shape.TextFrame.MarginLeft = 0
    $shape.TextFrame.MarginRight = 0
    $shape.TextFrame.MarginTop = 0
    $shape.TextFrame.MarginBottom = 0
    $shape.TextFrame.WordWrap = -1
    $shape.TextFrame.TextRange.Text = $Text
    $shape.TextFrame.TextRange.Font.Name = 'Segoe UI'
    $shape.TextFrame.TextRange.Font.Size = $Size
    $shape.TextFrame.TextRange.Font.Bold = $(if ($Bold) { -1 } else { 0 })
    $shape.TextFrame.TextRange.Font.Color.RGB = Convert-Color $Color
    $shape.TextFrame.TextRange.ParagraphFormat.SpaceAfter = 0
    return $shape
}
function Add-NativeChart($Slide,$Spec,[double]$Top,[double]$Height) {
    $chartShape = $Slide.Shapes.AddChart(57,477,$Top,426,$Height)
    $chart = $chartShape.Chart
    $chart.ChartData.Activate()
    $workbook = $chart.ChartData.Workbook
    try {
        $sheet = $workbook.Worksheets.Item(1)
        [void]$sheet.Cells.Clear()
        $hasNominal = $null -ne $Spec.rows[0].nominal
        $sheet.Cells.Item(1,1).Value2 = 'Metodo'
        $sheet.Cells.Item(1,2).Value2 = $(if ($hasNominal) { 'Osservata' } else { 'Indicatore' })
        if ($hasNominal) { $sheet.Cells.Item(1,3).Value2 = 'Nominale' }
        for ($j=0;$j -lt $Spec.rows.Count;$j++) {
            $sheet.Cells.Item($j+2,1).Value2 = [string]$Spec.rows[$j].label
            $sheet.Cells.Item($j+2,2).Value2 = [double]$Spec.rows[$j].value
            if ($hasNominal) { $sheet.Cells.Item($j+2,3).Value2 = [double]$Spec.rows[$j].nominal }
        }
        $lastCol = $(if ($hasNominal) { 'C' } else { 'B' })
        $source = "='" + $sheet.Name + "'!" + '$A$1:$' + $lastCol + '$' + ($Spec.rows.Count+1)
        $chart.SetSourceData($source,2)
        $chart.HasLegend = $(if ($hasNominal) { -1 } else { 0 })
        if ($hasNominal) { $chart.Legend.Position = -4107; $chart.Legend.Font.Size = 9 }
        $chart.HasTitle = -1
        $chart.ChartTitle.Text = [string]$Spec.title
        $chart.ChartTitle.Font.Name = 'Segoe UI'
        $chart.ChartTitle.Font.Size = 12
        $chart.ChartTitle.Font.Bold = -1
        $chart.ChartTitle.Font.Color = Convert-Color '#244b3e'
        $chart.ChartArea.Font.Name = 'Segoe UI'
        $chart.ChartArea.Font.Size = 10
        $chart.ChartArea.Format.Fill.Visible = 0
        $chart.ChartArea.Format.Line.Visible = 0
        $chart.PlotArea.Format.Fill.Visible = 0
        $chart.PlotArea.Format.Line.Visible = 0
        $chart.Axes(1).ReversePlotOrder = -1
        $chart.Axes(1).TickLabels.Font.Size = 10
        $chart.Axes(1).Format.Line.Visible = 0
        $chart.Axes(2).MinimumScale = 0
        $chart.Axes(2).TickLabels.Font.Size = 8
        $chart.Axes(2).HasMajorGridlines = 0
        $chart.Axes(2).Format.Line.ForeColor.RGB = Convert-Color '#d1d9ce'
        if ($hasNominal) { $chart.Axes(2).MaximumScale = 100 }
        $series = $chart.SeriesCollection(1)
        $series.ApplyDataLabels()
        $series.DataLabels().Position = 2
        # Office usa qui i separatori della lingua italiana dell'installazione.
        $series.DataLabels().NumberFormat = '#.##0,00'
        $series.DataLabels().Font.Name = 'Segoe UI'
        $series.DataLabels().Font.Size = 10
        $series.Format.Fill.ForeColor.RGB = Convert-Color '#087e8b'
        for ($j=0;$j -lt $Spec.rows.Count;$j++) {
            $series.Points($j+1).Format.Fill.ForeColor.RGB = Convert-Color $Spec.rows[$j].color
            $series.Points($j+1).Format.Line.Visible = 0
        }
        if ($hasNominal) {
            $chart.SeriesCollection(2).Format.Fill.ForeColor.RGB = Convert-Color '#c6d4c9'
            $chart.SeriesCollection(2).Format.Line.Visible = 0
        }
        $chart.ChartGroups(1).GapWidth = 65
    } finally {
        # Excel puo' essere occupato per un breve istante dopo il rendering del grafico.
        $closed = $false
        for ($attempt=0;$attempt -lt 10 -and -not $closed;$attempt++) {
            try { $workbook.Close($true); $closed = $true }
            catch { if ($attempt -eq 9) { throw }; Start-Sleep -Milliseconds 300 }
        }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
    }
}

$powerpoint = New-Object -ComObject PowerPoint.Application
$initialCount = $powerpoint.Presentations.Count
$presentation = $null
$geometry = @()
try {
    # Il motore dei grafici di Office richiede una finestra; resta ridotta a icona.
    $presentation = $powerpoint.Presentations.Add(-1)
    $presentation.Windows.Item(1).WindowState = 2
    $presentation.PageSetup.SlideWidth = 960
    $presentation.PageSetup.SlideHeight = 540
    # Alcune installazioni Office non espongono la raccolta dei metadati via COM.
    for ($i=0;$i -lt $slidesData.Count;$i++) {
        $data = $slidesData[$i]
        $slide = $presentation.Slides.Add($i+1,12)
        $background = $slide.Shapes.AddPicture((Join-Path $assetRoot 'energy_background.png'),0,-1,0,0,960,540)
        $background.Name = 'Sfondo decorativo - sole e pale eoliche'
        $background.AlternativeText = 'Illustrazione decorativa generata: sole e pale eoliche, non sito reale.'
        [void](Add-Text $slide 'SolarWindCast' 36 20 350 22 11 $true)
        [void](Add-Text $slide ([string]$data.chapter).ToUpperInvariant() 36 79 384 18 9 $true '#527465')
        $title = Add-Text $slide $data.title 36 108 382 140 26 $true
        $title.Height = [math]::Ceiling($title.TextFrame.TextRange.BoundHeight)+3
        $nextY = $title.Top + $title.Height + 18
        foreach ($p in $data.paragraphs) {
            $text = Add-Text $slide $p.text 36 $nextY 382 240 14 ([bool]$p.emphasis)
            $text.Height = [math]::Ceiling($text.TextFrame.TextRange.BoundHeight)+3
            if ($p.emphasis) { $text.TextFrame.TextRange.Font.Color.RGB = Convert-Color '#285b4d' }
            if ($p.links.Count -eq 1) { $text.ActionSettings(1).Hyperlink.Address = [string]$p.links[0].href }
            $nextY = $text.Top + $text.Height + 13
        }
        if ($nextY -gt 501) { throw "Testo troppo lungo nella slide $($i+1): $nextY" }
        $panel = $slide.Shapes.AddShape(5,459,83,465,409)
        $panel.Fill.Solid()
        $panel.Fill.ForeColor.RGB = Convert-Color '#fffdf6'
        $panel.Fill.Transparency = .12
        $panel.Line.ForeColor.RGB = Convert-Color '#d5dfcf'
        $panel.Line.Weight = .6
        $panel.Adjustments.Item(1) = .04
        if ($data.artwork) {
            $artPath = if ($data.artwork -eq 'map') { Join-Path $assetRoot 'italy_regions.svg' } else { Join-Path $OutlineDirectory 'sources.svg' }
            $artHeight = if ($data.artwork -eq 'map') { 305 } else { 263 }
            $art = $slide.Shapes.AddPicture($artPath,0,-1,479,105,425,$artHeight)
            $art.AlternativeText = $(if ($data.artwork -eq 'map') { 'Regioni amministrative, non zone elettriche: Puglia e Calabria evidenziate.' } else { 'ENTSO-E: dati utilizzati. Open-Meteo: predisposto, escluso dai risultati.' })
        }
        if ($data.tables.Count) {
            $spec = $data.tables[0]
            [void](Add-Text $slide $spec.caption 479 111 425 43 16 $true)
            $table = $slide.Shapes.AddTable($spec.rows.Count,2,479,165,425,214).Table
            $table.Columns.Item(1).Width = 180
            $table.Columns.Item(2).Width = 245
            for ($r=0;$r -lt $spec.rows.Count;$r++) {
                for ($c=0;$c -lt 2;$c++) {
                    $cell = $table.Cell($r+1,$c+1).Shape
                    $cell.TextFrame.TextRange.Text = [string]$spec.rows[$r][$c]
                    $cell.TextFrame.TextRange.Font.Name = 'Segoe UI'
                    $cell.TextFrame.TextRange.Font.Size = 13
                    $cell.TextFrame.TextRange.Font.Bold = $(if ($c -eq 0) { -1 } else { 0 })
                    $cell.TextFrame.TextRange.Font.Color.RGB = Convert-Color '#244b3e'
                    $cell.Fill.Solid()
                    $cell.Fill.ForeColor.RGB = Convert-Color '#fffdf6'
                    $cell.Fill.Transparency = .1
                    $cell.TextFrame.MarginLeft = 8
                    $cell.TextFrame.MarginRight = 8
                    $cell.TextFrame.MarginTop = 9
                    $cell.TextFrame.MarginBottom = 6
                }
            }
        }
        $chartCount = $data.charts.Count
        for ($j=0;$j -lt $chartCount;$j++) {
            $chartTop = if ($chartCount -eq 2) { 103+161*$j } else { 104 }
            $chartHeight = if ($chartCount -eq 2) { 135 } else { 280 }
            Add-NativeChart $slide $data.charts[$j] $chartTop $chartHeight
            $unit = ([string]$data.charts[$j].unit).Replace('tratteggio = livello nominale','serie grigia = livello nominale')
            [void](Add-Text $slide $unit 480 ($chartTop+$chartHeight+3) 421 23 8 $false '#607569')
        }
        [void](Add-Text $slide $data.caption 479 439 425 46 9 $false '#536b5e')
        [void](Add-Text $slide 'Valutazione retrospettiva - dati reali' 36 517 600 15 9 $false '#496c5a')
        [void](Add-Text $slide "$($i+1) / 12" 865 514 60 18 11 $true)
        $notes = $data.title + "`n`n" + (($data.paragraphs | ForEach-Object { $_.text }) -join "`n`n") + "`n`n" + $data.caption
        $notes += "`n`nFonti: docs/portfolio/metrics.json e approfondimento details.html. Dati estratti dall'HTML con precisione numerica completa. ENTSO-E: https://transparency.entsoe.eu/ . Open-Meteo: https://open-meteo.com/ . Mappa: Openpolis geojson-italy, CC BY 4.0, https://github.com/openpolis/geojson-italy . Sfondo generato con imagegen; illustrazione, non fotografia di un sito reale. Nessuna nuova inferenza o fit."
        $slide.NotesPage.Shapes.Placeholders(2).TextFrame.TextRange.Text = $notes
        $geometry += [pscustomobject]@{slide=$i+1;title=$data.title;textBottom=$nextY;charts=$chartCount;tables=$data.tables.Count}
        Write-Output "Slide $($i+1)/12 creata."
    }
    # Secondo passaggio: Office stabilizza la lingua dei formati dopo il primo workbook.
    foreach ($slide in $presentation.Slides) {
        foreach ($shape in $slide.Shapes) {
            if ($shape.HasChart -eq -1) {
                $labels = $shape.Chart.SeriesCollection(1).DataLabels()
                $labels.NumberFormatLinked = $false
                $labels.NumberFormat = '#.##0,00'
            }
        }
    }
    $officeDraft = Join-Path $PreviewDirectory 'office-draft.pptx'
    $presentation.SaveAs($officeDraft,24)
    $geometry | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PreviewDirectory 'geometry.json') -Encoding UTF8
} finally {
    if ($null -ne $presentation) { $presentation.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) }
    if ($initialCount -eq 0 -and $powerpoint.Presentations.Count -eq 0) { $powerpoint.Quit() }
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($powerpoint)
    [GC]::Collect()
}
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
& $pythonPath -B -m solarwindcast.powerpoint_outline --finalize-pptx $officeDraft --output $OutputPath
if ($LASTEXITCODE -ne 0) { throw 'Finalizzazione PowerPoint fallita.' }
$viewer = New-Object -ComObject PowerPoint.Application
$initialViewerCount = $viewer.Presentations.Count
$verifiedDeck = $null
try {
    $verifiedDeck = $viewer.Presentations.Open($OutputPath,-1,0,0)
    for ($i=1;$i -le $verifiedDeck.Slides.Count;$i++) {
        $verifiedDeck.Slides.Item($i).Export((Join-Path $PreviewDirectory ("slide{0:00}.png" -f $i)),'PNG',1600,900)
    }
} finally {
    if ($null -ne $verifiedDeck) { $verifiedDeck.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($verifiedDeck) }
    if ($initialViewerCount -eq 0 -and $viewer.Presentations.Count -eq 0) { $viewer.Quit() }
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($viewer)
}
Write-Output "PowerPoint salvato e renderizzato: $OutputPath"
