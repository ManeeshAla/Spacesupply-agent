"""Central configuration (override with environment variables or backend/.env)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = BASE_DIR / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)

# Load backend/.env (and the repo-root .env) if present; real env vars always win.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR.parent / ".env")
except Exception:  # python-dotenv missing -> plain environment variables only
    pass

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

# ---- Gemini supervisor (free tier). Without a key the chat stays on the Micro LM. ----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "25"))
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
MAX_TOOL_STEPS = int(os.getenv("MAX_TOOL_STEPS", "6"))      # tool-calling rounds per question
CHAT_HISTORY_TURNS = int(os.getenv("CHAT_HISTORY_TURNS", "8"))  # user+assistant turns kept in memory
CONFIRM_ACTIONS = os.getenv("CONFIRM_ACTIONS", "1") == "1"  # ask before simulation/state changes
CHAT_EVAL_PATH = ARTIFACT_DIR / "chat_eval.json"
