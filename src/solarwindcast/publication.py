"""Audit an explicit public file set and stage an offline static site without publishing it."""

import argparse
import json
import re
import subprocess
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from shutil import copyfile
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile

import yaml

ROOT_FILES = {'.gitignore', '.gitattributes', '.env.example', 'README.md',
              'pyproject.toml', 'requirements.txt', 'constraints.txt', 'pytest.ini', 'LICENSE', 'NOTICE.md'}
PRIVATE_FILES = {'AGENTS.md', 'PROGRESS.md'} | {
    f'docs/{name}.{extension}'
    for name in ('cleanup_20261121', 'github_publication_20261122',
                 'portfolio_site_update_20261122', 'readme_review_20261122',
                 'release_checks_20261122', 'release_setup_validation',
                 'release_v1_checks_20261123')
    for extension in ('html', 'json')
}
PUBLIC_DIRS = {'.github', 'configs', 'docs', 'scripts', 'src', 'tests'}
GENERATED = {'__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache', 'build', 'dist'}
SECRET_PATTERN = re.compile(rb'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|hf_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{35,})')


def contains_credential(data: bytes, known: list[bytes], depth: int = 0) -> bool:
    """Inspect plain bytes and embedded Office XML/workbooks without revealing matched values."""
    if SECRET_PATTERN.search(data) or any(secret in data for secret in known):
        return True
    if depth >= 2 or not data.startswith(b'PK\x03\x04'):
        return False
    try:
        with ZipFile(BytesIO(data)) as package:
            if sum(p.file_size for p in package.infolist()) > 32*1024*1024:
                raise ValueError('Archivio pubblico troppo grande per il controllo.')
            return any(contains_credential(package.read(p), known, depth+1)
                       for p in package.infolist() if not p.is_dir())
    except BadZipFile:
        return False


def public_files(root: Path) -> list[Path]:
    """Enumerate intended repository files without traversing environments, datasets or archives."""
    result = [root/name for name in ROOT_FILES if (root/name).is_file()]
    result += [root/name/'README.md' for name in ('data', 'reports', 'archive')
               if (root/name/'README.md').is_file()]
    for directory in PUBLIC_DIRS:
        if not (root/directory).is_dir():
            continue
        for path in (root/directory).rglob('*'):
            relative = path.relative_to(root)
            if (relative.as_posix() in PRIVATE_FILES
                    or any(p in GENERATED or p.endswith('.egg-info') for p in relative.parts)
                    or path.suffix in {'.pyc', '.pyo'} or not path.is_file()):
                continue
            result.append(path)
    return sorted(set(result))


def audit(root: Path, require_license: bool = False) -> dict:
    """Check public files for credentials and frozen artifacts; report findings without secret text."""
    files = public_files(root)
    findings = []
    if (root/'.git').exists():
        inventory = subprocess.run(['git', '-c', f'safe.directory={root.resolve()}', '-C', str(root.resolve()),
                                    'ls-files', '-z'], capture_output=True, check=False)
        if inventory.returncode:
            findings.append({'file': '.git', 'rule': 'tracked_inventory_unavailable'})
        else:
            allowed = {p.relative_to(root).as_posix() for p in files}
            for name in inventory.stdout.decode('utf-8', errors='surrogateescape').split('\0'):
                if name and name not in allowed:
                    findings.append({'file': name, 'rule': 'unexpected_tracked_file'})
    known_secrets = []
    local_env = root/'.env'
    if local_env.is_file():
        for line in local_env.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                value = line.split('=', 1)[1].strip().strip('\"\'')
                if len(value) >= 12:
                    known_secrets.append(value.encode('utf-8'))
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            findings.append({'file': relative, 'rule': 'external_path_or_symlink'})
            continue
        data = path.read_bytes()
        if path.name.startswith('.env') and path.name != '.env.example':
            findings.append({'file': relative, 'rule': 'environment_file'})
        if contains_credential(data, known_secrets):
            findings.append({'file': relative, 'rule': 'possible_credential'})
    example = root/'.env.example'
    if not example.is_file() or example.read_text(encoding='utf-8-sig').strip() != 'ENTSOE_API_KEY=':
        findings.append({'file': '.env.example', 'rule': 'example_must_have_one_empty_key'})
    config = yaml.safe_load((root/'configs/project.yaml').read_text(encoding='utf-8'))
    frozen = config['release_v1']['frozen_powerpoint_sha256']
    ppt = root/'docs/portfolio/PresentazioneSolarWindCast.pptx'
    if not ppt.is_file() or sha256(ppt.read_bytes()).hexdigest() != frozen:
        findings.append({'file': 'docs/portfolio/PresentazioneSolarWindCast.pptx', 'rule': 'frozen_powerpoint_changed'})
    portfolio = root/'docs/portfolio'
    manifest = json.loads((portfolio/'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files_sha256'].items():
        path = portfolio/name
        if (not path.resolve().is_relative_to(portfolio.resolve()) or not path.is_file()
                or sha256(path.read_bytes()).hexdigest() != expected):
            findings.append({'file': 'docs/portfolio/'+name, 'rule': 'manifest_mismatch'})
    license_ready = (root/'LICENSE').is_file()
    if require_license and not license_ready:
        findings.append({'file': 'LICENSE', 'rule': 'project_license_missing'})
    return {'status': 'pass' if not findings else 'fail', 'files_checked': len(files),
            'bytes_checked': sum(p.stat().st_size for p in files), 'findings': findings,
            'project_license_present': license_ready, 'powerpoint_frozen': not any(
                f['rule'] == 'frozen_powerpoint_changed' for f in findings),
            'claim_boundary': 'Public allowlist and credential patterns checked; not a proof that every possible secret is detectable.'}


class Links(HTMLParser):
    """Read local references without executing page code."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if value and key in {'href', 'src'}:
                self.links.append(value)
            if key == 'id' and value:
                self.ids.add(value)


def validate_site(folder: Path) -> list[str]:
    """Reject missing, escaping or unsafe links in a staged self-contained site."""
    failures = []
    for page in folder.rglob('*.html'):
        parsed = Links()
        parsed.feed(page.read_text(encoding='utf-8'))
        for link in parsed.links:
            parts = urlsplit(link)
            if parts.scheme in {'https', 'http', 'mailto', 'data'}:
                continue
            if parts.scheme or parts.netloc:
                failures.append(page.name+': unsafe link scheme')
                continue
            target = (page.parent/unquote(parts.path)).resolve() if parts.path else page.resolve()
            if not target.is_relative_to(folder.resolve()) or not target.is_file():
                failures.append(page.name+': '+link)
                continue
            if parts.fragment and target.suffix == '.html':
                target_parser = Links()
                target_parser.feed(target.read_text(encoding='utf-8'))
                if parts.fragment not in target_parser.ids:
                    failures.append(page.name+': missing anchor '+link)
    return failures


def guide(repository_url: str) -> str:
    """Build a short public guide without local machine paths or unavailable source links."""
    if repository_url and not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?', repository_url):
        raise ValueError('URL repository non valido: usare https://github.com/owner/repository.')
    repository = ('<p><a href="'+escape(repository_url)+'">Codice e documentazione su GitHub</a></p>'
                  if repository_url else '<p>Il collegamento al repository sarà aggiunto alla pubblicazione.</p>')
    return '''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Guida e provenienza</title><style>body{font:18px/1.6 system-ui;max-width:900px;margin:40px auto;padding:20px;color:#193f36;background:#f8f6ef}pre{white-space:pre-wrap;padding:20px;background:white}a{color:#087e8b}</style>
<h1>SolarWindCast: codice, metodo e provenienza</h1>''' + repository + '''
<p><a href="index.html">12 slide</a> · <a href="details.html#complete">Tutti i confronti</a> · <a href="PresentazioneSolarWindCast.pptx">PowerPoint</a> · <a href="metrics.json">Metriche JSON</a> · <a href="project.yaml">Configurazione</a></p>
<h2 id="setup">Prova riproducibile</h2><p>La demo sintetica usa baseline, non richiede token o pesi durante l'esecuzione. Setup dettagliato e scelta CPU sono documentati nel repository. I dati originali e i pesi non fanno parte di questo sito.</p>
<pre>.\\scripts\\check.ps1
.\\.venv\\Scripts\\python.exe -B -m solarwindcast.backtest_demo --config configs/project.yaml --profile step8 --baselines-only --output reports/demo_nuova</pre>
<h2>Risultati e limiti</h2><p>Valutazione retrospettiva su dati revisionati della zona Sud, non della sola Puglia. Periodi già esaminati, ore correlate e ritardi assunti; nessuna superiorità generale o beneficio economico certificato. Le metriche misurano gli esperimenti SolarWindCast, non i benchmark dichiarati da Mistral.</p>
<h2>Fonte dei dati</h2><p>Fonte: <a href="https://transparency.entsoe.eu/">ENTSO-E Transparency Platform</a>. Le statistiche pubblicate sono risultati aggregati del backtest. Non sono redistribuite osservazioni o serie di previsioni per singola ora/mese. Le condizioni dei dati sorgente restano separate dalla licenza del codice.</p>
<h2>Timestral e immagini</h2><p>Codice upstream Timestral: Apache-2.0. Pesi: Modified MIT separata; il testo delle revisioni usate limita i diritti quando il fatturato mensile globale consolidato della società o del datore di lavoro supera 20 milioni di dollari nel mese precedente. I pesi non sono inclusi.</p>
<p><a href="licenses/Timestral-5M_LICENSE.txt">Licenza pesi 5M</a> · <a href="licenses/Timestral-28M_LICENSE.txt">Licenza pesi 28M</a></p>
<p>Mappa amministrativa derivata da Openpolis, CC BY 4.0, semplificata e colorata: non rappresenta i confini delle zone elettriche. Sfondo di sole/turbine generato con imagegen: illustrazione decorativa, non fotografia di un sito reale. Pittogrammi delle fonti originali, senza affiliazione ai servizi citati.</p>
<p><a href="https://github.com/openpolis/geojson-italy">Fonte geografica</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a></p></html>'''


def stage_site(root: Path, output: Path, repository_url: str = '') -> dict:
    """Copy only approved public assets and repair links for a website hosted at its own root."""
    if output.exists():
        raise FileExistsError('Destinazione del sito già presente.')
    guide_html = guide(repository_url)
    output.mkdir(parents=True)
    source = root/'docs/portfolio'
    for name in ('index.html', 'details.html', 'metrics.json', 'PresentazioneSolarWindCast.pptx', 'staticwebapp.config.json'):
        copyfile(source/name, output/name)
    for name in ('index.html', 'details.html'):
        path = output/name
        text = path.read_text(encoding='utf-8')
        for old, new in {'../../README.md': 'guide.html', '../../docs/setup.md': 'guide.html#setup',
                         '../../configs/project.yaml': 'project.yaml'}.items():
            text = text.replace(old, new)
        path.write_text(text, encoding='utf-8')
    (output/'guide.html').write_text(guide_html, encoding='utf-8')
    copyfile(root/'configs/project.yaml', output/'project.yaml')
    (output/'licenses').mkdir()
    for size, revision in [('5M', 'bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f'),
                           ('28M', '49b26409ac87b5935539a5d8ffe7f397b720db47')]:
        copyfile(root/f'docs/licenses/Timestral-{size}_{revision}_LICENSE.txt', output/f'licenses/Timestral-{size}_LICENSE.txt')
    broken = validate_site(output)
    if broken:
        raise ValueError('Collegamenti non validi: '+str(broken))
    manifest = {p.relative_to(output).as_posix(): sha256(p.read_bytes()).hexdigest()
                for p in output.rglob('*') if p.is_file()}
    (output/'manifest.json').write_text(json.dumps({'files_sha256': manifest}, indent=2)+'\n', encoding='utf-8')
    return {'files': len(manifest)+1, 'bytes': sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
            'broken_links': 0, 'published': False}


def main() -> None:
    """Run the release audit and optionally stage a new static site, never publish automatically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--require-license', action='store_true')
    parser.add_argument('--site-output', type=Path)
    parser.add_argument('--source-repo-url', default='')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = audit(args.root.resolve(), args.require_license)
    if report['status'] == 'pass' and args.site_output:
        report['site'] = stage_site(args.root.resolve(), args.site_output, args.source_repo_url)
    if args.report:
        if args.report.exists():
            raise FileExistsError('Resoconto già presente.')
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    if report['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
