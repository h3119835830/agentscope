#!/usr/bin/env python3
"""Copy an existing RQ1 directory snapshot into a separate development database."""
import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def copy_catalog(source_db, target_db, expected_count, source_label="原策略库"):
    source_db, target_db = Path(source_db).resolve(), Path(target_db).resolve()
    if source_db == target_db:
        raise ValueError("来源与目标数据库必须独立")
    if not source_db.is_file() or not target_db.is_file():
        raise ValueError("来源和目标数据库必须已初始化")
    source = sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(target_db, timeout=30)
    target.row_factory = sqlite3.Row
    target.execute("PRAGMA foreign_keys=ON")
    try:
        source.execute("BEGIN")
        rows = [dict(r) for r in source.execute("SELECT * FROM strategies WHERE source_kind='rq1_corpus' ORDER BY id")]
        if len(rows) != expected_count:
            raise ValueError("RQ1 原库数量与预期不一致")
        if source.execute("SELECT COUNT(*) FROM strategy_statement_versions WHERE strategy_id IN (SELECT id FROM strategies WHERE source_kind='rq1_corpus')").fetchone()[0]:
            raise ValueError("源 RQ1 已有转换版本，目录快照工具不能遗漏其版本关系")
        ids = {row['id'] for row in rows}
        revisions = [dict(r) for r in source.execute("SELECT * FROM strategy_revisions WHERE strategy_id IN (SELECT id FROM strategies WHERE source_kind='rq1_corpus') ORDER BY id")]
        audits = []
        for row in source.execute("SELECT * FROM audit_log ORDER BY id"):
            detail = json.loads(row['details_json'])
            if not row['task_id'] and (detail.get('strategy_id') in ids or row['action'] == 'rq1_corpus_import'):
                audits.append(dict(row))
        meta = {r[0]: r[1] for r in source.execute("SELECT key,value FROM meta WHERE key IN ('rq1_dataset_identity','rq1_imported_at')")}
        files = {}
        for row in rows:
            if not row['source_verified']:
                continue
            url = f"https://raw.githubusercontent.com/{row['source_repo']}/{row['source_commit']}/{row['source_path']}"
            name = hashlib.sha256(url.encode()).hexdigest()
            path = source_db.parent / 'source-snapshots' / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("已核验 RQ1 原文快照缺失")
            data = path.read_bytes()
            if hashlib.sha256(data.decode('utf-8', errors='replace').encode()).hexdigest() != row['source_content_sha256']:
                raise ValueError("RQ1 原文快照 hash 不一致")
            files[name] = data
        before = [dict(r) for r in target.execute("SELECT * FROM strategies ORDER BY id")]
        backups = target_db.parent / 'backups'
        backups.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = backups / ('pre-rq1-catalog-' + stamp + '.sqlite3')
        with sqlite3.connect(backup) as saved:
            target.backup(saved)
        backup.chmod(0o600)
        target.execute("BEGIN IMMEDIATE")
        inserted = 0
        for table, records in [('strategies', rows), ('strategy_revisions', revisions), ('audit_log', audits)]:
            for row in records:
                existing = target.execute('SELECT * FROM ' + table + ' WHERE id=?', (row['id'],)).fetchone()
                if existing:
                    if any(existing[k] != v for k, v in row.items()):
                        raise ValueError("目标已有不同内容或审核状态，拒绝覆盖")
                    continue
                columns = ','.join('"' + key + '"' for key in row)
                target.execute('INSERT INTO ' + table + '(' + columns + ') VALUES(' + ','.join(['?'] * len(row)) + ')', list(row.values()))
                if table == 'strategies':
                    inserted += 1
        for key, value in meta.items():
            existing = target.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
            if existing and existing[0] != value:
                raise ValueError("目标已有不同 RQ1 数据集，拒绝覆盖")
            target.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', (key, value))
        cache = target_db.parent / 'source-snapshots'
        cache.mkdir(exist_ok=True)
        owner = target_db.parent.stat()
        for name, data in files.items():
            dest = cache / name
            if dest.is_symlink() or dest.exists() and dest.read_bytes() != data:
                raise ValueError("目标原文快照冲突")
            if not dest.exists():
                with dest.open('xb') as handle:
                    handle.write(data)
                dest.chmod(0o640)
                if os.geteuid() == 0:
                    os.chown(dest, owner.st_uid, owner.st_gid)
        if os.geteuid() == 0:
            os.chown(cache, owner.st_uid, owner.st_gid)
        restored = [dict(r) for r in target.execute("SELECT * FROM strategies WHERE source_kind='rq1_corpus' ORDER BY id")]
        if restored != rows:
            raise ValueError("目标 RQ1 目录与原库不一致")
        for row in before:
            if dict(target.execute('SELECT * FROM strategies WHERE id=?', (row['id'],)).fetchone()) != row:
                raise ValueError("目标原记录发生改变")
        snapshot = {'kind': 'rq1_directory_snapshot', 'label': source_label, 'captured_at': datetime.now(timezone.utc).isoformat(), 'record_count': len(rows), 'records_sha256': digest(rows), 'dataset_identity': meta.get('rq1_dataset_identity')}
        target.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('history_catalog_snapshot', json.dumps(snapshot, ensure_ascii=False)))
        target.commit()
        return {'source_count': len(rows), 'inserted_count': inserted, 'reused_count': len(rows) - inserted, 'statuses': {state: sum(r['status'] == state for r in rows) for state in sorted({r['status'] for r in rows})}, 'source_verified': sum(r['source_verified'] for r in rows), 'source_files': len(files), 'records_sha256': digest(rows), 'existing_target_preserved': True, 'backup': str(backup)}
    except Exception:
        target.rollback()
        raise
    finally:
        target.close()
        source.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', required=True)
    parser.add_argument('--target-db', required=True)
    parser.add_argument('--expected-count', type=int, required=True)
    parser.add_argument('--source-label', default='原策略库')
    args = parser.parse_args()
    print(json.dumps(copy_catalog(args.source_db, args.target_db, args.expected_count, args.source_label), ensure_ascii=False))
