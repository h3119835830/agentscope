"""Independent compile/matcher checks and public receipts, never policy loading."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import urllib.request


def hashed(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    args = argparse.ArgumentParser()
    args.add_argument('root', type=Path)
    options = args.parse_args()
    root = options.root.resolve()
    release = Path('/opt/agentscope/current').resolve()
    output = root / 'inspection'
    output.mkdir(exist_ok=True)
    if (output / 'public-verification.json').exists():
        raise ValueError('Do not overwrite a completed verification')
    binary = output / 'matcher'
    subprocess.run(['cc', '-O2', '-I', str(release / 'actplane/bpf'),
                    str(root / 'probe_public_policy_match.c'), '-o', str(binary)], check=True)
    report = {'policy_loaded': False, 'agent_started': False,
              'compiler_sha256': hashed(Path('/usr/local/bin/actplane')),
              'matcher_header_sha256': hashed(release / 'actplane/bpf/taint.h'),
              'checks': {}, 'model_runs': [], 'read_receipts': []}
    results = json.loads((root / 'results/report.json').read_text())
    gate = next(case for case in results['cases'] if case['id'] == 'actplane-test-gate')
    for item in gate['result']['items']:
        target = item['parameters']['target']
        for variant, pattern in [('agent-original', target), ('independent-recursive-control', target + '/**')]:
            ident = target.rsplit('/', 1)[-1] + '-' + variant
            # Control copy only: the retained model result is never edited.
            text = 'source A = exec "git"\n' + item['document']['original_dsl'].replace('if AGENT', 'if A').replace('since write "' + target + '"', 'since write "' + pattern + '"')
            blob = output / (ident + '.bin')
            compiled = subprocess.run(['/usr/local/bin/actplane', '--rule', text, 'compile', '--json'], capture_output=True, text=True, timeout=20)
            assert compiled.returncode == 0, compiled.stderr
            emitted = subprocess.run(['/usr/local/bin/actplane', '--rule', text, 'compile', '--out', str(blob)], capture_output=True, text=True, timeout=20)
            assert emitted.returncode == 0, emitted.stderr
            samples = {}
            for path in (target + '/example.py', target + '/nested/example.py'):
                probe = subprocess.run([str(binary), str(blob), path], capture_output=True, text=True, check=True)
                samples[path] = json.loads(probe.stdout)
            report['checks'][ident] = {'input_dsl': text, 'compile': json.loads(compiled.stdout), 'samples': samples,
                                      'blob_sha256': hashed(blob), 'control_is_not_an_agent_result': variant != 'agent-original'}
    mediation = 'source A = exec "git"\nrule migration_probe:\n block open file "/w/0/db/prod.db" if A unless lineage-includes exec "migrate"\n because "isolated compiler capability check"'
    probe = subprocess.run(['/usr/local/bin/actplane', '--rule', mediation, 'compile', '--json'], capture_output=True, text=True, timeout=20)
    report['checks']['mediation-compiler-support'] = {'input_dsl': mediation, 'exit_code': probe.returncode,
                                                      'compile': json.loads(probe.stdout), 'runtime_enforcement_tested': False}
    with sqlite3.connect('file:' + str(root / 'state/agentscope.sqlite3') + '?mode=ro', uri=True) as con:
        for raw, in con.execute("SELECT details_json FROM audit_log WHERE action='template_parameters_generated'"):
            details = json.loads(raw)
            report['model_runs'].append({'scope_id': details['scope_id'], 'metadata': details.get('llm_run')})
        for ident, instance_id, snapshot_json, snapshot_hash in con.execute('SELECT id,instance_id,snapshot_json,snapshot_hash FROM template_workspace_reads'):
            snapshot = json.loads(snapshot_json)
            report['read_receipts'].append({'id': ident, 'instance_id': instance_id, 'snapshot_hash': snapshot_hash,
                                            'binding': snapshot['binding'],
                                            'files': [{k: file.get(k) for k in ('relative_path', 'execution_path', 'byte_size', 'text_hash')} for file in snapshot['files']]})
    with urllib.request.urlopen('http://127.0.0.1:18003/api/policy-templates', timeout=10) as response:
        live_catalog = json.load(response)['catalog']
    isolated = json.loads((root / 'results/catalog.json').read_text())
    report['catalog_matches_live'] = live_catalog == isolated
    assert report['catalog_matches_live'], 'Template catalog differs from live server'
    assert report['checks']['mediation-compiler-support']['exit_code'] == 0
    for name in ('src', 'tests'):
        assert all(sample['matched'] == 0 for sample in report['checks'][name + '-agent-original']['samples'].values())
        assert all(sample['matched'] > 0 for sample in report['checks'][name + '-independent-recursive-control']['samples'].values())
    (output / 'public-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'catalog_matches_live': report['catalog_matches_live'],
                      'verified_model_runs': len(report['model_runs']), 'read_receipts': len(report['read_receipts']),
                      'original_directory_patterns_miss_children': True, 'recursive_controls_match_children': True,
                      'mediation_compiler_supported': True, 'policy_loaded': False}))


if __name__ == '__main__':
    main()
