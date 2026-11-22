"""Audit monthly sample availability and synthetic gradients without fitting or changing weights."""

import argparse
import json
import time
from hashlib import sha256
from html import escape
from pathlib import Path

import pandas as pd
import torch
import yaml

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.load_experiment import monthly_frame
from solarwindcast.monthly_experiment import check_frozen_protocol
from solarwindcast.monthly_forecasting import MonthlyTimestral
from solarwindcast.monthly_protocol import fold_preview, load_monthly_targets


def development_audit(months: pd.DataFrame, periods: dict[str, str],
                       protocol: dict[str, object], validation_lengths: list[int]) -> dict[str, object]:
    """Count only development origins; purge training labels unavailable at first validation issue."""
    start = pd.Period(periods["development_start_utc"][:7], freq="M")
    stop = pd.Period(periods["test_start_utc"][:7], freq="M")
    development = months.loc[(months.index >= start) & (months.index < stop)].copy()
    folds = fold_preview(development, periods["development_start_utc"], periods["test_start_utc"], protocol)
    usable = [fold for fold in folds if fold["scorable_without_model_run"]]
    examples = []
    for count in validation_lengths:
        if not isinstance(count, int) or isinstance(count, bool) or count < 1 or count >= len(usable):
            raise ValueError("Durata illustrativa di validazione non valida.")
        validation = usable[-count:]
        first = pd.Period(validation[0]["target_month"], freq="M")
        cutoff = first - protocol["unavailable_recent_months"] - 1
        train = [fold["target_month"] for fold in usable if pd.Period(fold["target_month"], freq="M") <= cutoff]
        purged = [fold["target_month"] for fold in usable[:-count] if pd.Period(fold["target_month"], freq="M") > cutoff]
        examples.append({"illustrative_only": True, "validation_months": [fold["target_month"] for fold in validation],
            "training_months": train, "purged_months": purged, "training_labels_available_through": str(cutoff)})
    return {"development_months": len(development), "complete_months": int(development.complete.sum()),
        "usable_origins": len(usable), "origin_months": [fold["target_month"] for fold in usable],
        "split_examples": examples, "overlapping_contexts_not_independent": True}


def state_digest(model: torch.nn.Module) -> str:
    """Fingerprint all model tensors to demonstrate absence of an optimization update."""
    digest = sha256()
    for name, tensor in model.state_dict().items():
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def synthetic_gradient_probe(backend: object, context_months: int, horizon: int,
                             variant: str) -> dict[str, object]:
    """Check a pinned private differentiable path against public inference; no optimizer or real target."""
    if variant not in ("target_only", "known_calendar") or horizon != 2:
        raise ValueError("La verifica supporta il protocollo a due passi mensili.")
    device = backend.device
    phase = torch.arange(context_months, device=device, dtype=torch.float32)
    context = (100 + 20 * torch.sin(phase * (2 * torch.pi / 12)) + phase).reshape(1, 1, -1)
    context[..., context_months // 3] = float("nan")
    known = None
    if variant == "known_calendar":
        calendar = torch.arange(context_months + horizon, device=device, dtype=torch.float32) * (2 * torch.pi / 12)
        known = torch.stack((calendar.sin(), calendar.cos()))[None]
    before = state_digest(backend.model)
    original_flags = {name: value.requires_grad for name, value in backend.model.named_parameters()}
    trainable = []
    for name, value in backend.model.named_parameters():
        value.requires_grad_(name.startswith("head."))
        if value.requires_grad:
            trainable.append(value)
    started = time.perf_counter()
    try:
        public = backend.forecast(context, horizon, known_covariates=known,
            symmetric_averaging=False, clip_nonnegative=False).quantiles.detach().clone()
        mask = torch.isfinite(context)
        inputs = torch.where(mask, context, torch.zeros_like(context))
        with torch.enable_grad():
            raw = backend._forecast_raw(inputs, mask, horizon, known_covariates=known)
            if raw.shape != public.shape or not torch.allclose(raw.detach(), public, rtol=1e-5, atol=1e-5):
                raise ValueError("Percorso differenziabile diverso dall'inferenza pubblica.")
            # One synthetic final-month label only; the intervening month never enters the loss.
            target = raw.new_tensor(125.)
            error = target - raw[..., -1, :]
            levels = raw.new_tensor(backend.quantile_levels)
            loss = torch.maximum(levels * error, (levels - 1) * error).mean()
            gradients = torch.autograd.grad(loss, trainable)
        finite = all(bool(torch.isfinite(gradient).all()) for gradient in gradients)
        norm = float(sum(gradient.double().square().sum() for gradient in gradients).sqrt())
        if not finite or norm <= 0 or not torch.isfinite(loss):
            raise ValueError("Gradiente assente, nullo o non finito.")
    finally:
        for name, value in backend.model.named_parameters():
            value.requires_grad_(original_flags[name])
    after = state_digest(backend.model)
    if after != before:
        raise ValueError("La prova ha modificato lo stato dei pesi.")
    return {"variant": variant, "public_private_agree": True, "finite_nonzero_gradients": True,
        "gradient_norm": norm, "synthetic_loss_not_accuracy": float(loss.detach()),
        "elapsed_seconds_not_benchmark": time.perf_counter() - started,
        "state_sha256_before": before, "state_sha256_after": after, "optimizer_steps": 0,
        "output_shape": list(raw.shape), "scope_probed": "head_only", "device": str(device),
        "training_mode_tested": "eval with gradients; dropout/train-mode not validated"}


def run_audit(config: dict[str, object], root: Path) -> dict[str, object]:
    """Use verified local weights, audited development data and tiny CPU-only synthetic backward passes."""
    settings = config["finetuning_feasibility"]
    if settings["authorized"] is not True or settings["real_training_authorized"] is not False or settings["device"] != "cpu":
        raise RuntimeError("Solo audit autorizzato su CPU; nessun training reale.")
    output = root / settings["output_directory"]
    if output.exists():
        raise FileExistsError("Serve una nuova directory per l'audit.")
    frozen = check_frozen_protocol(config, root)
    protocol = config["monthly_protocol"]
    months = load_monthly_targets(root / config["monthly_inspection"]["prepared_directory"], protocol["calendar_timezone"], protocol["wind_components"])
    extension = root / config["step12"]["output_directory"]
    manifest = json.loads((extension / "manifest.json").read_text())
    for name, digest in manifest["files_sha256"].items():
        path = (extension / name).resolve()
        if not path.is_relative_to(extension.resolve()) or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Risultati dello Step 12 modificati.")
    for target in config["step12"]["targets"]:
        dataset = TimeSeriesDataset(pd.read_parquet(extension / (target + ".parquet")),
            DatasetSpec(target, config["data"]["frequency"], (), (), (), "verified step12 snapshot"))
        months[target] = monthly_frame(dataset, protocol["calendar_timezone"])
    data = {target: development_audit(frame, frozen["evaluation_periods"], protocol,
        settings["illustrative_validation_months"]) for target, frame in months.items()}
    torch.set_num_threads(settings["cpu_threads"])
    models = {}
    for specification in protocol["models"]:
        if specification["size"] not in settings["model_sizes"]:
            continue
        adapter = MonthlyTimestral(protocol, specification)
        adapter.load()
        backend = adapter.backend
        total = sum(parameter.numel() for parameter in backend.model.parameters())
        head = sum(parameter.numel() for name, parameter in backend.model.named_parameters() if name.startswith("head."))
        probes = [synthetic_gradient_probe(backend, protocol["context_months"], protocol["prediction_length_months"], variant)
                  for variant in protocol["model_variants"]]
        models[adapter.size] = {"provenance": adapter.provenance, "total_parameters": total, "head_parameters": head,
            "head_fraction": head / total, "fp32_weight_bytes": total * 4,
            "full_adam_fp32_lower_bound_bytes": total * 16,
            "head_adam_fp32_lower_bound_bytes": total * 4 + head * 12,
            "memory_estimate_excludes_activations_workspaces_and_overheads": True, "probes": probes}
        print(f"{adapter.size}: gradienti sintetici verificati; pesi invariati", flush=True)
        del backend, adapter
    if set(models) != set(settings["model_sizes"]):
        raise ValueError("Taglia richiesta non presente nel protocollo.")
    hardware = {"cuda_available": torch.cuda.is_available(), "gpu_training_tested": False}
    if hardware["cuda_available"]:
        properties = torch.cuda.get_device_properties(0)
        hardware.update(gpu_name=properties.name, gpu_total_bytes=properties.total_memory)
    result = {"kind": "feasibility_audit_not_training_or_accuracy", "settings": settings,
        "data": data, "models": models, "hardware": hardware, "torch_version": torch.__version__,
        "protocol_sha256": frozen["settings_sha256"],
        "production_manifest_sha256": frozen["source_prepared_manifest_sha256"],
        "step12_manifest_sha256": sha256((extension / "manifest.json").read_bytes()).hexdigest(),
        "verdict": "technically_feasible_head_gradients_monthly_data_insufficient_for_robust_finetuning_claims",
        "real_training_started": False, "test_used_for_selection": False,
        "test_already_inspected_prior_to_audit": True}
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    rows = ''.join(f'<tr><td>{escape(target)}</td><td>{entry["complete_months"]}/{entry["development_months"]}</td>'
        f'<td>{entry["usable_origins"]}</td><td>' + '; '.join(f'{len(split["training_months"])} training + {len(split["purged_months"])} escluso + {len(split["validation_months"])} validazione'
        for split in entry["split_examples"]) + '</td></tr>' for target, entry in data.items())
    model_rows = ''.join(f'<tr><td>{size}</td><td>{entry["total_parameters"]:,}</td><td>{entry["head_parameters"]:,}</td>'
        f'<td>{entry["head_fraction"]:.1%}</td><td>Verificati, nessun aggiornamento</td></tr>' for size, entry in models.items())
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Fattibilità del fine tuning</title><style>body{{font:16px/1.6 system-ui;background:#f2f6f7;color:#16313e;margin:0}}main{{max-width:1100px;margin:auto;padding:24px}}
header,section{{padding:25px;border-radius:16px;margin:20px 0;background:white}}header{{background:#16313e;color:white}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:720px}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #ddd}}.note{{padding:18px;background:#fff0d7}}</style></head>
<body><main><header><h1>Fine tuning: possibile tecnicamente, dati molto pochi</h1><p>Timestral 5M e 28M · Verifica preliminare · Nessun modello addestrato sui dati reali</p></header>
<p class="note">Gradienti sintetici verificati per entrambe le taglie, senza aggiornare i pesi. Non è una prova di miglioramento delle previsioni.</p>
<section><h2>Quanti esempi possiamo usare?</h2><div class="scroll"><table><thead><tr><th>Target</th><th>Mesi sviluppo completi</th><th>Origini utilizzabili</th><th>Divisioni illustrative, non approvate</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Le finestre condividono quasi tutto il contesto. Inoltre il residuo deriva da carico e produzione: quattro target non equivalgono a quattro raccolte indipendenti.</p>
<p>Le etichette di training devono essere note prima della prima emissione di validazione: il mese ancora in corso è escluso anche dalla selezione dei dati di addestramento.</p></section>
<section><h2>Che cosa è stato verificato sui modelli?</h2><div class="scroll"><table><thead><tr><th>Taglia</th><th>Parametri totali</th><th>Parametri testa quantili</th><th>Quota</th><th>Gradienti</th></tr></thead><tbody>{model_rows}</tbody></table></div>
<p>Prova su CPU, serie sintetica con un mancante, varianti solo serie e calendario noto. Il percorso interno produce gli stessi quantili dell'API pubblica, con gradienti finiti e non nulli sulla testa. Zero passi di ottimizzazione; hash dello stato invariati.</p>
<p>La testa non è necessariamente piccola rispetto ai nostri esempi. Il percorso usa API interne della revisione bloccata e richiederebbe manutenzione, checkpoint, test di ricaricamento e una strategia di regolarizzazione prima del training reale.</p>
<p>Le stime di memoria nel JSON sono limiti inferiori teorici FP32, senza attivazioni o overhead. Nessun training GPU è stato misurato; il rilevamento della scheda non certifica che una configurazione di addestramento ci stia.</p></section>
<section><h2>Decisione proposta</h2><p>Non partire con un fine tuning completo: con 11 origini mensili lo scarso numero di esempi è il limite principale. Un piccolo adattamento resta un esperimento esplorativo, con forte rischio di sovradattamento.</p>
<p>Prima del training scegliere insieme un protocollo: adattamento molto limitato e regolarizzato oppure più storico/serie coerenti, con nuova autorizzazione agli eventuali download. Allenare sulle ore non garantisce automaticamente un miglioramento mensile.</p>
<p>I due anni di test sono già stati esaminati: un nuovo confronto sugli stessi mesi va dichiarato esplorativo. Non si possono rendere nuovamente indipendenti semplicemente cambiando nome al test.</p>
<p>Fonti: <a href="https://github.com/mistralai/timestral">repository di inferenza</a>, <a href="https://huggingface.co/mistralai/Timestral-28M">modello 28M</a>, <a href="https://mistral.ai/news/timestral/">Mistral: adattamento tramite Forge</a>.
Licenze e revisioni restano quelle documentate nel progetto; nessun servizio esterno di training utilizzato.</p></section></main></body></html>'''
    (output / "presentazione.html").write_text(html, encoding="utf-8")
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in output.iterdir()}
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")
    return result


def main() -> None:
    """Execute only the explicitly authorized feasibility audit, using local cached checkpoints."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    run_audit(config, args.config.resolve().parent.parent)
    print(config["finetuning_feasibility"]["output_directory"] + "/presentazione.html")


if __name__ == "__main__":
    main()
