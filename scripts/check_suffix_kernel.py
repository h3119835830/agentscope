#!/usr/bin/env python3
"""Isolated kernel smoke probe. No console, user Agent or production pin access."""
import json,os,subprocess,tempfile,uuid
from pathlib import Path

def main():
    if os.getuid()!=0:raise SystemExit('Requires root for isolated BPF load')
    root=Path(tempfile.mkdtemp(prefix='agentscope-suffix-'))
    pin=Path('/sys/fs/bpf')/('agentscope-suffix-test-'+uuid.uuid4().hex)
    binary=Path(__file__).resolve().parents[1]/'actplane/target/release/actplane'
    deep=root/('deep-'+'x'*80)/('nested-'+'y'*80)
    deep.mkdir(parents=True);(deep/'production.env').write_text('synthetic-canary')
    source='source AGENT = exec "**/python3"\nrule suffix:\n block open file "**/*.env" if AGENT\n because "Isolated suffix probe"\n'
    policy=root/'policy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+x+'\n' for x in source.splitlines()))
    code='import os,json; p='+repr(str(deep/'production.env'))+'\ntry:\n open(p).read(); print("UNEXPECTED_READ")\nexcept PermissionError:\n print("BLOCKED")\n'
    env={**os.environ,'ACTPLANE_BPF_PIN_ROOT':str(pin),'ACTPLANE_RESERVE_PATH_SUFFIX':'1','ACTPLANE_RESERVE_OPEN_RULES':'1','SUDO_UID':'65534','SUDO_GID':'65534'}
    root.chmod(0o755)
    try:
        result=subprocess.run([str(binary),'--policy',str(policy),'run','/usr/bin/python3','-c',code],cwd=root,env=env,capture_output=True,text=True,timeout=100)
        (root/'stdout').write_text(result.stdout);(root/'stderr').write_text(result.stderr)
        print(json.dumps({'root':str(root),'pin':str(pin),'returncode':result.returncode,'stdout':result.stdout,'stderr_tail':result.stderr[-2500:]}))
    except subprocess.TimeoutExpired as error:
        (root/'stderr').write_bytes(error.stderr or b'')
        print(json.dumps({'root':str(root),'pin':str(pin),'timeout':True}))
    finally:
        # Only this probe's fresh, explicit pin directory. Unpinning releases its
        # links; never enumerate or touch another engine's pins.
        import shutil
        if pin.parent==Path('/sys/fs/bpf') and pin.name.startswith('agentscope-suffix-test-') and pin.exists():shutil.rmtree(pin)

if __name__=='__main__':main()
