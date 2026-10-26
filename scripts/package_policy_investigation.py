"""Package tracked source plus explicit reviewed tool changes; no local secrets."""
import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import zipfile

FILES=[
 'backend/agentscope_app/instances/policy_context_agent.py',
 'backend/agentscope_app/instances/pi_provider.py',
 'backend/agentscope_app/instances/template_tools.py',
 'backend/agentscope_app/instances/template_configurations.py',
 'backend/agentscope_app/instances/workspace_references.py',
 'backend/agentscope_app/instances/policy_investigation.py',
 'backend/policy_match_preview.c',
 'backend/tests/test_policy_investigation.py',
 'scripts/accept_policy_investigation.py',
]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    if args.output.exists():raise ValueError('Do not overwrite a staged source package')
    root=Path(__file__).resolve().parents[1]
    archive=subprocess.check_output(['git','archive','--format=zip','HEAD'],cwd=root)
    with zipfile.ZipFile(io.BytesIO(archive)) as original,zipfile.ZipFile(args.output,'w',compression=zipfile.ZIP_DEFLATED) as output:
        for entry in original.infolist():
            if entry.filename not in FILES:output.writestr(entry,original.read(entry.filename))
        for name in FILES:output.write(root/name,name)
    print(str(args.output.resolve()),hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__=='__main__':main()
