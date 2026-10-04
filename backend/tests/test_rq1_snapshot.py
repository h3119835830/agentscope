import importlib.util
import hashlib
import json
import sqlite3
from pathlib import Path
import pytest
from agentscope_app import db
from agentscope_app.history import catalog

spec = importlib.util.spec_from_file_location('copy_rq1_catalog', Path(__file__).resolve().parents[2] / 'scripts/copy_rq1_catalog.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


@pytest.fixture
def databases(tmp_path, monkeypatch):
    paths = [tmp_path / name / 'catalog.sqlite3' for name in ['source', 'target']]
    for path in paths:
        monkeypatch.setattr(db, 'DB_PATH', path)
        db.init_db()
    with sqlite3.connect(paths[0]) as con:
        for ident, state in [('rq1-pending', 'pending_review'), ('rq1-rejected', 'rejected')]:
            con.execute("INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,sentence_sha256,source_kind,created_at) VALUES(?,?,?,1,?,?,?,?,?,?)", (ident, 'Never change protected files.', 'per-event', 'project', 'repository_instruction', state, ident, 'rq1_corpus', '2026-10-03'))
        con.execute("INSERT INTO meta VALUES('rq1_dataset_identity','fixed-dataset')")
        con.execute("INSERT INTO audit_log VALUES('review-original',NULL,'strategy_review','研究者',?,?)", (json.dumps({'strategy_id': 'rq1-rejected'}), '2026-10-03'))
    monkeypatch.setattr(db, 'DB_PATH', paths[1])
    catalog.create({'text': 'Existing manual policy.', 'category': 'semantic', 'context_scope': 'self-contained', 'execution_layer': 'manual_instruction'}, '研究者')
    return paths


def test_copy_rq1_preserves_rejected_status_original_ids_and_other_records(databases):
    source, target = databases
    before = source.read_bytes()
    result = snapshot.copy_catalog(source, target, 2)
    assert result['inserted_count'] == 2 and result['statuses'] == {'pending_review': 1, 'rejected': 1}
    assert source.read_bytes() == before
    value = catalog.page(source_kind='rq1_corpus')
    assert value['total'] == 2 and {r['id'] for r in value['items']} == {'rq1-pending', 'rq1-rejected'}
    assert catalog.page(source_kind='manual')['total'] == 1
    assert value['catalog']['rq1_count'] == 2 and value['catalog']['snapshot']['kind'] == 'rq1_directory_snapshot'
    with db.connect() as con:
        assert con.execute("SELECT details_json FROM audit_log WHERE id='review-original'").fetchone()


def test_copy_rq1_idempotent_without_overwriting_later_review(databases):
    source, target = databases
    snapshot.copy_catalog(source, target, 2)
    assert snapshot.copy_catalog(source, target, 2)['inserted_count'] == 0
    with db.connect() as con:
        con.execute("UPDATE strategies SET status='approved' WHERE id='rq1-pending'")
    with pytest.raises(ValueError, match='拒绝覆盖'):
        snapshot.copy_catalog(source, target, 2)
    assert catalog.page(status='approved')['total'] == 1


def test_copy_rq1_rejects_wrong_count_or_same_database(databases):
    source, target = databases
    with pytest.raises(ValueError, match='数量'):
        snapshot.copy_catalog(source, target, 721)
    with pytest.raises(ValueError, match='独立'):
        snapshot.copy_catalog(source, source, 2)
    assert catalog.page(source_kind='rq1_corpus')['total'] == 0


@pytest.mark.parametrize('tampered', [False, True])
def test_copy_rq1_verified_source_cache_hash_and_readability(databases, tampered):
    source, target = databases
    data = b'Never change protected files.\n'
    url = 'https://raw.githubusercontent.com/example/repo/' + 'a'*40 + '/AGENTS.md'
    name = hashlib.sha256(url.encode()).hexdigest()
    cache = source.parent / 'source-snapshots'
    cache.mkdir()
    (cache / name).write_bytes(b'changed snapshot' if tampered else data)
    with sqlite3.connect(source) as con:
        con.execute("UPDATE strategies SET source_verified=1,source_repo='example/repo',source_commit=?,source_path='AGENTS.md',source_content_sha256=? WHERE id='rq1-pending'", ('a'*40, hashlib.sha256(data).hexdigest()))
    if tampered:
        with pytest.raises(ValueError, match='hash'):
            snapshot.copy_catalog(source, target, 2)
        assert catalog.page(source_kind='rq1_corpus')['total'] == 0
    else:
        assert snapshot.copy_catalog(source, target, 2)['source_files'] == 1
        copied = target.parent / 'source-snapshots' / name
        assert copied.read_bytes() == data and copied.stat().st_mode & 0o777 == 0o640
