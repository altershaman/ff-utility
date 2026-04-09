import json
import os
import sys
import uuid as uuid_lib
from datetime import datetime, timezone

from src.bb import common, db, git_ops, ollama_client


def _resolve_content(value: str | None) -> str | None:
    if value is None:
        return None
    if os.path.isfile(value):
        with open(value) as f:
            return f.read()
    return value.encode('raw_unicode_escape').decode('unicode_escape')


def _extract_title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            return stripped.lstrip('#').strip()
    return ''


def _validate_title(title: str) -> None:
    for ch in ('.', ':'):
        if ch in title:
            print(f'error: concept title "{title}" contains reserved character "{ch}" — dots and colons are not allowed in concept names', file=sys.stderr)
            sys.exit(1)


def _excerpt(content: str, title: str, max_chars: int = 200) -> str:
    lines = content.splitlines()
    body_lines = [l for l in lines if not l.strip().startswith('#')]
    body = ' '.join(body_lines).strip()
    return body[:max_chars]


def _short_uuid(u: str) -> str:
    return u[:4]


def _alias_gen():
    letters = 'abcdefghijklmnopqrstuvwxyz'
    i = 0
    while True:
        q, r = divmod(i, 26)
        yield (letters[q - 1] if q > 0 else '') + letters[r]
        i += 1


def _make_aliases(uuids: list[str], existing: dict[str, str]) -> dict[str, str]:
    """Merge new UUIDs into existing alias map, assigning new keys for unknowns."""
    uuid_to_alias = {v: k for k, v in existing.items()}
    taken = set(existing.keys())
    result = dict(existing)
    new_uuids = [u for u in uuids if u not in uuid_to_alias]
    gen = _alias_gen()
    for uid in new_uuids:
        alias = next(a for a in gen if a not in taken)
        taken.add(alias)
        result[alias] = uid
    return result


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _output_concepts(
    results: list[dict],
    contents: dict[str, str],
    aliases: dict[str, str],
    args,
) -> None:
    uuid_to_alias = {v: k for k, v in aliases.items()}
    if args.json:
        out = []
        for r in results:
            content = contents.get(r['uuid'], '')
            title = _extract_title(content) or r.get('title', '')
            entry = {
                'score': round(1 - r['distance'], 4),
                'uuid': r['uuid'],
                'alias': uuid_to_alias.get(r['uuid'], ''),
                'title': title,
            }
            if args.full:
                entry['content'] = content
            else:
                entry['excerpt'] = _excerpt(content, title)
            out.append(entry)
        print(json.dumps(out, indent=2))
    elif args.markdown:
        for r in results:
            content = contents.get(r['uuid'], '')
            fname = f"{r['uuid']}.md"
            with open(fname, 'w') as f:
                f.write(content)
            print(f'wrote {fname}')
    else:
        for r in results:
            content = contents.get(r['uuid'], '')
            title = _extract_title(content) or r.get('title', '')
            score = round(1 - r['distance'], 2)
            alias = uuid_to_alias.get(r['uuid'], '')
            if args.full:
                print(f'{score:.2f}  {alias}  {r["uuid"]}  # {title}\n{content}\n')
            else:
                excerpt = _excerpt(content, title)
                print(f'{score:.2f}  {alias}  {r["uuid"]}  # {title}')
                if excerpt:
                    print(f'            {excerpt}')


def cmd_suggest(git_dir: str, content: str, args) -> None:
    model = common.resolve_embedding_model(git_dir)
    ollama_client.check_ollama(model)
    conn = db.get_connection(git_dir)
    if not db.vector_tables_exist(conn):
        print('No concepts in BB yet.', file=sys.stderr)
        sys.exit(0)
    embedding = ollama_client.get_embedding(model, content)
    results = db.search_concepts(conn, embedding)
    if not results:
        print('No matching concepts found.')
        return
    contents = {}
    for r in results:
        try:
            c, _, _ = git_ops.read_concept(git_dir, r['uuid'])
            contents[r['uuid']] = c
        except SystemExit:
            contents[r['uuid']] = ''
    existing = common.load_aliases(git_dir)
    aliases = _make_aliases([r['uuid'] for r in results], existing)
    common.save_aliases(git_dir, aliases)
    _output_concepts(results, contents, aliases, args)


def cmd_genesis(git_dir: str, content: str, args) -> None:
    model = common.resolve_embedding_model(git_dir)
    ollama_client.check_ollama(model)
    new_uuid = str(uuid_lib.uuid4())
    title = _extract_title(content)
    _validate_title(title)

    source_uuid = None
    source_version = None
    if args.branch:
        raw_branch, branch_v, branch_mode = _parse_version_suffix(args.branch)
        if branch_mode not in ('latest', 'exact'):
            print('error: --branch only accepts an exact version suffix, e.g. --branch <uuid>@2', file=sys.stderr)
            sys.exit(1)
        alias_resolved = common.resolve_alias(git_dir, raw_branch)
        if alias_resolved:
            source_uuid = alias_resolved
        else:
            source_uuid = _resolve_uuid(git_dir, raw_branch)
        if not git_ops.concept_exists(git_dir, source_uuid):
            print(f'error: source concept {source_uuid} not found', file=sys.stderr)
            sys.exit(1)
        if branch_mode == 'exact':
            all_v = git_ops.read_all_versions(git_dir, source_uuid)
            match = next((v for v in all_v if v['version'] == branch_v), None)
            if match is None:
                print(f'error: version {branch_v} not found for concept {source_uuid}', file=sys.stderr)
                sys.exit(1)
            source_version = branch_v
        else:
            _, _, source_version = git_ops.read_concept(git_dir, source_uuid)

    commit_sha, blob_sha = git_ops.write_genesis_commit(git_dir, new_uuid, content, source_uuid, source_version)
    conn = db.get_connection(git_dir)
    embedding = ollama_client.get_embedding(model, content)
    db.ensure_vector_tables(conn, len(embedding))
    db.upsert_concept(conn, new_uuid, title, commit_sha, blob_sha, 1, _now(), source_uuid, source_version)
    db.upsert_embedding(conn, new_uuid, embedding)
    if args.json:
        out = {'uuid': new_uuid, 'title': title, 'version': 1}
        if source_uuid:
            out['branched_from'] = source_uuid
            out['branched_from_version'] = source_version
        print(json.dumps(out))
    else:
        if source_uuid:
            print(f'branch  {_short_uuid(new_uuid)}  # {title}  (from {source_uuid} v{source_version})')
        else:
            print(f'genesis  {_short_uuid(new_uuid)}  # {title}')


def cmd_new_version(git_dir: str, content: str, concept_uuid: str, args) -> None:
    if not git_ops.concept_exists(git_dir, concept_uuid):
        print(f'error: concept {concept_uuid} not found', file=sys.stderr)
        sys.exit(1)
    model = common.resolve_embedding_model(git_dir)
    ollama_client.check_ollama(model)
    title = _extract_title(content)
    _validate_title(title)
    commit_sha, blob_sha, version = git_ops.write_new_version_commit(
        git_dir, concept_uuid, content
    )
    conn = db.get_connection(git_dir)
    embedding = ollama_client.get_embedding(model, content)
    db.ensure_vector_tables(conn, len(embedding))
    db.upsert_concept(conn, concept_uuid, title, commit_sha, blob_sha, version, _now())
    db.upsert_embedding(conn, concept_uuid, embedding)
    if args.json:
        print(json.dumps({'uuid': concept_uuid, 'title': title, 'version': version}))
    else:
        print(f'version {version}  {_short_uuid(concept_uuid)}  # {title}')


def _collect_ancestors(git_dir: str, uuid: str, from_version: int) -> list[dict]:
    """Walk provenance/absorbed chain recursively, collecting versions up to from_version, newest first."""
    all_v = git_ops.read_all_versions(git_dir, uuid)
    subset = [v for v in all_v if v['version'] <= from_version]
    subset.reverse()  # newest first
    for entry in subset:
        entry['uuid'] = uuid
    result = list(subset)
    # follow branch provenance
    genesis = all_v[0] if all_v else None
    if genesis and genesis.get('source_uuid'):
        result += _collect_ancestors(git_dir, genesis['source_uuid'], genesis['source_version'])
    # follow merge absorptions — each merge version points at an absorbed concept
    for v in subset:
        if v.get('absorbed_uuid'):
            result += _collect_ancestors(git_dir, v['absorbed_uuid'], v['absorbed_version'])
    return result


def _collect_descendants(git_dir: str, uuid: str, from_version: int, conn) -> list[dict]:
    """Walk branch descendants recursively, collecting versions >= from_version, oldest first."""
    all_v = git_ops.read_all_versions(git_dir, uuid)
    subset = [v for v in all_v if v['version'] >= from_version]
    for entry in subset:
        entry['uuid'] = uuid
    result = list(subset)
    branches = db.get_branches_from(conn, uuid)
    for branch in branches:
        if branch['source_version'] >= from_version:
            result += _collect_descendants(git_dir, branch['uuid'], 1, conn)
    return result


def cmd_resolve(git_dir: str, concept_uuid: str, version: int | None, mode: str, args) -> None:
    if not git_ops.concept_exists(git_dir, concept_uuid):
        print(f'error: concept {concept_uuid} not found', file=sys.stderr)
        sys.exit(1)
    alias = common.resolve_alias_key(git_dir, concept_uuid) or ''

    if mode == 'latest':
        content, blob_sha, ver = git_ops.read_concept(git_dir, concept_uuid)
        _output_versions([{'content': content, 'blob_sha': blob_sha, 'version': ver,
                           'source_uuid': None, 'source_version': None}],
                         concept_uuid, alias, args)
        return

    if version < 1:
        print('error: versions start at 1', file=sys.stderr)
        sys.exit(1)

    all_versions = git_ops.read_all_versions(git_dir, concept_uuid)
    version_nums = {v['version'] for v in all_versions}

    if mode == 'exact':
        if version not in version_nums:
            print(f'error: version {version} not found for concept {concept_uuid}', file=sys.stderr)
            sys.exit(1)
        entry = next(v for v in all_versions if v['version'] == version)
        entry['uuid'] = concept_uuid
        _output_versions([entry], concept_uuid, alias, args)
    elif mode == '+':
        subset = _collect_descendants(git_dir, concept_uuid, version, db.get_connection(git_dir))
        if not subset:
            print(f'error: no versions >= {version} found', file=sys.stderr)
            sys.exit(1)
        _output_versions(subset, concept_uuid, alias, args)
    elif mode == '-':
        subset = _collect_ancestors(git_dir, concept_uuid, version)
        if not subset:
            print(f'error: no versions <= {version} found', file=sys.stderr)
            sys.exit(1)
        _output_versions(subset, concept_uuid, alias, args)


def _parse_version_suffix(value: str) -> tuple[str, int | None, str]:
    """Split alias/uuid from optional @version suffix.
    Returns (base, version, mode) where mode is 'exact', '+', '-', or 'latest'.
    """
    if '@' not in value:
        return value, None, 'latest'
    base, suffix = value.rsplit('@', 1)
    if suffix.endswith('+'):
        n = int(suffix[:-1])
        return base, n, '+'
    elif suffix.endswith('-'):
        n = int(suffix[:-1])
        return base, n, '-'
    else:
        return base, int(suffix), 'exact'


def _output_versions(
    versions: list[dict],
    uuid: str,
    alias: str,
    args,
) -> None:
    if args.json:
        out = []
        for v in versions:
            title = _extract_title(v['content'])
            entry = {'uuid': v.get('uuid', uuid), 'alias': alias, 'title': title, 'version': v['version']}
            if v.get('source_uuid'):
                entry['branched_from'] = v['source_uuid']
                entry['branched_from_version'] = v['source_version']
            if args.full:
                entry['content'] = v['content']
            else:
                entry['excerpt'] = _excerpt(v['content'], title)
            out.append(entry)
        print(json.dumps(out if len(out) > 1 else out[0], indent=2))
    elif args.markdown:
        for v in versions:
            entry_uuid = v.get('uuid', uuid)
            fname = f'{entry_uuid}@{v["version"]}.md'
            with open(fname, 'w') as f:
                f.write(v['content'])
            print(f'wrote {fname}')
    else:
        for v in versions:
            entry_uuid = v.get('uuid', uuid)
            title = _extract_title(v['content'])
            if v.get('source_uuid'):
                note = f'  ← branched from {v["source_uuid"]} v{v["source_version"]}'
            elif v.get('absorbed_uuid'):
                note = f'  ← merged {v["absorbed_uuid"]} v{v["absorbed_version"]}'
            else:
                note = ''
            if args.full:
                print(f'v{v["version"]}  {alias}  {entry_uuid}  # {title}{note}')
                print(v['content'])
                print()
            else:
                print(f'v{v["version"]}  {alias}  {entry_uuid}  # {title}{note}')
                excerpt = _excerpt(v['content'], title)
                if excerpt:
                    print(f'            {excerpt}')


def _resolve_uuid(git_dir: str, value: str) -> str:
    if len(value) == 36:
        return value
    resolved = git_ops.resolve_uuid(git_dir, value)
    if resolved is None:
        print(f'error: no unique concept found for prefix "{value}"', file=sys.stderr)
        sys.exit(1)
    return resolved


def cmd_alias_reassign(git_dir: str, current: str, new: str) -> None:
    aliases = common.load_aliases(git_dir)
    if current not in aliases:
        print(f'error: alias "{current}" not found', file=sys.stderr)
        sys.exit(1)
    uid = aliases.pop(current)
    aliases[new] = uid
    common.save_aliases(git_dir, aliases)
    print(f'{current} → {new}  {uid}')


def cmd_merge(git_dir: str, survivor_uuid: str, retired_raw: str, content: str | None, args) -> None:
    # resolve retired UUID
    alias_resolved = common.resolve_alias(git_dir, retired_raw)
    retired_uuid = alias_resolved if alias_resolved else _resolve_uuid(git_dir, retired_raw)

    if not git_ops.concept_exists(git_dir, survivor_uuid):
        print(f'error: survivor concept {survivor_uuid} not found', file=sys.stderr)
        sys.exit(1)
    if not git_ops.concept_exists(git_dir, retired_uuid):
        print(f'error: retired concept {retired_uuid} not found', file=sys.stderr)
        sys.exit(1)
    if survivor_uuid == retired_uuid:
        print('error: survivor and retired must be different concepts', file=sys.stderr)
        sys.exit(1)

    # use survivor's latest content if none provided
    if not content:
        content, _, _ = git_ops.read_concept(git_dir, survivor_uuid)

    title = _extract_title(content)
    _validate_title(title)

    _, retired_blob_sha, absorbed_version = git_ops.read_concept(git_dir, retired_uuid)

    model = common.resolve_embedding_model(git_dir)
    ollama_client.check_ollama(model)

    conn = db.get_connection(git_dir)

    # warn if judgments exist for retired concept (future — not yet implemented)
    # TODO: check judgment index once judgment storage is implemented

    commit_sha, blob_sha, new_version = git_ops.write_merge_commit(
        git_dir, survivor_uuid, content, retired_uuid, absorbed_version
    )
    git_ops.write_retire_commit(git_dir, retired_uuid, survivor_uuid, new_version)

    embedding = ollama_client.get_embedding(model, content)
    db.ensure_vector_tables(conn, len(embedding))
    db.upsert_concept(conn, survivor_uuid, title, commit_sha, blob_sha, new_version, _now())
    db.upsert_embedding(conn, survivor_uuid, embedding)
    db.retire_concept(conn, retired_uuid, survivor_uuid, new_version)

    if args.json:
        print(json.dumps({
            'survivor': survivor_uuid,
            'retired': retired_uuid,
            'version': new_version,
            'title': title,
        }))
    else:
        print(f'merge  v{new_version}  {_short_uuid(survivor_uuid)}  # {title}')
        print(f'       retired  {retired_uuid}')


def cmd_concept(args) -> None:
    git_dir = common.find_git_dir()
    common.require_bb(git_dir)

    content = _resolve_content(args.content)

    version_n = None
    version_mode = 'latest'

    if args.alias:
        if len(args.alias) == 2:
            cmd_alias_reassign(git_dir, args.alias[0], args.alias[1])
            return
        raw_alias, version_n, version_mode = _parse_version_suffix(args.alias[0])
        resolved = common.resolve_alias(git_dir, raw_alias)
        if resolved is None:
            print(f'error: alias "{raw_alias}" not found', file=sys.stderr)
            sys.exit(1)
        args.uuid = resolved
    elif args.uuid:
        raw_uuid, version_n, version_mode = _parse_version_suffix(args.uuid)
        args.uuid = _resolve_uuid(git_dir, raw_uuid)

    suggest_mode = getattr(args, '_suggest', False)

    if args.merge and not args.uuid:
        print('error: --merge requires --uuid to specify the survivor', file=sys.stderr)
        sys.exit(1)

    if args.genesis:
        if not content:
            print('error: content required for genesis', file=sys.stderr)
            sys.exit(1)
        cmd_genesis(git_dir, content, args)
    elif args.merge and args.uuid:
        cmd_merge(git_dir, args.uuid, args.merge, content, args)
    elif args.uuid and content:
        cmd_new_version(git_dir, content, args.uuid, args)
    elif args.uuid and not content:
        cmd_resolve(git_dir, args.uuid, version_n, version_mode, args)
    elif suggest_mode and content:
        cmd_suggest(git_dir, content, args)
    else:
        print('error: prefix content with ? to suggest, add --genesis to record, or use --uuid/--alias to look up', file=sys.stderr)
        sys.exit(1)
