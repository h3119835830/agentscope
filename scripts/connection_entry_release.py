"""Stage the live UI baseline plus ONLY the accepted connection fixes; no merge."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from deploy_policy_semantics import authority, service, sha, guard, api, files
from connection_layout_release import ROOT, UI, API, BROKER, ENGINE, git

LIVE_BASE = 'b37b4fd'
EXPECTED_INDEX = 'ef1e2ef27e81980937efe0a2e9da8259c9107bf335f2c941ef2daab52bfaa79f'
# A separate notice release landed after our CSS publication. Preserve, not merge, it.
RETAINED = {'src/ProductOverview.jsx': '649a8f07c70444385767c4ccd6049e92e9ac5e3c94191453ff191308dc7a976a'}
RETAINED_SOURCE = Path('/tmp/agentscope-notice-release-LemnwD/frontend')
LIVE_JS_SHA = '4c6cd0cbb36b0b378c3da3bac304bba8a731475aed1716aabceccdca4a44a7ad'
OVERLAYS = ('src/agentInstances.css', 'src/AgentInstances.jsx', 'src/AgentLaunchFields.jsx',
            'src/agentInstancePresentation.mjs', 'src/openAgentPage.mjs', 'src/connectionOpen.mjs')


def sources(path):
    return {str(p.relative_to(path)): sha(p) for p in path.rglob('*')
            if p.is_file() and 'node_modules' not in p.parts and 'dist' not in p.parts}


def stage(prove_baseline=False):
    root = Path(tempfile.mkdtemp(prefix='agentscope-connection-entry-'))
    archive = subprocess.Popen(['git', '-C', str(ROOT), 'archive', LIVE_BASE, 'frontend'], stdout=subprocess.PIPE)
    subprocess.run(['tar', '-x', '-C', str(root)], stdin=archive.stdout, check=True)
    assert archive.wait() == 0
    for rel, digest in RETAINED.items():
        assert sha(RETAINED_SOURCE/rel) == digest
        shutil.copyfile(RETAINED_SOURCE/rel, root/'frontend'/rel)
    for rel in (() if prove_baseline else OVERLAYS):
        shutil.copyfile(ROOT/'frontend'/rel, root/'frontend'/rel)
    manifest = {'baseline': LIVE_BASE, 'retained': RETAINED, 'overlays': {rel: sha(ROOT/'frontend'/rel) for rel in OVERLAYS},
                'sources': sources(root/'frontend')}
    (root/'frontend/node_modules').symlink_to((ROOT/'frontend/node_modules').resolve())
    subprocess.run(['npm', 'run', 'build'], cwd=root/'frontend', check=True)
    manifest['dist'] = files(root/'frontend/dist')
    if prove_baseline:
        js = list((root/'frontend/dist/assets').glob('main-*.js'))
        assert len(js) == 1 and sha(js[0]) == LIVE_JS_SHA, 'Concurrent live source baseline not reproduced'
        print(json.dumps({'baseline_reproduced': True, 'live_js_sha256': LIVE_JS_SHA}))
        return
    (root/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'stage': str(root)}))


def verify(root, committed=False):
    assert root.parent == Path('/tmp') and root.name.startswith('agentscope-connection-entry-')
    manifest = json.loads((root/'manifest.json').read_text())
    assert manifest['baseline'] == LIVE_BASE and set(manifest['overlays']) == set(OVERLAYS) and manifest['retained'] == RETAINED
    assert sources(root/'frontend') == manifest['sources']
    assert files(root/'frontend/dist') == manifest['dist']
    # Validate every source against the live Git baseline plus the exact allowlist.
    tracked = git('ls-tree', '-r', '--name-only', LIVE_BASE, '--', 'frontend').decode().splitlines()
    assert set(manifest['sources']) == {p.removeprefix('frontend/') for p in tracked} | set(OVERLAYS)
    for rel, digest in manifest['sources'].items():
        if rel in RETAINED:
            assert digest == RETAINED[rel], 'Previously published notice changed'
            continue
        expected = (git('show', 'HEAD:frontend/'+rel) if committed else (ROOT/'frontend'/rel).read_bytes()) if rel in OVERLAYS else git('show', LIVE_BASE+':frontend/'+rel)
        assert hashlib.sha256(expected).hexdigest() == digest, 'Unreviewed source: '+rel
    return root/'frontend/dist'


def preview(root):
    dist = verify(root)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dist), **kwargs)

        def proxy(self):
            headers = {key: self.headers[key] for key in ('X-AgentScope-Surface', 'Content-Type') if key in self.headers}
            body = self.rfile.read(int(self.headers.get('Content-Length', '0'))) if self.command == 'POST' else None
            request = urllib.request.Request('http://127.0.0.1:18003'+self.path, data=body, headers=headers, method=self.command)
            try:
                response = urllib.request.urlopen(request, timeout=15)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                data = response.read()
                self.send_response(response.status)
                self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith('/api/'):
                return self.proxy()
            return super().do_GET()

        def do_POST(self):
            if re.fullmatch(r'/api/agent-instances/instance-[a-z0-9]+/(check|open)', self.path):
                return self.proxy()  # Existing Broker checks only; neither starts a process.
            self.send_error(405, 'Preview forbids start/stop, configuration and policy writes')

    ThreadingHTTPServer(('127.0.0.1', 18177), Handler).serve_forever()


def publish(root):
    assert os.geteuid() == 0 and git('branch', '--show-current').strip() == b'main'
    # Parallel work on unrelated files is preserved and never copied to this package.
    assert not git('diff', 'HEAD', '--', *('frontend/'+rel for rel in OVERLAYS),
                   'scripts/connection_entry_release.py').strip(), 'Connection changes must be committed first'
    dist = verify(root, committed=True)
    assert sha(UI/'index.html') == EXPECTED_INDEX
    original = (UI/'index.html').read_bytes()
    assert sha(UI/'assets/main-CUSNOPOG.js') == LIVE_JS_SHA
    new_index = (dist/'index.html').read_bytes()
    pattern = rb'/assets/main-[a-zA-Z0-9_-]+\.js'
    old_js, new_js = re.findall(pattern, original), re.findall(pattern, new_index)
    assert len(old_js) == len(new_js) == 1 and original.replace(old_js[0], new_js[0]) == new_index
    guard()
    identities, rules, engine = (service(API), service(BROKER)), authority(), sha(ENGINE)
    existing = files(UI)
    for name, digest in files(dist).items():
        if name not in ('index.html', new_js[0].decode().lstrip('/')):
            assert existing.get(name) == digest, 'Unrelated UI asset change: '+name
    backup = UI.parent/'release-backups'/('connection-entry-'+time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700, parents=True)
    shutil.copy2(UI/'index.html', backup/'index.html')
    result = dict(published=False, source_commit=git('rev-parse', 'HEAD').decode().strip(),
                  baseline=LIVE_BASE, retained=RETAINED, overlays=list(OVERLAYS), service_restart=False,
                  agent_actions=False, policy_application=False, withheld_commit='0d526d2')
    try:
        name = new_js[0].decode().lstrip('/')
        if (UI/name).exists():
            assert sha(UI/name) == sha(dist/name)
        else:
            shutil.copyfile(dist/name, UI/name)
            (UI/name).chmod(0o644)
        temporary = UI/'index.html.connection-entry-upload'
        with temporary.open('xb') as output:
            output.write(new_index)
        temporary.chmod(0o644)
        os.replace(temporary, UI/'index.html')
        with urllib.request.urlopen('http://127.0.0.1:18003/', timeout=10) as response:
            assert response.read() == new_index
        with urllib.request.urlopen('http://127.0.0.1:18003/'+name, timeout=10) as response:
            assert hashlib.sha256(response.read()).hexdigest() == sha(dist/name)
        assert api('/api/health')['ok']
        assert identities == (service(API), service(BROKER)) and rules == authority() and engine == sha(ENGINE)
        assert all(sha(UI/name) == digest for name, digest in existing.items() if name != 'index.html')
        result.update(published=True, api_broker_unchanged=True, authority_unchanged=True,
                      engine_unchanged=True, index_sha256=sha(UI/'index.html'), asset=name, asset_sha256=sha(UI/name))
    except BaseException:
        temporary = UI/'index.html.connection-entry-rollback'
        shutil.copyfile(backup/'index.html', temporary)
        temporary.chmod(0o644)
        os.replace(temporary, UI/'index.html')
        result['entry_rolled_back'] = True
        raise
    finally:
        evidence = backup/'result.json'
        evidence.write_text(json.dumps(result, indent=2))
        evidence.chmod(0o600)
    print(json.dumps({**result, 'evidence': str(evidence)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--stage', action='store_true')
    group.add_argument('--prove-baseline', action='store_true')
    group.add_argument('--preview', type=Path)
    group.add_argument('--publish', type=Path)
    args = parser.parse_args()
    if args.prove_baseline:
        stage(prove_baseline=True)
    elif args.stage:
        stage()
    elif args.preview:
        preview(args.preview.resolve())
    else:
        publish(args.publish.resolve())
