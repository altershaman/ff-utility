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
    commit_sha, blob_sha = git_ops.write_genesis_commit(git_dir, new_uuid, content)
    conn = db.get_connection(git_dir)
    embedding = ollama_client.get_embedding(model, content)
    db.ensure_vector_tables(conn, len(embedding))
    db.upsert_concept(conn, new_uuid, title, commit_sha, blob_sha, 1, _now())
    db.upsert_embedding(conn, new_uuid, embedding)
    if args.json:
        print(json.dumps({'uuid': new_uuid, 'title': title, 'version': 1}))
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


def cmd_resolve(git_dir: str, concept_uuid: str, args) -> None:
    if not git_ops.concept_exists(git_dir, concept_uuid):
        print(f'error: concept {concept_uuid} not found', file=sys.stderr)
        sys.exit(1)
    content, blob_sha, version = git_ops.read_concept(git_dir, concept_uuid)
    title = _extract_title(content)
    alias = common.resolve_alias_key(git_dir, concept_uuid) or 'a'
    if args.json:
        entry = {'uuid': concept_uuid, 'alias': alias, 'title': title, 'version': version}
        if args.full:
            entry['content'] = content
        else:
            entry['excerpt'] = _excerpt(content, title)
        print(json.dumps(entry))
    elif args.markdown:
        fname = f'{concept_uuid}.md'
        with open(fname, 'w') as f:
            f.write(content)
        print(f'wrote {fname}')
    else:
        if args.full:
            print(f'{alias}  {concept_uuid}  # {title}')
            print(content)
        else:
            print(f'{alias}  {concept_uuid}  # {title}')
            excerpt = _excerpt(content, title)
            if excerpt:
                print(excerpt)


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


def cmd_concept(args) -> None:
    git_dir = common.find_git_dir()
    common.require_bb(git_dir)

    content = _resolve_content(args.content)

    if args.alias:
        if len(args.alias) == 2:
            cmd_alias_reassign(git_dir, args.alias[0], args.alias[1])
            return
        resolved = common.resolve_alias(git_dir, args.alias[0])
        if resolved is None:
            print(f'error: alias "{args.alias[0]}" not found', file=sys.stderr)
            sys.exit(1)
        args.uuid = resolved
    elif args.uuid:
        args.uuid = _resolve_uuid(git_dir, args.uuid)

    suggest_mode = getattr(args, '_suggest', False)

    if args.genesis:
        if not content:
            print('error: content required for genesis', file=sys.stderr)
            sys.exit(1)
        cmd_genesis(git_dir, content, args)
    elif args.uuid and content:
        cmd_new_version(git_dir, content, args.uuid, args)
    elif args.uuid and not content:
        cmd_resolve(git_dir, args.uuid, args)
    elif suggest_mode and content:
        cmd_suggest(git_dir, content, args)
    else:
        print('error: prefix content with ? to suggest, add --genesis to record, or use --uuid/--alias to look up', file=sys.stderr)
        sys.exit(1)
