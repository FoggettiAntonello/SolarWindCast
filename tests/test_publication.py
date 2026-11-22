"""Synthetic release checks for secret redaction, exclusions and portable website links."""

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
import yaml

from solarwindcast.publication import (
    audit,
    contains_credential,
    guide,
    public_files,
    validate_site,
)


def fixture_root(root: Path) -> None:
    """Create the smallest synthetic public tree without reading project credentials."""
    (root/'configs').mkdir()
    portfolio = root/'docs/portfolio'
    portfolio.mkdir(parents=True)
    (portfolio/'PresentazioneSolarWindCast.pptx').write_bytes(b'synthetic frozen file')
    digest = sha256((portfolio/'PresentazioneSolarWindCast.pptx').read_bytes()).hexdigest()
    (root/'configs/project.yaml').write_text(yaml.safe_dump({'release_v1': {'frozen_powerpoint_sha256': digest}}), encoding='utf-8')
    (portfolio/'manifest.json').write_text(json.dumps({'files_sha256': {'PresentazioneSolarWindCast.pptx': digest}}), encoding='utf-8')
    (root/'.env.example').write_text('ENTSOE_API_KEY=\n', encoding='utf-8')
    (root/'README.md').write_text('Synthetic example', encoding='utf-8')


def test_public_audit_excludes_private_trees_and_redacts_detected_secret(tmp_path: Path) -> None:
    fixture_root(tmp_path)
    secret = 'synthetic_' + 'private_credential_12345'
    (tmp_path/'.env').write_text('ENTSOE_API_KEY='+secret, encoding='utf-8')
    (tmp_path/'data/raw').mkdir(parents=True)
    (tmp_path/'data/raw/private.xml').write_text(secret, encoding='utf-8')
    assert all(p.name != '.env' and 'raw' not in p.parts for p in public_files(tmp_path))
    assert audit(tmp_path)['status'] == 'pass'
    (tmp_path/'README.md').write_text('Accidental leak: '+secret, encoding='utf-8')
    report = audit(tmp_path)
    assert report['status'] == 'fail'
    assert {'file': 'README.md', 'rule': 'possible_credential'} in report['findings']
    assert secret not in str(report)


def test_release_requires_license_and_rejects_changed_frozen_file(tmp_path: Path) -> None:
    fixture_root(tmp_path)
    assert any(f['rule'] == 'project_license_missing' for f in audit(tmp_path, True)['findings'])
    (tmp_path/'docs/portfolio/PresentazioneSolarWindCast.pptx').write_bytes(b'changed')
    assert not audit(tmp_path)['powerpoint_frozen']


def test_secret_in_compressed_office_xml_is_detected(tmp_path: Path) -> None:
    path = tmp_path/'fixture.pptx'
    secret = b'fictional_' + b'credential_in_notes'
    with ZipFile(path, 'w') as package:
        package.writestr('ppt/notesSlides/notesSlide1.xml', b'<notes>'+secret+b'</notes>')
    assert contains_credential(path.read_bytes(), [secret])


def test_audit_blocks_tracked_files_outside_public_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_root(tmp_path)
    (tmp_path/'.git').mkdir()
    monkeypatch.setattr('solarwindcast.publication.subprocess.run',
                        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b'private-backup.zip\0'))
    report = audit(tmp_path)
    assert {'file': 'private-backup.zip', 'rule': 'unexpected_tracked_file'} in report['findings']


def test_site_checks_escape_and_anchor_and_rejects_credential_urls(tmp_path: Path) -> None:
    (tmp_path/'index.html').write_text('<a href="guide.html#setup">Setup</a>', encoding='utf-8')
    (tmp_path/'guide.html').write_text('<h1 id="setup">Setup</h1>', encoding='utf-8')
    assert validate_site(tmp_path) == []
    (tmp_path/'index.html').write_text('<a href="../private.env">bad</a>', encoding='utf-8')
    assert validate_site(tmp_path)
    with pytest.raises(ValueError, match='URL repository'):
        guide('https://github.com/owner/repo?token=never')
