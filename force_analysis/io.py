"""Small deterministic JSON artifacts; exclusive output creation."""
import hashlib
import json
import math
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def bad(value):
        raise ValueError(f"Nonfinite JSON number: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=bad)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite numeric value required")
    return float(value)


def seal(value, key):
    value[key] = identity({k: v for k, v in value.items() if k != key})
    return value


def verify(value, key):
    if value.get(key) != identity({k: v for k, v in value.items() if k != key}):
        raise ValueError(f"{key}: artifact content changed")
    return value


def code_identity():
    root = Path(__file__).parent
    return {p.name: file_hash(p) for p in sorted(root.glob("*.py"))}
