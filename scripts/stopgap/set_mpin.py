# ruff: noqa  -- reference copy of a server stopgap (scripts/stopgap/README in docs/CURSOR_NEXT.md); not engine code
import getpass, os, sys
from pathlib import Path
sys.path.insert(0, os.getcwd())
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        if k.strip() != "TZ":
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
from config.secrets_loader import save_key
p = getpass.getpass("New Angel MPIN (hidden): ").strip()
if not (len(p) == 4 and p.isdigit()):
    sys.exit("Not saved: the MPIN must be exactly 4 digits.")
if p != getpass.getpass("Type it again: ").strip():
    sys.exit("Not saved: the two entries differ.")
save_key("angel_pin", p)
print("Saved angel_pin to the server database.")
