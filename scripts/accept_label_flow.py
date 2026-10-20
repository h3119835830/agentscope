"""Isolated synthetic runtime acceptance; never contacts non-loopback targets."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]


def worker(mode, folder, port):
    folder=Path(folder)
    if mode=='writer':
        value=(folder/'secret.txt').read_bytes()
        (folder/'derived.txt').write_bytes(value)
        return
    if mode in ('reader','renamed-reader','inherited'):
        value=b'public-after-inheritance' if mode=='inherited' else (folder/('renamed.txt' if mode=='renamed-reader' else 'derived.txt')).read_bytes()
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=2) as conn:
                conn.sendall(value)
            print('SECRET_CONNECT_ALLOWED',flush=True)
            sys.exit(3)
        except PermissionError:
            print('SECRET_CONNECT_BLOCKED',flush=True)
            return
    if mode=='control':
        with socket.create_connection(('127.0.0.1',port),timeout=2) as conn:
            conn.sendall(b'public-control')
        print('CONTROL_ALLOWED',flush=True)
        return
    if mode in ('workload','rename-workload','replace-workload','inherit-workload'):
        if mode=='inherit-workload':
            (folder/'secret.txt').read_bytes()
            child=os.fork()
            if child==0:os.execv(sys.executable,[sys.executable,__file__,'inherited',str(folder),str(port)])
            _,status=os.waitpid(child,0)
            if os.waitstatus_to_exitcode(status)!=0:sys.exit(4)
            time.sleep(.4);return
        for child in ('control','writer','reader'):
            if child=='reader' and mode=='rename-workload':
                (folder/'derived.txt').rename(folder/'renamed.txt');child='renamed-reader'
            if child=='reader' and mode=='replace-workload':
                (folder/'replacement.txt').write_bytes(b'public-replacement')
                os.replace(folder/'replacement.txt',folder/'derived.txt')
                # A new object at the same name must not inherit the old inode's
                # SECRET. The independent parent has never read the source.
                child='replacement-reader'
            subprocess.run([sys.executable,__file__,child,str(folder),str(port)],check=True)
        # Let the bounded collector drain before the harness exits.
        time.sleep(.4)
    if mode=='replacement-reader':
        value=(folder/'derived.txt').read_bytes()
        with socket.create_connection(('127.0.0.1',port),timeout=2) as conn:conn.sendall(value)
        print('REPLACEMENT_ALLOWED',flush=True)


def accept(scenario='main'):
    folder=Path(tempfile.mkdtemp(prefix='as-flow-'))
    (folder/'secret.txt').write_bytes(b'SYNTHETIC_SECRET_NOT_A_CREDENTIAL')
    server=socket.socket()
    server.bind(('127.0.0.1',0));server.listen();server.settimeout(.1)
    port=server.getsockname()[1]
    received=[];done=threading.Event()
    def receive():
        while not done.is_set():
            try:
                conn,_=server.accept()
                with conn:
                    conn.settimeout(2)
                    received.append(conn.recv(4096))
            except socket.timeout:pass
    thread=threading.Thread(target=receive);thread.start()
    policy=f'''source AGENT = exec "**/python3"
source SECRET = file "{folder}/secret.txt"
rule protect:
 block connect endpoint "127.0.0.1" if AGENT and SECRET
 because "Synthetic secret must not reach the loopback receiver"
'''
    pin='/sys/fs/bpf/agentscope-label-flow-'+folder.name
    env={**os.environ,'ACTPLANE_BPF_PIN_ROOT':pin,'ACTPLANE_RESERVE_FILE_FLOW':'1'}
    try:
        start=time.monotonic()
        result=subprocess.run([str(ROOT/'actplane/target/release/actplane'),'--rule',policy,
                               'run','--run-as-root',sys.executable,__file__,
                               {'main':'workload','rename':'rename-workload','replacement':'replace-workload','inheritance':'inherit-workload'}[scenario],
                               str(folder),str(port)],
                              env=env,cwd=folder,capture_output=True,text=True,timeout=90)
        elapsed=time.monotonic()-start
    finally:
        done.set();thread.join(3);server.close()
    files=list(folder.rglob('events.jsonl'))
    events=[json.loads(line) for path in files for line in path.read_text().splitlines() if line]
    violations=[e for e in events if e.get('event')=='taint_violation' and 'SECRET' in e.get('matched_label_names',[])]
    sinks=[e for e in violations if e.get('op')=='connect' and e.get('action')=='block']
    expected=[] if scenario=='inheritance' else [b'public-control',b'public-replacement'] if scenario=='replacement' else [b'public-control']
    provenance_ok=all(e.get('provenance',{}).get('origin_target')==str(folder/'secret.txt') and
                      e.get('provenance_model',{}).get('causal_chain_scope')=='single_hop_origin' and
                      e.get('provenance_model',{}).get('full_causal_chain') is False for e in sinks)
    passed=(result.returncode==0 and received==expected and
            (not sinks if scenario=='replacement' else bool(sinks) and provenance_ok))
    (folder/'collector-stderr.log').write_text(result.stderr)
    report={'passed':passed,'scenario':scenario,'returncode':result.returncode,'elapsed_seconds':elapsed,
            'receiver_matches_expected':received==expected,'receiver_connections':len(received),
            'events':len(events),'native_secret_violations':len(violations),
            'actions':[e.get('action') for e in sinks],
            'provenance_targets':[e.get('provenance',{}).get('origin_target') for e in sinks],
            'single_hop_provenance':provenance_ok if sinks else None,
            'stdout':result.stdout,'stderr_head':result.stderr[:800],'stderr_tail':result.stderr[-1800:],
            'evidence_directory':str(folder),'pin_root':pin}
    (folder/'acceptance.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return 0 if passed else 1


if __name__=='__main__':
    if len(sys.argv)>1 and not sys.argv[1].startswith('--'):worker(sys.argv[1],sys.argv[2],int(sys.argv[3]))
    else:
        parser=argparse.ArgumentParser();parser.add_argument('--scenario',choices=['main','rename','replacement','inheritance'],default='main')
        sys.exit(accept(parser.parse_args().scenario))
