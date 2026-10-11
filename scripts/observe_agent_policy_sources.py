"""Root-owned, read-only /proc sampler for the unprivileged 18003 control API.

Only admitted open Agent identities are sampled. No argv, environ, credentials,
commands, network, database writes or policy/runtime operations.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import sqlite3
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from agentscope_app.instances.policy_sources import process_executable, IDENTITY
DATABASE=Path('/var/lib/agentscope-scope-demo/demo.sqlite3')
OUTPUT=Path('/run/agentscope-scope-demo/policy-source-facts.json')


def collect(database=DATABASE):
    sources={}
    with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as con:
        rows=con.execute("SELECT id,generation,runtime_json FROM agent_instances WHERE mode='controlled' AND gate='open' LIMIT 1000").fetchall()
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    for ident,generation,raw in rows:
        try:
            runtime=json.loads(raw)
            if runtime.get('generation')!=generation or not runtime.get('verified') or runtime.get('boot_id')!=boot:
                continue
            identity={k:runtime[k] for k in IDENTITY}
            executable=process_executable(identity['pid'],identity['start_ticks'],identity['boot_id'])
            sources[ident]={**identity,'executable':executable}
        except (ValueError,KeyError,OSError):
            continue
    return {'boot_id':boot,'observed_monotonic':time.monotonic(),'sources':sources}


def publish(snapshot):
    assert os.geteuid()==0
    gid=pwd.getpwnam('agentscope-api').pw_gid
    fd,name=tempfile.mkstemp(prefix='.policy-source-',dir=OUTPUT.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            os.fchown(stream.fileno(),0,gid);os.fchmod(stream.fileno(),0o640)
            json.dump(snapshot,stream);stream.flush();os.fsync(stream.fileno())
        os.replace(name,OUTPUT)
    finally:
        Path(name).unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    while True:
        publish(collect())
        if args.once:break
        time.sleep(2)
