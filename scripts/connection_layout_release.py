"""CSS-only 18003 overlay. Preview proxies GET only; publication never restarts."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from deploy_policy_semantics import authority, service, sha, guard, api

ROOT = Path(__file__).resolve().parents[1]
UI = Path('/var/lib/agentscope-scope-demo/ui')
INDEX_SHA = '8509054a4346c63ea286d70ba9202c80634b799a502d359737eef46b267c0aea'
OLD = '/assets/main-B3FuXDHH.css'
NEW = '/assets/main-CIQeSv1W.css'
NEW_SHA = 'ab9013413d0b280127bdb9cf041adebfb679c9d157ec5a8ff2ff556fc8783ca8'
BASE = '0d526d2'
API = 'agentscope-scope-demo-api.service'
BROKER = 'agentscope-scope-demo-broker.service'
ENGINE = Path('/var/lib/agentscope-scope-demo/bin/actplane')


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory='+str(ROOT), '-C', str(ROOT), *args])


def payload():
    original = (UI/'index.html').read_bytes()
    assert sha(UI/'index.html') == INDEX_SHA, 'Live UI changed; re-review before publication'
    new_css = ROOT/'frontend/dist'/NEW.lstrip('/')
    assert sha(new_css) == NEW_SHA, 'CSS does not match accepted build'
    old_css = (UI/OLD.lstrip('/')).read_bytes()
    new_bytes = new_css.read_bytes()
    # The complete build differs by exactly the compact connection CSS insertion.
    offset = next(i for i, (a, b) in enumerate(zip(old_css, new_bytes)) if a != b)
    size = len(new_bytes) - len(old_css)
    assert size == 1021 and old_css == new_bytes[:offset]+new_bytes[offset+size:]
    assert original.count(OLD.encode()) == 1
    return original.replace(OLD.encode(), NEW.encode()), new_css


class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        # Serve exactly the live JS/other assets, substituting only one stylesheet.
        if self.path.split('?', 1)[0] == '/':
            body, _ = payload()
            status, content_type = 200, 'text/html; charset=utf-8'
        elif self.path == NEW:
            _, source = payload()
            body, status, content_type = source.read_bytes(), 200, 'text/css'
        else:
            headers = {key: self.headers[key] for key in ('X-AgentScope-Surface',) if key in self.headers}
            request = urllib.request.Request('http://127.0.0.1:18003'+self.path, headers=headers)
            try:
                response = urllib.request.urlopen(request, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                body, status, content_type = response.read(), response.status, response.headers.get('Content-Type', 'application/octet-stream')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def deny(self):
        self.send_error(405, 'Read-only preview: no lifecycle, configuration or policy writes')

    do_POST = do_PUT = do_PATCH = do_DELETE = deny


def publish():
    assert os.geteuid() == 0
    assert git('branch', '--show-current').strip() == b'main'
    assert not git('status', '--porcelain').strip(), 'Commit accepted changes first'
    changed = set(git('diff', '--name-only', BASE, 'HEAD', '--', 'frontend').decode().splitlines())
    assert changed == {'frontend/src/agentInstances.css', 'frontend/src/connectionLayout.test.mjs'}
    body, css = payload()
    guard()
    identities = service(API), service(BROKER)
    rules = authority()
    engine_hash = sha(ENGINE)
    old_files = {str(p.relative_to(UI)): sha(p) for p in UI.rglob('*') if p.is_file()}
    backup = UI.parent/'release-backups'/('connection-layout-'+time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700, parents=True)
    shutil.copy2(UI/'index.html', backup/'index.html')
    result = dict(published=False, source_commit=git('rev-parse', 'HEAD').decode().strip(),
                  publication='connection-settings-css-only', unchanged_js='/assets/main-DImLISr8.js',
                  service_restart=False, agent_actions=False, policy_application=False)
    try:
        target = UI/NEW.lstrip('/')
        if target.exists():
            assert sha(target) == NEW_SHA
        else:
            shutil.copyfile(css, target)
            target.chmod(0o644)
        assert sha(UI/'index.html') == INDEX_SHA
        temporary = UI/'index.html.connection-layout-upload'
        with temporary.open('xb') as output:
            output.write(body)
        temporary.chmod(0o644)
        os.replace(temporary, UI/'index.html')
        with urllib.request.urlopen('http://127.0.0.1:18003/', timeout=10) as response:
            assert response.read() == body
        with urllib.request.urlopen('http://127.0.0.1:18003'+NEW, timeout=10) as response:
            assert hashlib.sha256(response.read()).hexdigest() == NEW_SHA
        assert api('/api/health')['ok']
        assert identities == (service(API), service(BROKER))
        assert authority() == rules and sha(ENGINE) == engine_hash
        assert all(sha(UI/name) == digest for name, digest in old_files.items() if name != 'index.html')
        assert {str(p.relative_to(UI)) for p in UI.rglob('*') if p.is_file()} == set(old_files) | {NEW.lstrip('/')}
        result.update(published=True, index_sha256=sha(UI/'index.html'), css_sha256=NEW_SHA,
                      api_broker_unchanged=True, authority_unchanged=True, engine_unchanged=True,
                      other_assets_unchanged=True)
    except BaseException:
        temporary = UI/'index.html.connection-layout-rollback'
        shutil.copyfile(backup/'index.html', temporary)
        temporary.chmod(0o644)
        os.replace(temporary, UI/'index.html')
        result['entry_rolled_back'] = True
        raise
    finally:
        report = backup/'result.json'
        report.write_text(json.dumps(result, indent=2)+'\n')
        report.chmod(0o600)
    print(json.dumps({**result, 'evidence': str(report)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--preview', action='store_true')
    group.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.preview:
        payload()
        ThreadingHTTPServer(('127.0.0.1', 18176), Preview).serve_forever()
    else:
        publish()
