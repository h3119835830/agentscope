"""Reuse the authorized native DeepSeek account without printing its secret."""
import grp
import os
from pathlib import Path
import pwd
import yaml

source=Path('/var/lib/agentscope-agent/controlled-instances/instance-e86886cee6e04d9e/state/.dsh/.credentials.yaml')
value=yaml.safe_load(source.read_text())['refs']['DEEPSEEK_API_KEY']
if not isinstance(value,str) or not value.startswith('sk-'):raise ValueError('Native credential is not configured')
target=Path('/etc/agentscope/policy-model.key')
if target.exists() and target.read_text().strip()!=value:raise ValueError('Dedicated credential already differs; do not overwrite')
target.write_text(value+'\n');os.chown(target,0,grp.getgrnam('agentscope').gr_gid);os.chmod(target,0o640)
native=Path('/var/lib/agentscope-agent/.dsh/.credentials.yaml')
data=yaml.safe_load(native.read_text());data.setdefault('refs',{})['DEEPSEEK_API_KEY']=value
native.write_text(yaml.safe_dump(data));os.chown(native,pwd.getpwnam('agentscope-agent').pw_uid,grp.getgrnam('agentscope-task').gr_gid);os.chmod(native,0o600)
Path('/etc/systemd/system/agentscope-preview.service.d/51-policy-credential.conf').write_text('[Service]\nEnvironment=AGENTSCOPE_POLICY_LLM_KEY_FILE=/etc/agentscope/policy-model.key\n')
print('Dedicated policy credential configured; no credential value emitted.')
