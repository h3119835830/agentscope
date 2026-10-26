#!/usr/bin/env python3
"""Create an inherited least-privilege reader, then permanently drop API UID."""
import grp
import os
from pathlib import Path
import pwd
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from reference_reader_channel import launch,FD_ENV

def main():
    if os.geteuid()!=0:raise SystemExit('The trusted systemd launcher must start as root')
    api=pwd.getpwnam(os.environ.get('AGENTSCOPE_API_USER','agentscope'))
    reader=pwd.getpwnam(os.environ['AGENTSCOPE_REFERENCE_READER_USER'])
    group=grp.getgrnam(os.environ['AGENTSCOPE_REFERENCE_READER_GROUP'])
    if not api.pw_uid or not reader.pw_uid or api.pw_uid==reader.pw_uid:
        raise SystemExit('API and reader require distinct unprivileged identities')
    print('Reader launcher: '+str({k:v for k,v in (line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line) if k in ('Uid','Gid','CapEff','Groups')}),flush=True)
    channel,process=launch('/usr/bin/python3',reader.pw_uid,group.gr_gid)
    os.environ[FD_ENV]=str(channel.fileno())
    os.initgroups(api.pw_name,api.pw_gid)
    os.setgid(api.pw_gid)
    os.setuid(api.pw_uid)
    os.chdir(root)
    os.execv(sys.executable,[sys.executable,'-m','uvicorn','agentscope_app.main:app',
                           '--host','127.0.0.1','--port','18003','--timeout-graceful-shutdown','3'])

if __name__=='__main__':main()
