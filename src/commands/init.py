import json
import os
import subprocess
import sys


def _find_git_dir() -> str | None:
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


def _bb_refs_dir(git_dir: str) -> str:
    return os.path.join(git_dir, 'refs', 'bb')


def _bb_config_path(git_dir: str) -> str:
    return os.path.join(git_dir, 'bb', 'config')


def _is_bb_initialized(git_dir: str) -> bool:
    return os.path.isdir(_bb_refs_dir(git_dir))


def _read_bb_config(git_dir: str) -> dict:
    path = _bb_config_path(git_dir)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _write_bb_config(git_dir: str, title: str, description: str) -> None:
    config_dir = os.path.dirname(_bb_config_path(git_dir))
    os.makedirs(config_dir, exist_ok=True)
    with open(_bb_config_path(git_dir), 'w') as f:
        json.dump({'title': title, 'description': description}, f, indent=2)


def _create_bb(git_dir: str, title: str, description: str) -> None:
    os.makedirs(_bb_refs_dir(git_dir), exist_ok=True)
    _write_bb_config(git_dir, title, description)


def _print_bb_initialized(title: str, description: str) -> None:
    parts = ['bb is initialized']
    if title:
        parts.append(title)
    if description:
        parts.append(description)
    print(', '.join(parts) if len(parts) > 1 else parts[0])


def cmd_init() -> None:
    git_dir = _find_git_dir()

    if git_dir is None:
        answer = input(
            'There is no Bounded Belief in this directory. '
            'Initialize git repository? [Y/n] '
        ).strip().lower()
        if answer not in ('', 'y', 'yes'):
            sys.exit(0)
        subprocess.run(['git', 'init'], check=True)
        git_dir = _find_git_dir()

    if _is_bb_initialized(git_dir):
        config = _read_bb_config(git_dir)
        _print_bb_initialized(config.get('title', ''), config.get('description', ''))
        sys.exit(0)

    title = input('BB title (press Enter to skip): ').strip()
    description = input('BB description (press Enter to skip): ').strip()

    _create_bb(git_dir, title, description)
    _print_bb_initialized(title, description)
