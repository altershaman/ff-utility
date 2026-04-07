import json
import os
import subprocess
import sys


def find_git_dir() -> str | None:
    result = subprocess.run(
        ['git', 'rev-parse', '--git-dir'],
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    if result.returncode != 0:
        return None
    git_dir = result.stdout.strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.abspath(git_dir)
    return git_dir


def require_bb(git_dir: str | None) -> str:
    if git_dir is None:
        print('error: not a git repository', file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(os.path.join(git_dir, 'refs', 'bb')):
        print('error: BB not initialized — run ff init', file=sys.stderr)
        sys.exit(1)
    return git_dir


def bb_config_path(git_dir: str) -> str:
    return os.path.join(git_dir, 'bb', 'config')


def read_bb_config(git_dir: str) -> dict:
    path = bb_config_path(git_dir)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def read_global_config() -> dict:
    path = os.path.expanduser('~/.config/ff/config')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _aliases_path(git_dir: str) -> str:
    return os.path.join(git_dir, 'bb', 'aliases.json')


def save_aliases(git_dir: str, aliases: dict[str, str]) -> None:
    with open(_aliases_path(git_dir), 'w') as f:
        json.dump(aliases, f)


def resolve_alias(git_dir: str, value: str) -> str | None:
    path = _aliases_path(git_dir)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        aliases = json.load(f)
    return aliases.get(value)


def resolve_alias_key(git_dir: str, uuid: str) -> str | None:
    """Return the alias key for a given UUID, if one exists in current aliases."""
    path = _aliases_path(git_dir)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        aliases = json.load(f)
    return next((k for k, v in aliases.items() if v == uuid), None)


def resolve_embedding_model(git_dir: str) -> str:
    bb_cfg = read_bb_config(git_dir)
    if bb_cfg.get('embedding_model'):
        return bb_cfg['embedding_model']
    global_cfg = read_global_config()
    if global_cfg.get('embedding_model'):
        return global_cfg['embedding_model']
    return 'nomic-embed-text'
