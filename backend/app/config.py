"""Central configuration (override with environment variables)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = BASE_DIR / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)

# SQLite by default (zero setup). For PostgreSQL set e.g.
# DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/spacesupply
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'spacesupply.db'}")

# Optional Qwen language layer served by Ollama (falls back to templates if unreachable)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5:3b-instruct")
USE_QWEN = os.getenv("USE_QWEN", "auto")  # auto | on | off

MICROLM_PATH = ARTIFACT_DIR / "microlm.pt"
MICROLM_METRICS = ARTIFACT_DIR / "microlm_metrics.json"
BENCHMARK_PATH = ARTIFACT_DIR / "benchmark.json"

SOLVER_TIME_LIMIT_S = float(os.getenv("SOLVER_TIME_LIMIT_S", "8"))
SUPERVISOR_INTERVAL_S = int(os.getenv("SUPERVISOR_INTERVAL_S", "15"))
SUPERVISOR_ENABLED = os.getenv("SUPERVISOR_ENABLED", "1") == "1"
