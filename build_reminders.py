"""Generate english-only word batches for LLM translation/review.

Pipeline:
  1. Fetch Google's top-10000-english list (cached locally).
  2. POS-filter to NOUN/VERB/ADJ via spaCy (drops function words).
  3. Write CSVs in small batches of 100 to ./reminders/eng_NNN.csv with
     columns (rank, eng) only.

Review agents read each eng_NNN.csv and write a sibling clean_NNN.csv with
full translations into our 6 target languages, dropping rows whose English
headword isn't teaching-worthy in isolation.

Run:
    uv run python build_reminders.py
"""

import csv
from pathlib import Path

import httpx
import spacy

SOURCE_URL = (
    "https://raw.githubusercontent.com/first20hours/google-10000-english/"
    "master/google-10000-english.txt"
)
CACHE_PATH = Path(__file__).parent / "data" / ".cache" / "google-10000-english.txt"
OUTPUT_DIR = Path(__file__).parent / "reminders"
BATCH_SIZE = 100
KEEP_POS = {"NOUN", "VERB", "ADJ"}


def fetch_word_list() -> list[str]:
    if CACHE_PATH.exists():
        return CACHE_PATH.read_text().splitlines()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    r = httpx.get(SOURCE_URL, timeout=30)
    r.raise_for_status()
    CACHE_PATH.write_text(r.text)
    return r.text.splitlines()


def pos_filter(words: list[str]) -> list[tuple[int, str]]:
    """Keep words whose isolated POS tag is NOUN/VERB/ADJ.

    Tagging a single word out of context is imprecise — many ambiguous words
    will be misclassified. That's fine for a coarse filter; review agents
    will catch leftover noise.
    """
    nlp = spacy.load("en_core_web_md")
    kept = []
    for rank, w in enumerate(words, 1):
        w = w.strip()
        if not w:
            continue
        doc = nlp(w)
        if doc and doc[0].pos_ in KEEP_POS:
            kept.append((rank, w))
    return kept


def write_batch(idx: int, rows: list[tuple[int, str]]) -> Path:
    path = OUTPUT_DIR / f"eng_{idx:03d}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "eng"])
        w.writerows(rows)
    return path


def main() -> None:
    words = fetch_word_list()
    print(f"Loaded {len(words)} source words")

    kept = pos_filter(words)
    print(f"Kept {len(kept)} after POS filter (NOUN/VERB/ADJ)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Clear any prior artifacts — word2word-era CSVs and earlier eng batches.
    for old in OUTPUT_DIR.glob("words_*.csv"):
        old.unlink()
    for old in OUTPUT_DIR.glob("eng_*.csv"):
        old.unlink()

    batch_idx = 1
    for i in range(0, len(kept), BATCH_SIZE):
        chunk = kept[i : i + BATCH_SIZE]
        path = write_batch(batch_idx, chunk)
        print(f"  {path.name}: {len(chunk)} rows")
        batch_idx += 1

    print(f"\nWrote {batch_idx - 1} batches to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
