"""Frozen snapshot paths and persistent roots; package internals remain unchanged.

Allocation commits its independent reservation before mkdir. Callers must not
wrap allocation in their task transaction. Reservations are permanent even when
filesystem creation or later task/context publication fails.
"""
import itertools
import os
import re
import secrets
import stat
import string
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from ..policy_ir import PATTERN_MAX_UTF8_BYTES

PROJECT_MARKERS = frozenset({'setup.py', 'pyproject.toml', 'package.json', 'Cargo.toml', 'go.mod', 'pom.xml', 'CMakeLists.txt'})
COMPACT_PREFIXES = string.ascii_lowercase[15:] + string.ascii_lowercase[:15] + string.ascii_uppercase
ROOT_ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits
SHORT_ROOT_CAPACITY = len(ROOT_ALPHABET) ** 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot_roots (
 root TEXT PRIMARY KEY, task_id TEXT UNIQUE, base TEXT NOT NULL,
 root_key TEXT NOT NULL, workspace TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('task_id','compact')),
 state TEXT NOT NULL CHECK(state IN ('reserved','ready','occupied','failed')),
 device INTEGER, inode INTEGER, created_at TEXT NOT NULL
);
"""


def snapshot_layout(entries, workspace, *, compact_prefixes=False):
    paths = [str(entry['relative_path']) for entry in entries]
    parts = {}
    for value in paths:
        path = PurePosixPath(value)
        if not path.parts or path.is_absolute() or '..' in path.parts or str(path) != value:
            raise ValueError('工作区快照路径必须是规范相对路径')
        parts[value] = path.parts
    project_roots = {value[:-1] for value in parts.values() if value[-1] in PROJECT_MARKERS}
    used = {value[0] for value in parts.values()}
    prefixes = {}
    for root in sorted(project_roots, key=lambda value: (len(value), value)):
        if not root or any(root[:i] in project_roots for i in range(len(root))):
            continue
        members = [name for name, value in parts.items() if value[:len(root)] == root]
        if not any(len((str(workspace) + '/' + name).encode('utf-8')) > PATTERN_MAX_UTF8_BYTES for name in members):
            continue
        if compact_prefixes:
            alias = next((name for name in COMPACT_PREFIXES if name not in used), None)
            if alias is None:
                raise ValueError('snapshot_project_alias_capacity_exhausted')
        else:
            index = 0
            while 'p' + str(index) in used:
                index += 1
            alias = 'p' + str(index)
        if len('/'.join(root).encode('utf-8')) <= len(alias.encode('utf-8')):
            continue
        used.add(alias)
        prefixes['/'.join(root)] = alias
    mapping = {}
    for name in paths:
        prefix = next((prefix for prefix in prefixes if name.startswith(prefix + '/')), None)
        mapping[name] = prefixes[prefix] + name[len(prefix):] if prefix else name
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('工作区快照路径映射发生冲突')
    return mapping, prefixes


def _fits(mapping, workspace):
    return all(len((str(workspace) + '/' + name).encode('utf-8')) <= PATTERN_MAX_UTF8_BYTES for name in mapping.values())


def _root_key(path, base):
    """Read historical lexical paths even when their filesystem has disappeared."""
    if not isinstance(path, str) or not path.startswith('/'):
        return None
    value = PurePosixPath(os.path.normpath(path))
    try:
        parts = value.relative_to(PurePosixPath(base)).parts
    except ValueError:
        return None
    return parts[0] if parts else None


def _occupied_keys(con, base):
    used = {_root_key(row[0], base) for row in con.execute('SELECT root FROM snapshot_roots')}
    columns = {row[1] for row in con.execute('PRAGMA table_info(tasks)')}
    for column in ('workspace', 'output_dir'):
        if column in columns:
            used.update(_root_key(row[0], base) for row in con.execute('SELECT ' + column + ' FROM tasks'))
    used.discard(None)
    return used


def _short_root_keys():
    # A random starting point, then every slot exactly once. Capacity is finite,
    # and available slots cannot be missed through repeated random samples.
    keys = [''.join(parts) for parts in itertools.product(ROOT_ALPHABET, repeat=2)]
    start = secrets.randbelow(SHORT_ROOT_CAPACITY)
    return keys[start:] + keys[:start]


def _canonical_directory(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir() or path.resolve(strict=True) != path:
        raise ValueError('snapshot_directory_must_be_canonical_and_real')
    return path


def _insert_reservation(con, root, task_id, base, mode, state, identity=None):
    con.execute('INSERT INTO snapshot_roots(root,task_id,base,root_key,workspace,mode,state,device,inode,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (str(root), task_id, str(base), root.name, str(root / 'r'), mode, state,
                 identity.st_dev if identity else None, identity.st_ino if identity else None,
                 datetime.now(timezone.utc).isoformat()))


def allocate_snapshot_layout(entries, base, task_id, con):
    """Commit a permanent reservation, then exclusively mkdir its physical root.

    con must have no active transaction. Returns (root: Path, asset_mapping,
    project_aliases, storage). Caller task publication is a later transaction;
    its rollback never releases this allocation. Failed allocations and existing
    FS entries remain occupied, even if their directory subsequently disappears.
    """
    if con.in_transaction:
        raise ValueError('snapshot_allocation_requires_independent_connection')
    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', task_id):
        raise ValueError('snapshot_task_id_invalid')
    base = _canonical_directory(base)
    entries = list(entries)
    default_root = base / task_id
    mapping, aliases = snapshot_layout(entries, default_root / 'r')
    compact = not _fits(mapping, default_root / 'r')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    base_fd = os.open(base, flags)
    try:
        original = base.stat(follow_symlinks=False)
        opened = os.fstat(base_fd)
        if (original.st_dev, original.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError('snapshot_base_identity_changed')
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute(SCHEMA)
            if con.execute('SELECT 1 FROM snapshot_roots WHERE task_id=?', (task_id,)).fetchone():
                raise ValueError('snapshot_task_already_reserved')
            occupied = _occupied_keys(con, base)
            candidates = _short_root_keys() if compact else [task_id]
            mode = 'compact' if compact else 'task_id'
            chosen = None
            for attempt, key in enumerate(candidates, 1):
                root = base / key
                if key in occupied:
                    # Import a historical task's missing filesystem root into
                    # the permanent ledger before any later task deletion.
                    if not con.execute('SELECT 1 FROM snapshot_roots WHERE root=?', (str(root),)).fetchone():
                        _insert_reservation(con, root, None, base, mode, 'occupied')
                    continue
                try:
                    identity = os.stat(key, dir_fd=base_fd, follow_symlinks=False)
                except FileNotFoundError:
                    identity = None
                if identity is not None:
                    _insert_reservation(con, root, None, base, mode, 'occupied', identity)
                    continue
                _insert_reservation(con, root, task_id, base, mode, 'reserved')
                chosen = root
                break
            con.commit()  # Durable before mkdir, including every collision.
        except BaseException:
            con.rollback()
            raise
        if chosen is None:
            if compact:
                raise ValueError('snapshot_short_root_capacity_exhausted:3844')
            raise ValueError('snapshot_root_reserved_or_filesystem_collision')
        root = chosen
        try:
            # If another process creates an entry after our check, this fails;
            # the assigned reservation remains a permanent failed tombstone.
            os.mkdir(root.name, mode=0o700, dir_fd=base_fd)
            root_fd = os.open(root.name, flags, dir_fd=base_fd)
            try:
                os.fchmod(root_fd, 0o700)
                identity = os.fstat(root_fd)
                named = os.stat(root.name, dir_fd=base_fd, follow_symlinks=False)
                parent_now = base.stat(follow_symlinks=False)
                if (not stat.S_ISDIR(named.st_mode)
                        or (identity.st_dev, identity.st_ino) != (named.st_dev, named.st_ino)
                        or (opened.st_dev, opened.st_ino) != (parent_now.st_dev, parent_now.st_ino)
                        or root.is_symlink() or root.resolve(strict=True) != root):
                    raise ValueError('snapshot_root_identity_changed')
                con.execute('BEGIN IMMEDIATE')
                try:
                    result = con.execute("UPDATE snapshot_roots SET state='ready',device=?,inode=? WHERE root=? AND task_id=? AND state='reserved'",
                                         (identity.st_dev, identity.st_ino, str(root), task_id))
                    if result.rowcount != 1:
                        raise ValueError('snapshot_reservation_identity_changed')
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
            finally:
                os.close(root_fd)
        except BaseException:
            # This cannot undo the earlier committed reservation. Do not delete
            # a directory on any failure, including a racer-owned FS entry.
            if con.in_transaction:
                con.rollback()
            con.execute("UPDATE snapshot_roots SET state='failed' WHERE root=? AND task_id=? AND state='reserved'", (str(root), task_id))
            con.commit()
            raise
        if compact:
            mapping, aliases = snapshot_layout(entries, root / 'r', compact_prefixes=True)
        overlong = [{'path': str(root / 'r' / mapped), 'source_relative_path': source,
                     'utf8_bytes': len(str(root / 'r' / mapped).encode('utf-8')),
                     'limit': PATTERN_MAX_UTF8_BYTES}
                    for source, mapped in mapping.items()
                    if len(str(root / 'r' / mapped).encode('utf-8')) > PATTERN_MAX_UTF8_BYTES]
        storage = {'schema': 'snapshot-root/1', 'task_id': task_id,
                   'base': str(base), 'root': str(root), 'root_key': root.name,
                   'workspace': str(root / 'r'), 'mode': mode, 'compact': compact,
                   'device': identity.st_dev, 'inode': identity.st_ino,
                   'short_root_capacity': SHORT_ROOT_CAPACITY,
                   'pattern_max_utf8_bytes': PATTERN_MAX_UTF8_BYTES,
                   'allocation_attempts': attempt, 'overlong_assets': overlong,
                   'all_assets_fit': not overlong}
        return root, mapping, aliases, storage
    finally:
        os.close(base_fd)


def verify_snapshot_root(task_id, workspace, output_dir, storage, con):
    """Read-only admission check. Invalid or replaced roots raise ValueError.

    Mode/ownership may legitimately change when registry grants the task group
    access; device/inode, canonical paths and immutable task reservation may not.
    """
    if not isinstance(storage, dict) or storage.get('task_id') != task_id:
        raise ValueError('snapshot_storage_task_mismatch')
    try:
        root = _canonical_directory(storage['root'])
        base = _canonical_directory(storage['base'])
        ws = _canonical_directory(workspace)
        output = _canonical_directory(output_dir)
    except (KeyError, OSError, TypeError) as error:
        raise ValueError('snapshot_storage_directory_unavailable') from error
    if (str(root) != storage['root'] or str(base) != storage['base']
            or root.parent != base or storage.get('root_key') != root.name
            or ws != root / 'r' or output != root / 'output'
            or storage.get('workspace') != str(ws)):
        raise ValueError('snapshot_storage_path_mismatch')
    row = con.execute('SELECT root,task_id,base,root_key,workspace,mode,state,device,inode FROM snapshot_roots WHERE task_id=?', (task_id,)).fetchone()
    expected = (str(root), task_id, str(base), root.name, str(ws),
                'compact' if storage.get('compact') is True else 'task_id', 'ready',
                storage.get('device'), storage.get('inode'))
    if row is None or tuple(row) != expected or not isinstance(storage.get('compact'), bool):
        raise ValueError('snapshot_storage_reservation_mismatch')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    base_fd = os.open(base, flags)
    try:
        base_identity = os.fstat(base_fd)
        parent_named = base.stat(follow_symlinks=False)
        if (base_identity.st_dev, base_identity.st_ino) != (parent_named.st_dev, parent_named.st_ino):
            raise ValueError('snapshot_storage_base_replaced')
        root_fd = os.open(root.name, flags, dir_fd=base_fd)
        try:
            identity = os.fstat(root_fd)
            named = os.stat(root.name, dir_fd=base_fd, follow_symlinks=False)
            absolute_named = root.stat(follow_symlinks=False)
            if ((identity.st_dev, identity.st_ino) != (storage['device'], storage['inode'])
                    or (identity.st_dev, identity.st_ino) != (named.st_dev, named.st_ino)
                    or (identity.st_dev, identity.st_ino) != (absolute_named.st_dev, absolute_named.st_ino)
                    or root.resolve(strict=True) != root):
                raise ValueError('snapshot_storage_inode_mismatch')
            for child in ('r', 'output'):
                child_fd = os.open(child, flags, dir_fd=root_fd)
                try:
                    child_identity = os.fstat(child_fd)
                    child_named = os.stat(child, dir_fd=root_fd, follow_symlinks=False)
                    if (child_identity.st_dev, child_identity.st_ino) != (child_named.st_dev, child_named.st_ino):
                        raise ValueError('snapshot_storage_child_replaced')
                    if (root / child).resolve(strict=True) != root / child:
                        raise ValueError('snapshot_storage_child_replaced')
                finally:
                    os.close(child_fd)
        finally:
            os.close(root_fd)
    except OSError as error:
        raise ValueError('snapshot_storage_directory_unavailable') from error
    finally:
        os.close(base_fd)
    return True
