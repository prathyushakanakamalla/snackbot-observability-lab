"""Central settings. Everything tunable lives here so later experiments can change one value at a time."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- LLM (Groq) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))

# --- Retrieval ---
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))        # characters
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))  # characters
TOP_K = int(os.getenv("TOP_K", "4"))

# --- Tracing (Phase 1) ---
TRACING = os.getenv("TRACING", "full").lower()          # off | auto | full
PHOENIX_ENDPOINT = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT", "snackbot")

# --- Paths ---
DOCS_DIR = PROJECT_ROOT / "data" / "docs"
INDEX_DIR = PROJECT_ROOT / "data" / "index"
INVENTORY_PATH = PROJECT_ROOT / "data" / "inventory.json"
