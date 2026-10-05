"""Build private Demo UI; restore other instances' static UI from a fixed baseline."""
import io
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path
from scope_service import ROOT, STATE

NODE="/opt/agentscope/bin/node"
VITE=ROOT/"frontend/node_modules/vite/bin/vite.js"
subprocess.run([NODE,str(VITE),"build","--outDir",str(STATE/"ui")],cwd=ROOT/"frontend",check=True)
with tempfile.TemporaryDirectory(prefix="scope-legacy-ui-",dir=STATE) as temporary:
    legacy_ref=os.getenv("AGENTSCOPE_LEGACY_UI_REF","9d54f92")
    raw=subprocess.check_output(["git","-c","safe.directory="+str(ROOT),"archive",legacy_ref,"frontend"],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive: archive.extractall(temporary,filter="data")
    frontend=Path(temporary)/"frontend"
    (frontend/"node_modules").symlink_to(ROOT/"frontend/node_modules",target_is_directory=True)
    subprocess.run([NODE,str(VITE),"build","--outDir",str(ROOT/"frontend/dist")],cwd=frontend,check=True)
