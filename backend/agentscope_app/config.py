from pathlib import Path
import os, shutil

HOME = Path.home()
APP_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = Path(os.getenv("AGENTSCOPE_STATE_DIR", HOME / ".local/state/agentscope"))
DB_PATH = Path(os.getenv("AGENTSCOPE_DB", STATE_DIR / "agentscope.sqlite3"))
TASK_ROOT = Path(os.getenv("AGENTSCOPE_TASK_ROOT", STATE_DIR / "tasks"))
WORKSPACE_ROOT = TASK_ROOT
OUTPUT_ROOT = TASK_ROOT
POLICY_ROOT = Path(os.getenv("AGENTSCOPE_POLICY_DIR", STATE_DIR / "protected/policies"))
CORPUS_ROOT = Path(os.getenv("AGENTSCOPE_CORPUS_ROOT", STATE_DIR / "import/corpus"))
ACTPLANE_BIN = Path(os.getenv("ACTPLANE_BIN", shutil.which("actplane") or "/usr/local/bin/actplane"))
BROKER_SOCKET = Path(os.getenv("AGENTSCOPE_BROKER_SOCKET", "/run/agentscope/broker.sock"))
DSH_BIN = Path(os.getenv("DSH_BIN", shutil.which("dsh") or "/usr/local/bin/dsh"))
DSH_HOME = Path(os.getenv("DSH_HOME", STATE_DIR / "dsh-home"))
UI_DIST = Path(os.getenv("AGENTSCOPE_UI_DIST", APP_ROOT / "frontend/dist"))
RUNTIME_DIR = Path(os.getenv("AGENTSCOPE_RUNTIME_DIR", "/run/agentscope"))
ACTPLANE_COMPAT = os.getenv("ACTPLANE_COMPAT", "")
ADMIN_TOKEN = os.getenv("AGENTSCOPE_ADMIN_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("AGENTSCOPE_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
SERVICE_HOME = Path(os.getenv("AGENTSCOPE_SERVICE_HOME", STATE_DIR))
EXEC_PATH = os.getenv("AGENTSCOPE_EXEC_PATH", f"{ACTPLANE_BIN.parent}:{DSH_BIN.parent}:/usr/local/bin:/usr/bin:/bin")
LOG_DIR = Path(os.getenv("AGENTSCOPE_LOG_DIR", STATE_DIR / "logs"))
_PI_STATE_BIN = STATE_DIR / "pi-runtime/bin/pi"
_PI_BIN = os.getenv("PI_BIN") or shutil.which("pi") or (str(_PI_STATE_BIN) if _PI_STATE_BIN.is_file() else None)
PI_BIN = Path(_PI_BIN) if _PI_BIN else None
try:
    PI_TIMEOUT_SECONDS = max(30, min(int(os.getenv("AGENTSCOPE_PI_TIMEOUT_SECONDS", "240")), 900))
except ValueError:
    PI_TIMEOUT_SECONDS = 240
PI_EXTENSION_PATH = Path(os.getenv("AGENTSCOPE_PI_EXTENSION", APP_ROOT / "integrations/pi-policy-tools/index.ts"))
PI_SKILL_PATH = Path(os.getenv("AGENTSCOPE_PI_SKILL", APP_ROOT / "integrations/pi-policy-tools/skills/task-scope-bootstrap/SKILL.md"))

for directory in (STATE_DIR, WORKSPACE_ROOT, POLICY_ROOT, CORPUS_ROOT, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)
