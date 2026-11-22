#Requires -Version 5.1
<#
.SYNOPSIS
Aggiunge una slide autore a una copia del PowerPoint, mantenendo i grafici esistenti.
.DESCRIPTION
Richiede PowerPoint locale. Sorgente intatta, destinazione e anteprime nuove.
Nessuna rete, dato energetico, inferenza o nuova dipendenza.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][string]$OutputPath,
    [Parameter(Mandatory)][string]$PreviewDirectory,
    [Parameter(Mandatory)][string]$PresenterName,
    [Parameter(Mandatory)][string]$Email,
    [Parameter(Mandatory)][string]$GitHubUrl,
    [Parameter(Mandatory)][string]$RepositoryUrl,
    [string]$PortraitPath = ''
)
$ErrorActionPreference = 'Stop'
$source = (Get-Item -LiteralPath $SourcePath).FullName
if (Test-Path -LiteralPath $OutputPath) { throw 'Destinazione gia presente.' }
if (Test-Path -LiteralPath $PreviewDirectory) { throw 'Anteprime gia presenti.' }
[void](New-Item -ItemType Directory -Path $PreviewDirectory)
function Convert-Color([string]$Hex) {
    $h = $Hex.TrimStart('#')
    return [Convert]::ToInt32($h.Substring(0,2),16) + 256*[Convert]::ToInt32($h.Substring(2,2),16) + 65536*[Convert]::ToInt32($h.Substring(4,2),16)
}
function Add-Text($Slide,[string]$Text,[double]$X,[double]$Y,[double]$W,[double]$H,[double]$Size,[bool]$Bold=$false,[string]$Color='#193f36') {
    $shape = $Slide.Shapes.AddTextbox(1,$X,$Y,$W,$H)
    foreach ($side in @('MarginLeft','MarginRight','MarginTop','MarginBottom')) { $shape.TextFrame.$side=0 }
    $shape.TextFrame.WordWrap=-1
    $shape.TextFrame.TextRange.Text=$Text
    $shape.TextFrame.TextRange.Font.Name='Segoe UI'
    $shape.TextFrame.TextRange.Font.Size=$Size
    $shape.TextFrame.TextRange.Font.Bold=$(if($Bold){-1}else{0})
    $shape.TextFrame.TextRange.Font.Color.RGB=Convert-Color $Color
    return $shape
}
$app=New-Object -ComObject PowerPoint.Application
$initialCount=$app.Presentations.Count
$deck=$null
try {
    $deck=$app.Presentations.Open($source,-1,0,0)
    if($deck.Slides.Count -notin @(12,13)){throw 'Sono attese dodici slide o tredici con autore.'}
    $deck.Slides.Item(1).Export((Join-Path $PreviewDirectory 'original01.png'),'PNG',1600,900)
    $deck.Slides.Item(12).Export((Join-Path $PreviewDirectory 'original12.png'),'PNG',1600,900)
    if($deck.Slides.Count -eq 12) {
    $slide=$deck.Slides.Add(13,12)
    $slide.FollowMasterBackground=0
    $slide.Background.Fill.Solid()
    $slide.Background.Fill.ForeColor.RGB=Convert-Color '#f5f3eb'
    $background=Join-Path (Split-Path -Parent $PSScriptRoot) 'src/solarwindcast/assets/energy_background.png'
    [void]$slide.Shapes.AddPicture($background,0,-1,0,0,$deck.PageSetup.SlideWidth,$deck.PageSetup.SlideHeight)
    [void](Add-Text $slide 'SOLARWINDCAST / AUTORE' 40 38 800 23 12 $true '#496c5a')
    [void](Add-Text $slide $PresenterName 40 109 800 68 42 $true)
    [void](Add-Text $slide 'Autore del progetto SolarWindCast' 42 186 780 38 22 $false '#496c5a')
    [void](Add-Text $slide 'Previsioni energetiche e valutazione dei modelli su dati reali della zona Sud.' 42 245 450 100 24)
    $line=$slide.Shapes.AddShape(1,42,356,822,2)
    $line.Line.Visible=0
    $line.Fill.ForeColor.RGB=Convert-Color '#b78b40'
    [void](Add-Text $slide 'EMAIL' 42 386 95 19 10 $true '#496c5a')
    $mail=Add-Text $slide $Email 42 411 405 28 18
    $mail.ActionSettings(1).Hyperlink.Address='mailto:'+$Email
    [void](Add-Text $slide 'GITHUB' 485 386 95 19 10 $true '#496c5a')
    $profile=Add-Text $slide $GitHubUrl 485 411 420 28 16
    $profile.ActionSettings(1).Hyperlink.Address=$GitHubUrl
    $repo=Add-Text $slide 'Codice, metodo e risultati: SolarWindCast' 42 463 800 26 16 $true '#087e8b'
    $repo.ActionSettings(1).Hyperlink.Address=$RepositoryUrl
    [void](Add-Text $slide 'Contatti' 36 517 600 15 9 $false '#496c5a')
    [void](Add-Text $slide '13 / 13' 865 514 60 18 11 $true)
    $slide.NotesPage.Shapes.Placeholders(2).TextFrame.TextRange.Text='Autore: '+$PresenterName+'. Email confermata dall utente: '+$Email+'. Profilo: '+$GitHubUrl+'. Repository: '+$RepositoryUrl+'. Sfondo illustrativo generato con imagegen, come nelle slide precedenti. Nessuna distribuzione Azure dichiarata.'
    } else {
        $slide=$null
        foreach($candidate in $deck.Slides) {
            foreach($shape in $candidate.Shapes) {
                if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1 -and $shape.TextFrame.TextRange.Text -eq $Email) {
                    $slide=$candidate
                }
            }
        }
        if($null -eq $slide){throw 'Slide autore non trovata: nessuna modifica salvata.'}
    }
    if($PortraitPath) {
        $portrait=(Get-Item -LiteralPath $PortraitPath).FullName
        foreach($shape in $slide.Shapes) {
            if($shape.Name -eq 'PresenterPortrait'){$shape.Delete()}
        }
        $picture=$slide.Shapes.AddPicture($portrait,0,-1,688,109,-1,-1)
        $picture.Name='PresenterPortrait'
        $picture.AlternativeText='Ritratto di '+$PresenterName+', fornito dall autore.'
        $picture.LockAspectRatio=-1
        $picture.Width=220
        if($picture.Height -gt 220){$picture.Height=220}
        foreach($shape in $slide.Shapes) {
            if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                if($shape.TextFrame.TextRange.Text -eq $PresenterName){$shape.Width=610;$shape.TextFrame.TextRange.Font.Size=40}
                if($shape.TextFrame.TextRange.Text -eq 'Autore del progetto SolarWindCast'){$shape.Width=610}
            }
        }
    }
    $slide.MoveTo(1)
    for($i=1;$i -le 13;$i++) {
        foreach($shape in $deck.Slides.Item($i).Shapes) {
            if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                if($shape.TextFrame.TextRange.Text -match '^\d+ / (12|13)$'){$shape.TextFrame.TextRange.Text="$i / 13"}
            }
        }
    }
    $deck.SaveCopyAs($OutputPath,24)
} finally {
    if($null -ne $deck){$deck.Saved=-1;$deck.Close();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($deck)}
    if($initialCount -eq 0 -and $app.Presentations.Count -eq 0){$app.Quit()}
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}
Write-Output 'Copia con tredici slide creata; sorgente invariata.'
