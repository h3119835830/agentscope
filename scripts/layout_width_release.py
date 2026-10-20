"""Publish only the reviewed workspace-width CSS; retain live JavaScript."""
import argparse
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from deploy_policy_semantics import authority, service, sha, guard, api, files
from connection_layout_release import ROOT, UI, API, BROKER, ENGINE, git

BASE_INDEX = '3fdd68b075d0577a251aa086b3ed36c55db18c7df0130f658be0e31039f8931a'
OLD = '/assets/main-CIQeSv1W.css'
NEW = '/assets/main-CXG-2KhO.css'
OLD_SHA = 'ab9013413d0b280127bdb9cf041adebfb679c9d157ec5a8ff2ff556fc8783ca8'
NEW_SHA = '0ecf7cd7fa62cca1310968070dbf01c4e925ceec2bdb399f0a8b93a03508aa4d'
SOURCE_FILES = ('frontend/src/recordVisuals.css', 'frontend/src/unifiedPolicyLibrary.css')


def read_live(path):
    with urllib.request.urlopen('http://127.0.0.1:18003'+path, timeout=15) as response:
        return response.read(), response.headers.get('Content-Type', 'application/octet-stream')


def payload():
    index, _ = read_live('/')
    old, _ = read_live(OLD)
    new = (ROOT/'frontend/dist'/NEW.lstrip('/')).read_bytes()
    assert hashlib.sha256(index).hexdigest() == BASE_INDEX, 'Live entry changed; review before publication'
    assert hashlib.sha256(old).hexdigest() == OLD_SHA and hashlib.sha256(new).hexdigest() == NEW_SHA
    changes = {
        b'.record-badge{display:inline-flex;': (b'.prototype-theme .main[data-page] .content{width:100%;max-width:none;min-width:0}'
            b'.prototype-theme .main[data-page=workbench] :is(.policy-assistant,.policy-reference-select){width:100%;max-width:none;min-width:0}.record-badge{display:inline-flex;'),
        b'.prototype-theme .main[data-page]:not([data-page=overview]) .content{max-width:1440px;':
            b'.prototype-theme .main[data-page]:not([data-page=overview]) .content{',
        b'.unified-policy-library .upl-template-library>table{min-width:0;':
            b'.unified-policy-library .upl-template-library>table{min-width:100%;',
    }
    for before, after in changes.items():
        assert old.count(before) == 1
        old = old.replace(before, after)
    assert old == new, 'Built CSS contains unrelated changes'
    assert index.count(OLD.encode()) == 1
    return index.replace(OLD.encode(), NEW.encode()), new


class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?', 1)[0] == '/':
            body, _ = payload()
            status, content_type = 200, 'text/html; charset=utf-8'
        elif self.path == NEW:
            _, body = payload()
            status, content_type = 200, 'text/css'
        else:
            request = urllib.request.Request('http://127.0.0.1:18003'+self.path,
                headers={k: self.headers[k] for k in ('X-AgentScope-Surface',) if k in self.headers})
            try:
                response = urllib.request.urlopen(request, timeout=15)
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
        self.send_error(405, 'Read-only preview')

    do_POST = do_PUT = do_PATCH = do_DELETE = deny


def publish():
    assert os.geteuid() == 0 and git('branch', '--show-current').strip() == b'main'
    assert not git('diff', 'HEAD', '--', *SOURCE_FILES, 'scripts/layout_width_release.py').strip()
    body, css = payload()
    guard()
    identities, rules, engine = (service(API), service(BROKER)), authority(), sha(ENGINE)
    existing = files(UI)
    assert existing['index.html'] == BASE_INDEX
    backup = UI.parent/'release-backups'/('layout-width-'+time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700, parents=True)
    shutil.copy2(UI/'index.html', backup/'index.html')
    result = dict(published=False, source_commit=git('rev-parse', 'HEAD').decode().strip(),
        publication='workspace-width-css-only', service_restart=False, agent_actions=False,
        policy_application=False, css_sha256=NEW_SHA)
    try:
        target = UI/NEW.lstrip('/')
        if target.exists():
            assert sha(target) == NEW_SHA
        else:
            target.write_bytes(css)
            target.chmod(0o644)
        assert sha(UI/'index.html') == BASE_INDEX
        temporary = UI/'index.html.layout-width-upload'
        with temporary.open('xb') as output:
            output.write(body)
        temporary.chmod(0o644)
        os.replace(temporary, UI/'index.html')
        assert read_live('/')[0] == body and read_live(NEW)[0] == css and api('/api/health')['ok']
        assert identities == (service(API), service(BROKER)) and rules == authority() and engine == sha(ENGINE)
        assert all(sha(UI/name) == digest for name, digest in existing.items() if name != 'index.html')
        result.update(published=True, index_sha256=sha(UI/'index.html'), api_broker_unchanged=True,
            authority_unchanged=True, engine_unchanged=True, javascript_unchanged=True)
    except BaseException:
        temporary = UI/'index.html.layout-width-rollback'
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
    group.add_argument('--preview', action='store_true')
    group.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.preview:
        payload()
        ThreadingHTTPServer(('127.0.0.1', 18178), Preview).serve_forever()
    else:
        publish()
