#!/usr/bin/env python3
"""Dedicated reliability/value laboratory; never controls the 18003 services."""
import argparse
from pathlib import Path
import system_policy_acceptance_service as service

service.SOURCE=Path('/opt/asvalue-accept-20261012')
service.STATE=Path('/var/lib/asvalue-accept-20261012')
service.TASKS=Path('/avt')
service.RUNTIME=Path('/run/asvalue-accept-20261012')
service.PORT=18163
base_environment=service.environment
def environment():
    return {**base_environment(),'ACTPLANE_BPF_PIN_ROOT':'/sys/fs/bpf/asvalue-accept-20261012'}
service.environment=environment

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('start','stop'))
    parser.add_argument('--kernel-report',default='/var/lib/agentscope-scope-demo/bin/actplane.capabilities.json')
    options=parser.parse_args()
    if options.action=='start':service.start(options.kernel_report)
    else:service.stop()
