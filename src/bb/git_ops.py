import subprocess
import sys
from datetime import datetime, timezone


def _run(args: list[str], git_dir: str, input: str | None = None) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=git_dir,
        input=input,
    )
    if result.returncode != 0:
        print(f'error: git command failed: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def write_blob(git_dir: str, content: str) -> str:
    return _run(['git', 'hash-object', '-w', '--stdin'], git_dir, input=content)


def _make_tree(git_dir: str, blob_sha: str, name: str) -> str:
    return _run(['git', 'mktree'], git_dir, input=f'100644 blob {blob_sha}\t{name}\n')


def _commit_message(uuid: str, version: int, act: str, extra: dict | None = None) -> str:
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    msg = f'concept:{uuid}\nversion: {version}\nact: {act}\ntimestamp: {ts}'
    for k, v in (extra or {}).items():
        msg += f'\n{k}: {v}'
    return msg


def resolve_uuid(git_dir: str, prefix: str) -> str | None:
    """Resolve a UUID prefix to a full UUID. Returns None if no match or ambiguous."""
    result = subprocess.run(
        ['git', 'for-each-ref', '--format=%(refname:short)', 'refs/bb/concepts/'],
        capture_output=True,
        text=True,
        cwd=git_dir,
    )
    matches = [
        name.split('/')[-1]
        for name in result.stdout.splitlines()
        if name.split('/')[-1].startswith(prefix)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def concept_exists(git_dir: str, uuid: str) -> bool:
    result = subprocess.run(
        ['git', 'rev-parse', '--verify', f'refs/bb/concepts/{uuid}'],
        capture_output=True,
        cwd=git_dir,
    )
    return result.returncode == 0


def write_genesis_commit(
    git_dir: str, uuid: str, content: str,
    source_uuid: str | None = None, source_version: int | None = None,
) -> tuple[str, str]:
    """Returns (commit_sha, blob_sha)."""
    blob_sha = write_blob(git_dir, content)
    tree_sha = _make_tree(git_dir, blob_sha, uuid)
    act = 'branch' if source_uuid else 'genesis'
    extra = {'source': source_uuid, 'source_version': source_version} if source_uuid else None
    msg = _commit_message(uuid, 1, act, extra)
    commit_sha = _run(['git', 'commit-tree', tree_sha, '-m', msg], git_dir)
    _run(['git', 'update-ref', f'refs/bb/concepts/{uuid}', commit_sha], git_dir)
    return commit_sha, blob_sha


def write_new_version_commit(git_dir: str, uuid: str, content: str) -> tuple[str, str, int]:
    """Returns (commit_sha, blob_sha, version)."""
    parent_sha = _run(['git', 'rev-parse', f'refs/bb/concepts/{uuid}'], git_dir)
    parent_msg = _run(['git', 'log', '-1', '--format=%B', parent_sha], git_dir)
    version = 1
    for line in parent_msg.splitlines():
        if line.startswith('version:'):
            try:
                version = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
    version += 1
    blob_sha = write_blob(git_dir, content)
    tree_sha = _make_tree(git_dir, blob_sha, uuid)
    msg = _commit_message(uuid, version, 'recordVersion')
    commit_sha = _run(
        ['git', 'commit-tree', tree_sha, '-p', parent_sha, '-m', msg], git_dir
    )
    _run(['git', 'update-ref', f'refs/bb/concepts/{uuid}', commit_sha], git_dir)
    return commit_sha, blob_sha, version


def _parse_version_from_msg(msg: str) -> int:
    for line in msg.splitlines():
        if line.startswith('version:'):
            try:
                return int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
    return 1


def read_concept(git_dir: str, uuid: str) -> tuple[str, str, int]:
    """Returns (content, blob_sha, version) for the latest version."""
    commit_sha = _run(['git', 'rev-parse', f'refs/bb/concepts/{uuid}'], git_dir)
    blob_sha = _run(['git', 'rev-parse', f'{commit_sha}:{uuid}'], git_dir)
    content = _run(['git', 'cat-file', 'blob', blob_sha], git_dir)
    msg = _run(['git', 'log', '-1', '--format=%B', commit_sha], git_dir)
    return content, blob_sha, _parse_version_from_msg(msg)


def _parse_source_from_msg(msg: str) -> tuple[str | None, int | None]:
    source_uuid = None
    source_version = None
    for line in msg.splitlines():
        if line.startswith('source:'):
            source_uuid = line.split(':', 1)[1].strip()
        elif line.startswith('source_version:'):
            try:
                source_version = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
    return source_uuid, source_version


def _parse_absorbed_from_msg(msg: str) -> tuple[str | None, int | None]:
    absorbed_uuid = None
    absorbed_version = None
    for line in msg.splitlines():
        if line.startswith('absorbed:'):
            absorbed_uuid = line.split(':', 1)[1].strip()
        elif line.startswith('absorbed_version:'):
            try:
                absorbed_version = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
    return absorbed_uuid, absorbed_version


def write_merge_commit(
    git_dir: str, survivor_uuid: str, content: str, absorbed_uuid: str, absorbed_version: int
) -> tuple[str, str, int]:
    """Write a new version on survivor recording the merge. Returns (commit_sha, blob_sha, version)."""
    parent_sha = _run(['git', 'rev-parse', f'refs/bb/concepts/{survivor_uuid}'], git_dir)
    parent_msg = _run(['git', 'log', '-1', '--format=%B', parent_sha], git_dir)
    version = _parse_version_from_msg(parent_msg) + 1
    blob_sha = write_blob(git_dir, content)
    tree_sha = _make_tree(git_dir, blob_sha, survivor_uuid)
    msg = _commit_message(survivor_uuid, version, 'merge', {
        'absorbed': absorbed_uuid,
        'absorbed_version': absorbed_version,
    })
    commit_sha = _run(['git', 'commit-tree', tree_sha, '-p', parent_sha, '-m', msg], git_dir)
    _run(['git', 'update-ref', f'refs/bb/concepts/{survivor_uuid}', commit_sha], git_dir)
    return commit_sha, blob_sha, version


def write_retire_commit(
    git_dir: str, retired_uuid: str, absorbed_into: str, absorbed_into_version: int
) -> str:
    """Write a retire commit on the retired concept's ref. Returns commit_sha."""
    parent_sha = _run(['git', 'rev-parse', f'refs/bb/concepts/{retired_uuid}'], git_dir)
    parent_msg = _run(['git', 'log', '-1', '--format=%B', parent_sha], git_dir)
    version = _parse_version_from_msg(parent_msg)
    # reuse last blob — content unchanged
    blob_sha = _run(['git', 'rev-parse', f'{parent_sha}:{retired_uuid}'], git_dir)
    tree_sha = _make_tree(git_dir, blob_sha, retired_uuid)
    msg = _commit_message(retired_uuid, version, 'retire', {
        'absorbed_into': absorbed_into,
        'absorbed_into_version': absorbed_into_version,
    })
    commit_sha = _run(['git', 'commit-tree', tree_sha, '-p', parent_sha, '-m', msg], git_dir)
    _run(['git', 'update-ref', f'refs/bb/concepts/{retired_uuid}', commit_sha], git_dir)
    return commit_sha


def read_all_versions(git_dir: str, uuid: str) -> list[dict]:
    """Walk commit chain tip→genesis.
    Returns list of dicts with keys: content, blob_sha, version, source_uuid, source_version.
    Oldest first. source_uuid/source_version only set on the genesis entry if it was a branch.
    """
    commit_sha = _run(['git', 'rev-parse', f'refs/bb/concepts/{uuid}'], git_dir)
    versions = []
    current = commit_sha
    while current:
        msg = _run(['git', 'log', '-1', '--format=%B', current], git_dir)
        blob_sha = _run(['git', 'rev-parse', f'{current}:{uuid}'], git_dir)
        content = _run(['git', 'cat-file', 'blob', blob_sha], git_dir)
        source_uuid, source_version = _parse_source_from_msg(msg)
        absorbed_uuid, absorbed_version = _parse_absorbed_from_msg(msg)
        versions.append({
            'content': content,
            'blob_sha': blob_sha,
            'version': _parse_version_from_msg(msg),
            'source_uuid': source_uuid,
            'source_version': source_version,
            'absorbed_uuid': absorbed_uuid,
            'absorbed_version': absorbed_version,
        })
        parent = subprocess.run(
            ['git', 'rev-parse', f'{current}^'],
            capture_output=True, text=True, cwd=git_dir,
        )
        if parent.returncode != 0:
            break
        current = parent.stdout.strip()
    versions.reverse()  # oldest first
    return versions
