#Requires -Version 5.1
<#
.SYNOPSIS
Esegue i controlli locali ripetibili di SolarWindCast.
.DESCRIPTION
Controlla dipendenze, test sintetici e Ruff. Non installa pacchetti, non scarica
dati o modelli e non legge .env. La prova Timestral con pesi richiede lo switch esplicito.
.PARAMETER PythonPath
Interprete da usare. Il valore predefinito e' .venv/Scripts/python.exe del progetto.
.PARAMETER CachedTimestral
Abilita anche la piccola prova sintetica Timestral-5M su CPU, solo da cache locale.
.EXAMPLE
.\scripts\check.ps1
.EXAMPLE
.\scripts\check.ps1 -CachedTimestral
#>
[CmdletBinding()]
param(
    [string]$PythonPath = '',
    [switch]$CachedTimestral
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
}
$selectedPython = (Get-Item -LiteralPath $PythonPath -ErrorAction Stop).FullName
$previousSmokeFlag = [Environment]::GetEnvironmentVariable('SOLARWINDCAST_RUN_CACHED_TIMESTRAL', 'Process')
Push-Location -LiteralPath $projectRoot
try {
    if ($CachedTimestral) {
        $env:SOLARWINDCAST_RUN_CACHED_TIMESTRAL = '1'
    } else {
        $env:SOLARWINDCAST_RUN_CACHED_TIMESTRAL = '0'
    }

    Write-Output 'Controllo dipendenze installate...'
    & $selectedPython -B -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "pip check fallito (codice $LASTEXITCODE)."
    }

    Write-Output 'Esecuzione test...'
    & $selectedPython -B -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) {
        throw "pytest fallito (codice $LASTEXITCODE)."
    }

    Write-Output 'Controllo Ruff...'
    & $selectedPython -B -m ruff check src tests --no-cache
    if ($LASTEXITCODE -ne 0) {
        throw "Ruff fallito (codice $LASTEXITCODE)."
    }
    Write-Output 'Tutti i controlli locali sono superati.'
} finally {
    [Environment]::SetEnvironmentVariable('SOLARWINDCAST_RUN_CACHED_TIMESTRAL', $previousSmokeFlag, 'Process')
    Pop-Location
}
