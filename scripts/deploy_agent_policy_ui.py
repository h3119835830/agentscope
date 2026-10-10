"""18003 static-only delivery. Keeps old hashed assets and never restarts a service."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,time

ROOT=Path(__file__).resolve().parents[1]
LIVE=Path('/var/lib/agentscope-scope-demo/ui')
parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
dist=ROOT/'frontend/dist'
assert LIVE.resolve()==Path('/var/lib/agentscope-scope-demo/ui')
assert (dist/'index.html').is_file() and (dist/'assets').is_dir()
files=[f for f in dist.rglob('*') if f.is_file()]
assert all(f.relative_to(dist).parts[0] in ('assets','index.html','vite.svg') for f in files)
if not args.apply:
    print('Static delivery ready: '+str(len(files))+' files; no API, Broker, Agent, or policy application action')
else:
    assert os.geteuid()==0,'Static directory requires its service owner/root'
    backup=LIVE.parent/'ui-backups'/('agent-policy-'+time.strftime('%Y%m%d-%H%M%S'))
    shutil.copytree(LIVE,backup)
    # Hashed assets first, index atomically last. Existing open tabs can still read their old assets.
    for source in files:
        if source.name=='index.html':continue
        dest=LIVE/source.relative_to(dist);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    temporary=LIVE/'index.html.agent-policy-new';shutil.copyfile(dist/'index.html',temporary);temporary.replace(LIVE/'index.html')
    assert all(hashlib.sha256(f.read_bytes()).digest()==hashlib.sha256((LIVE/f.relative_to(dist)).read_bytes()).digest() for f in files)
    print('Static UI delivered; backup: '+str(backup))
