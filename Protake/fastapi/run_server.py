"""
Start the FastAPI dev server with the correct site-packages path.
Usage: python run_server.py [--port 8000] [--no-reload]

Sets PYTHONPATH so uvicorn subprocesses (reload workers) also find
the project venv's sqlalchemy/psycopg packages.
"""
import sys, os, argparse

_here = os.path.dirname(os.path.abspath(__file__))
_venv_sp = os.path.join(_here, "venv", "Lib", "site-packages")

# Inject into OS-level PYTHONPATH so reload-spawned subprocesses inherit it.
existing = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = f"{_venv_sp};{_here}" + (f";{existing}" if existing else "")

# Also patch sys.path for this process.
if _venv_sp not in sys.path:
    sys.path.insert(0, _venv_sp)

import uvicorn

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--no-reload", action="store_true")
args = parser.parse_args()

os.chdir(_here)

uvicorn.run(
    "app.main:app",
    host=args.host,
    port=args.port,
    reload=not args.no_reload,
    reload_dirs=["app"],
)
