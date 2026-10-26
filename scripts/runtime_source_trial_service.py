#!/usr/bin/env python3
"""Reuse the existing acceptance launcher with a separate namespace and port."""
import memory_runtime_service as service
from pathlib import Path

TAG='runtime-source-trial-20261026'
service.CODE=Path('/opt/agentscope-'+TAG)
service.STATE=Path('/var/lib/agentscope-'+TAG)
service.TASKS=Path('/rtp')
service.ACTPLANE=Path('/opt/agentscope-runtime-source-engine-20261026/bin/actplane')
original=service.environment
def environment():
    value=original()
    value.update(AGENTSCOPE_RUNTIME_SOURCE_TOOLS='1',AGENTSCOPE_RUNTIME_DIR='/run/agentscope-'+TAG,
      AGENTSCOPE_BROKER_SOCKET='/run/agentscope-'+TAG+'/broker.sock',AGENTSCOPE_PUBLIC_URL='http://127.0.0.1:18007',
      ACTPLANE_BPF_PIN_ROOT='/sys/fs/bpf/agentscope-'+TAG,AGENTSCOPE_MEMORY_ROOT='/var/lib/dsh-runtime-source-trial-20261026')
    return value
service.environment=environment
if __name__=='__main__':service.main()
