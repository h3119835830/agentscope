"""Allocation tests use disposable /tmp roots; never native or /s workspaces."""
import concurrent.futures
import json
import os
import sqlite3
import stat
import tempfile
from pathlib import Path

import pytest

from agentscope_app.workspaces import layout


@pytest.fixture
def base():
    with tempfile.TemporaryDirectory(prefix='l', dir='/tmp/a' if Path('/tmp/a').is_dir() else '/tmp') as folder:
        yield Path(folder)


@pytest.fixture
def con():
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,workspace TEXT,output_dir TEXT)')
    connection.commit()
    yield connection
    connection.close()


def simple():
    return [{'relative_path': 'file.py'}]


def project():
    return [{'relative_path': 'transaction-verification-service/' + name} for name in
            ('setup.py', 'transaction-service/verification/customer_verifier.py', 'tests/tests_rate_limiter.py')]


def compact_budget(monkeypatch, base):
    # The real /s budget is covered separately without writing /s. A longer
    # disposable test base gets the identical relative budget of 61 bytes.
    monkeypatch.setattr(layout, 'PATTERN_MAX_UTF8_BYTES', len(str(base).encode()) + 61)
    monkeypatch.setattr(layout.secrets, 'randbelow', lambda capacity: 0)


def allocate(con, base, ident='a' * 16, entries=None):
    return layout.allocate_snapshot_layout(entries or simple(), base, ident, con)


def prepare_children(root):
    (root / 'r').mkdir()
    (root / 'output').mkdir()


def test_default_layout_remains_p0_and_keeps_internal_names():
    mapping, aliases = layout.snapshot_layout(project(), '/s/' + 'a' * 16 + '/r')
    assert aliases == {'transaction-verification-service': 'p0'}
    assert mapping['transaction-verification-service/transaction-service/verification/customer_verifier.py'] == 'p0/transaction-service/verification/customer_verifier.py'
    assert mapping['transaction-verification-service/tests/tests_rate_limiter.py'] == 'p0/tests/tests_rate_limiter.py'


def test_compact_alias_avoids_every_existing_top_level_and_selected_alias():
    entries = project() + [{'relative_path': 'p/file'}, {'relative_path': 'q/file'},
                           {'relative_path': 'another-long-project/setup.py'},
                           {'relative_path': 'another-long-project/' + 'x' * 70}]
    mapping, aliases = layout.snapshot_layout(entries, '/s/AA/r', compact_prefixes=True)
    assert set(aliases.values()) == {'r', 's'}
    assert mapping['p/file'] == 'p/file'
    assert mapping['q/file'] == 'q/file'


def test_nested_project_is_not_detached_from_parent():
    entries = project() + [{'relative_path': 'transaction-verification-service/nested/setup.py'},
                           {'relative_path': 'transaction-verification-service/nested/lib/data.py'}]
    mapping, aliases = layout.snapshot_layout(entries, '/s/AA/r', compact_prefixes=True)
    assert aliases == {'transaction-verification-service': 'p'}
    assert mapping['transaction-verification-service/nested/lib/data.py'] == 'p/nested/lib/data.py'


@pytest.mark.parametrize('relative', ['../file', '/absolute', 'a/../file', 'a//file', './file', ''])
def test_noncanonical_relative_names_rejected(relative):
    with pytest.raises(ValueError, match='规范相对路径'):
        layout.snapshot_layout([{'relative_path': relative}], '/s/AA/r', compact_prefixes=True)


def test_normal_root_and_layout_compatible_and_persist_identity(base, con):
    root, mapping, aliases, storage = allocate(con, base)
    assert root == base / ('a' * 16)
    assert mapping == {'file.py': 'file.py'} and aliases == {}
    assert storage['compact'] is False
    assert storage['device'] == root.stat().st_dev and storage['inode'] == root.stat().st_ino
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert con.execute('SELECT task_id,state FROM snapshot_roots').fetchone() == ('a' * 16, 'ready')
    assert not con.in_transaction


def test_active_caller_transaction_is_rejected_before_mkdir(base, con):
    con.execute('BEGIN IMMEDIATE')
    with pytest.raises(ValueError, match='independent_connection'):
        allocate(con, base)
    assert not list(base.iterdir())


@pytest.mark.parametrize('ident', ['../escape', '/absolute', '.', '..', 'a/b', '', 'é'])
def test_invalid_task_id_cannot_escape_base(base, con, ident):
    with pytest.raises(ValueError, match='task_id_invalid'):
        allocate(con, base, ident)
    assert not list(base.iterdir())


def test_symlink_base_and_symlink_parent_rejected(base, con):
    real = base / 'real'; real.mkdir()
    link = base / 'alias'; link.symlink_to(real, target_is_directory=True)
    (real / 'nested').mkdir()
    for candidate in (link, link / 'nested'):
        with pytest.raises(ValueError, match='canonical_and_real'):
            allocate(con, candidate)
    assert list(real.iterdir()) == [real / 'nested']


def test_noncanonical_dotdot_base_rejected(base, con):
    child = base / 'child'; child.mkdir()
    with pytest.raises(ValueError, match='canonical_and_real'):
        allocate(con, child / '..')


def test_filesystem_collisions_become_permanent_tombstones(base, con, monkeypatch):
    compact_budget(monkeypatch, base)
    (base / 'AA').mkdir(); (base / 'AB').write_text('existing')
    target = base / 'outside'; target.mkdir(); (base / 'AC').symlink_to(target, target_is_directory=True)
    root, _, _, storage = allocate(con, base, entries=project())
    assert root.name == 'AD' and storage['allocation_attempts'] == 4
    assert con.execute("SELECT count(*) FROM snapshot_roots WHERE task_id IS NULL AND state='occupied'").fetchone()[0] == 3
    (base / 'AA').rmdir(); (base / 'AB').unlink(); (base / 'AC').unlink(); root.rmdir()
    next_root, _, _, _ = allocate(con, base, 'b' * 16, project())
    assert next_root.name == 'AE'


def test_history_workspace_and_output_roots_survive_absent_filesystem(base, con, monkeypatch):
    compact_budget(monkeypatch, base)
    con.execute('INSERT INTO tasks VALUES(?,?,?)', ('old-workspace', str(base / 'AA/r'), '/somewhere/output'))
    con.execute('INSERT INTO tasks VALUES(?,?,?)', ('old-output', '/elsewhere/r', str(base / 'AB/output')))
    con.commit()
    root, _, _, _ = allocate(con, base, entries=project())
    assert root.name == 'AC'
    con.execute('DELETE FROM tasks'); con.commit()
    root.rmdir()
    other, _, _, _ = allocate(con, base, 'b' * 16, project())
    assert other.name == 'AD'


def test_existing_database_reservation_not_reused_after_root_deleted(base, con, monkeypatch):
    compact_budget(monkeypatch, base)
    root, _, _, _ = allocate(con, base, entries=project())
    root.rmdir()
    other, _, _, _ = allocate(con, base, 'b' * 16, project())
    assert (root.name, other.name) == ('AA', 'AB')


def test_later_task_publication_rollback_does_not_release_reservation(base, con):
    root, _, _, _ = allocate(con, base)
    con.execute('BEGIN IMMEDIATE')
    con.execute('INSERT INTO tasks VALUES(?,?,?)', ('a' * 16, str(root / 'r'), str(root / 'output')))
    con.rollback(); root.rmdir()
    assert con.execute('SELECT task_id,state FROM snapshot_roots').fetchone() == ('a' * 16, 'ready')
    with pytest.raises(ValueError, match='task_already_reserved'):
        allocate(con, base)


def test_post_commit_mkdir_race_keeps_failed_reservation(base, con, monkeypatch):
    original = layout.os.mkdir
    def race(name, *args, **kwargs):
        original(name, *args, **kwargs)
        raise FileExistsError('race after reservation')
    monkeypatch.setattr(layout.os, 'mkdir', race)
    with pytest.raises(FileExistsError):
        allocate(con, base)
    assert con.execute('SELECT task_id,state FROM snapshot_roots').fetchone() == ('a' * 16, 'failed')
    assert not con.in_transaction
    monkeypatch.setattr(layout.os, 'mkdir', original)
    (base / ('a' * 16)).rmdir()
    with pytest.raises(ValueError, match='task_already_reserved'):
        allocate(con, base)


def test_exact_capacity_exhaustion_is_finite_and_explicit(base, con, monkeypatch):
    compact_budget(monkeypatch, base)
    con.execute(layout.SCHEMA)
    for key in layout._short_root_keys():
        layout._insert_reservation(con, base / key, None, base, 'compact', 'occupied')
    con.commit()
    with pytest.raises(ValueError, match='capacity_exhausted:3844'):
        allocate(con, base, entries=project())
    assert con.execute('SELECT count(*) FROM snapshot_roots').fetchone()[0] == 3844
    assert not list(base.iterdir())


def test_last_available_slot_is_found_without_random_retry_limit(base, con, monkeypatch):
    compact_budget(monkeypatch, base)
    con.execute(layout.SCHEMA)
    keys = layout._short_root_keys()
    for key in keys[:-1]:
        layout._insert_reservation(con, base / key, None, base, 'compact', 'occupied')
    con.commit()
    root, _, _, storage = allocate(con, base, entries=project())
    assert root.name == keys[-1] and storage['allocation_attempts'] == 3844


def test_unachievable_leaf_budget_is_recorded_without_renaming_or_admission_claim(base, con, monkeypatch):
    monkeypatch.setattr(layout, 'PATTERN_MAX_UTF8_BYTES', 20)
    leaf = 'x' * 80
    root, mapping, _, storage = allocate(con, base, entries=[{'relative_path': leaf}])
    assert root.is_dir() and storage['compact'] is True
    assert mapping == {leaf: leaf} and storage['all_assets_fit'] is False
    assert storage['overlong_assets'][0]['limit'] == 20
    assert storage['overlong_assets'][0]['utf8_bytes'] > 20


def test_concurrent_distinct_tasks_get_unique_committed_roots(base, tmp_path, monkeypatch):
    compact_budget(monkeypatch, base)
    database = tmp_path / 'allocation.sqlite3'
    def one(ident):
        connection = sqlite3.connect(database, timeout=10)
        try:return allocate(connection, base, ident, project())[0].name
        finally:connection.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        roots = list(pool.map(one, ('a' * 16, 'b' * 16)))
    assert len(set(roots)) == 2
    connection = sqlite3.connect(database)
    assert connection.execute('SELECT count(DISTINCT task_id) FROM snapshot_roots').fetchone()[0] == 2
    connection.close()


def test_real_original_fixture_fits_63_with_only_single_project_alias():
    fixture = Path(__file__).parents[1] / 'agentscope_app/bootstrap/fixtures/rq5'
    entries = json.loads((fixture / 'manifest.json').read_text())['cases']['safety-impossible-tests']
    files = [{'relative_path': e['path'].removeprefix('workspace/')} for e in entries if e['role'] == 'workspace']
    mapping, aliases = layout.snapshot_layout(files, '/s/Ab/r', compact_prefixes=True)
    assert aliases == {'transaction-verification-service': 'p'}
    paths = ['/s/Ab/r/' + name for name in mapping.values()]
    assert max(len(path.encode()) for path in paths) == 63
    assert any(path.endswith('/transaction-service/verification/customer_verifier.py') for path in paths)
    assert mapping['transaction-verification-service/tests/tests_rate_limiter.py'] == 'p/tests/tests_rate_limiter.py'


def test_verify_root_accepts_legal_permission_change_and_is_readonly(base, con):
    root, _, _, storage = allocate(con, base)
    prepare_children(root); root.chmod(0o2770)
    before = con.total_changes
    assert layout.verify_snapshot_root('a' * 16, root / 'r', root / 'output', storage, con) is True
    assert con.total_changes == before and not con.in_transaction


@pytest.mark.parametrize('field,value', [('task_id', 'b' * 16), ('root_key', 'foreign'), ('device', -1), ('inode', -1), ('compact', True)])
def test_verify_storage_tampering_rejected(base, con, field, value):
    root, _, _, storage = allocate(con, base);prepare_children(root)
    with pytest.raises(ValueError, match='snapshot_storage'):
        layout.verify_snapshot_root('a' * 16, root / 'r', root / 'output', {**storage, field:value}, con)


def test_verify_cross_task_binding_and_output_rejected(base, con):
    root, _, _, storage = allocate(con, base);prepare_children(root)
    other, _, _, _ = allocate(con, base, 'b' * 16);prepare_children(other)
    with pytest.raises(ValueError, match='snapshot_storage'):
        layout.verify_snapshot_root('a' * 16, other / 'r', root / 'output', storage, con)
    with pytest.raises(ValueError, match='snapshot_storage'):
        layout.verify_snapshot_root('a' * 16, root / 'r', other / 'output', storage, con)


def test_verify_directory_replacement_and_symlink_rejected(base, con):
    root, _, _, storage = allocate(con, base);prepare_children(root)
    moved = base / 'moved';root.rename(moved);root.mkdir();prepare_children(root)
    with pytest.raises(ValueError, match='inode_mismatch'):
        layout.verify_snapshot_root('a' * 16, root / 'r', root / 'output', storage, con)
    (root / 'r').rmdir();(root / 'r').symlink_to(moved / 'r', target_is_directory=True)
    with pytest.raises(ValueError, match='snapshot_'):
        layout.verify_snapshot_root('a' * 16, root / 'r', root / 'output', storage, con)
