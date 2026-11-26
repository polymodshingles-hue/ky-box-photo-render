"""Shared filesystem contracts for the local photo workhorse."""
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]
ORIGINALS = ROOT / 'PHOTOS/1-ORIGINALS'
DONE = ROOT / 'PHOTOS/2-DONE'
WORK = ROOT / '_work'
META = WORK / 'meta'
PROCESSED = WORK / 'processed'
REPORT = PROCESSED / 'report.json'
ROLES = ('hero', 'front', 'back', 'side', 'open', 'insert', 'finish', 'set')
VARIANTS = {'.jpg': ('JPEG', (2400, 2400)), '.webp': ('WEBP', (2400, 2400)),
            '-cut.png': ('PNG', (2400, 2400)), '-wide.jpg': ('JPEG', (3200, 1800))}
VIDEOS = {'.mov', '.mp4', '.m4v', '.avi', '.webm'}

def read_json(path, default=None):
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding='utf-8'))

def checked(path):
    """Reject links and junctions below the checkout before writing or promoting."""
    path = Path(path).absolute()
    path.relative_to(ROOT)
    if path.resolve() != path:
        raise ValueError(f'Unexpected redirected path: {path}')
    return path

def slug(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value) or PureWindowsPath(value).is_reserved():
        raise ValueError(f'Invalid project name: {value!r}')
    return value

def manifest(project):
    name = slug(project)
    path = META / (name + '.json')
    m = read_json(path)
    if m.get('slug') != name:
        raise ValueError(f'Project name differs from {path.name}')
    if m.get('brand_ok') is not None and type(m['brand_ok']) is not bool:
        raise ValueError(f'{name}: brand_ok must be true, false or null')
    outputs = set()
    for photo in m['photos']:
        filename = photo['file']
        if (not re.fullmatch(r'[^<>:"/\\|?*\x00-\x1f]+\.jpg', filename, re.I)
                or PureWindowsPath(filename).is_reserved()):
            raise ValueError(f'Invalid source filename: {filename!r}')
        if photo.get('role') is not None and photo['role'] not in ROLES:
            raise ValueError(f'Unknown role for {filename}')
        for ext in VARIANTS:
            output = Path(filename).stem.casefold() + ext
            if output in outputs:
                raise ValueError(f'{name}: duplicate output {output}')
            outputs.add(output)
    return m

def projects(selected):
    entries = ORIGINALS.iterdir() if ORIGINALS.is_dir() else ()
    names = {p.name for p in entries if p.is_dir() and
             p.name not in ('ready', 'processed', 'blue-test') and not p.name.startswith(('_', '.'))}
    if selected and set(selected) - names:
        raise ValueError(f'Missing project folders: {sorted(set(selected) - names)}')
    return sorted(slug(p) for p in (set(selected) or names))

def digest(path):
    with Path(path).open('rb') as f:
        h = hashlib.sha256()      # hashlib.file_digest needs Python 3.11+; the workhorse VM runs 3.10
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
        return h.hexdigest()

def atomic_json(path, value):
    path = checked(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            json.dump(value, f, indent=1, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            f.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

@contextmanager
def writer():
    lock = checked(WORK / 'pipeline.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a+b') as f:
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Another local photo stage is running') from exc
        yield

def new_stage(project):
    directory = checked(WORK / 'stage')
    directory.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=slug(project) + '-', dir=directory))

def previous_for(out):
    return checked(WORK / 'previous' / out.parent.name / out.name)

def recover(out):
    out = checked(out)
    previous = previous_for(out)
    if previous.exists() and not out.exists():
        previous.rename(out)

def promote(stage, out):
    out = checked(out)
    checked(stage)
    recover(out)
    previous = previous_for(out)
    previous.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        if previous.exists():
            shutil.rmtree(previous)
        out.rename(previous)
    try:
        stage.rename(out)
    except OSError:
        recover(out)
        raise

def options(project, filename, defaults=None):
    overrides = read_json(ROOT / 'site/tools/overrides.json', {})
    return {**(defaults or {}), **overrides.get(project + '/' + filename, {})}
