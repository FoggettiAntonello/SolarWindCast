# Comandi

`check.ps1` esegue pip check, pytest e Ruff con l'interprete `.venv` del progetto.
Non installa pacchetti o usa rete. `-PythonPath` seleziona un altro interprete;
`-CachedTimestral` abilita la piccola prova CPU con pesi già in cache.

Il backtest sintetico è il comando installato `solarwindcast-demo`, alimentato
da `configs/project.yaml`. [Setup e comandi](../docs/setup.md).
L'opzione `--baselines-only` esegue la demo senza pesi, token o rete.
Il percorso equivalente da Python è `python -m solarwindcast.backtest_demo`.
Il comando `python -m solarwindcast.portfolio_report --config configs/project.yaml`
genera una nuova presentazione dalle metriche locali già esistenti, senza modelli;
la destinazione in `release_v1.output_directory` deve essere nuova.
L'archivio conserva provenienza e risultati precedenti, esclusi dalla pubblicazione.

`export_powerpoint.ps1` crea la copia PowerPoint modificabile delle 12 slide,
usando Microsoft PowerPoint/Excel installati localmente. È un comando opzionale,
separato dai test ordinari: [istruzioni](../docs/powerpoint_export.md).
L'outline è estratto dall'HTML dal modulo `solarwindcast.powerpoint_outline`;
il file di destinazione deve essere nuovo.
