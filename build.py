"""Lexaway language pack builder.

Downloads Tatoeba sentence pairs, POS-tags them with spaCy,
generates fill-in-the-blank questions, and writes a SQLite pack.

Usage:
    uv run build --lang fra
    uv run build --lang fra --force
"""

import argparse
import bz2
import csv
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
PACKS_DIR = Path("packs")
CACHE_DIR = DATA_DIR / ".cache"

TATOEBA_BASE = "https://downloads.tatoeba.org/exports/per_language"

EXCLUDE_TAGS = {
    "vulgar", "misogynistic", "@check translation",
    "unnatural", "not a sentence",
}

PREFERRED_POS = {"VERB", "ADJ", "NOUN"}
FALLBACK_POS = {"ADV", "NUM"}

TARGET_SENTENCES = 50_000
TOM_MARY_CAP = 0.03
TOM_MARY_RE = re.compile(r"\bTom\b|\bMary\b")

SPACY_MODELS = {
    "fra": "fr_core_news_md",
    "spa": "es_core_news_md",
    "deu": "de_core_news_md",
    "ita": "it_core_news_md",
    "por": "pt_core_news_md",
}

CEFRLEX_FILES = {
    "fra": "fr_flelex.tsv",
    "spa": "es_elelex.tsv",
}

CEFR_TO_LEVEL = {
    "A1": "beginner", "A2": "beginner",
    "B1": "intermediate", "B2": "intermediate",
    "C1": "advanced", "C2": "advanced",
}

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path) -> None:
    """Download a file with progress."""
    print(f"  Downloading {dest.name}...")
    with httpx.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  Downloading {dest.name}... {pct}%", end="", flush=True)
        if total:
            print()


def ensure_downloads(lang: str) -> None:
    """Download Tatoeba files if missing."""
    DATA_DIR.mkdir(exist_ok=True)

    files = {
        f"{lang}_sentences.tsv.bz2": f"{TATOEBA_BASE}/{lang}/{lang}_sentences.tsv.bz2",
        "eng_sentences.tsv.bz2": f"{TATOEBA_BASE}/eng/eng_sentences.tsv.bz2",
        f"{lang}-eng_links.tsv.bz2": f"{TATOEBA_BASE}/{lang}/{lang}-eng_links.tsv.bz2",
        f"{lang}_tags.tsv.bz2": f"{TATOEBA_BASE}/{lang}/{lang}_tags.tsv.bz2",
    }

    for filename, url in files.items():
        dest = DATA_DIR / filename
        if not dest.exists():
            download_file(url, dest)


# ---------------------------------------------------------------------------
# Load & Filter
# ---------------------------------------------------------------------------

def load_sentences(path: Path) -> dict[str, str]:
    """Load bz2 TSV sentence file → {id: text}."""
    sents = {}
    with bz2.open(path, "rt") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                sents[parts[0]] = parts[2]
    return sents


def load_excluded_ids(tags_path: Path) -> set[str]:
    """Load tag file, return sentence IDs with any excluded tag."""
    excluded = set()
    if not tags_path.exists():
        return excluded
    with bz2.open(tags_path, "rt") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2 and parts[1] in EXCLUDE_TAGS:
                excluded.add(parts[0])
    return excluded


def load_pairs(
    lang: str, excluded: set[str]
) -> list[tuple[str, str, str]]:
    """Load filtered sentence pairs: (source_id, phrase, translation).

    Filters: 4-20 words, not excluded, Tom/Mary capped at 3%.
    Samples down to TARGET_SENTENCES.
    """
    lang_sents = load_sentences(DATA_DIR / f"{lang}_sentences.tsv.bz2")
    eng_sents = load_sentences(DATA_DIR / "eng_sentences.tsv.bz2")

    pairs = []
    with bz2.open(DATA_DIR / f"{lang}-eng_links.tsv.bz2", "rt") as f:
        for line in f:
            lang_id, eng_id = line.strip().split("\t")
            if lang_id in excluded:
                continue
            if lang_id not in lang_sents or eng_id not in eng_sents:
                continue
            text = lang_sents[lang_id]
            wc = len(text.split())
            if 4 <= wc <= 20:
                pairs.append((lang_id, text, eng_sents[eng_id]))

    # Deduplicate by source_id (links file can have multiple English translations)
    seen = set()
    unique = []
    for src_id, phrase, translation in pairs:
        if src_id not in seen:
            seen.add(src_id)
            unique.append((src_id, phrase, translation))
    pairs = unique

    # Cap Tom/Mary sentences
    tom_mary = [(i, p) for i, p in enumerate(pairs) if TOM_MARY_RE.search(p[1])]
    max_tm = int(len(pairs) * TOM_MARY_CAP)
    if len(tom_mary) > max_tm:
        random.seed(42)
        to_drop = set(i for i, _ in random.sample(tom_mary, len(tom_mary) - max_tm))
        pairs = [p for i, p in enumerate(pairs) if i not in to_drop]

    # Sample down to target
    if len(pairs) > TARGET_SENTENCES:
        random.seed(42)
        pairs = random.sample(pairs, TARGET_SENTENCES)

    return pairs


# ---------------------------------------------------------------------------
# Stage 1: Tag & Checkpoint
# ---------------------------------------------------------------------------

def checkpoint_path(lang: str) -> Path:
    return CACHE_DIR / f"{lang}_tagged.jsonl"


def tag_and_checkpoint(pairs: list[tuple[str, str, str]], lang: str) -> None:
    """POS-tag all pairs with spaCy, write JSONL checkpoint."""
    import spacy

    model_name = SPACY_MODELS.get(lang)
    if not model_name:
        raise ValueError(f"No spaCy model configured for language: {lang}")

    print(f"Loading spaCy model {model_name}...")
    nlp = spacy.load(model_name)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = checkpoint_path(lang)

    print(f"Tagging {len(pairs):,} sentences...")
    t0 = time.time()

    texts = [phrase for _, phrase, _ in pairs]
    with open(out_path, "w") as f:
        for i, doc in enumerate(nlp.pipe(texts, batch_size=256)):
            src_id, phrase, translation = pairs[i]
            tokens = [[tok.text, tok.pos_, tok.idx] for tok in doc]
            line = json.dumps({
                "source_id": src_id,
                "phrase": phrase,
                "translation": translation,
                "tokens": tokens,
            })
            f.write(line + "\n")

            if (i + 1) % 10000 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                print(f"  {i + 1:,}/{len(pairs):,} ({rate:.0f} sent/s)")

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s ({len(pairs) / elapsed:.0f} sent/s)")


def load_checkpoint(lang: str) -> list[dict]:
    """Read JSONL checkpoint."""
    tagged = []
    with open(checkpoint_path(lang)) as f:
        for line in f:
            tagged.append(json.loads(line))
    return tagged


# ---------------------------------------------------------------------------
# Stage 2: Build
# ---------------------------------------------------------------------------

def build_distractor_pools(
    tagged: list[dict], stops: set[str]
) -> dict[str, list[str]]:
    """Build per-POS top-50 frequency lists from the tagged corpus."""
    pos_freq: dict[str, dict[str, int]] = {}
    for entry in tagged:
        for text, pos, _ in entry["tokens"]:
            if len(text) < 3:
                continue
            if "'" in text or "-" in text:
                continue
            if text.lower() in stops:
                continue
            pos_freq.setdefault(pos, {})
            pos_freq[pos][text.lower()] = pos_freq[pos].get(text.lower(), 0) + 1

    pools = {}
    for pos, freqs in pos_freq.items():
        ranked = sorted(freqs.items(), key=lambda x: -x[1])
        pools[pos] = [word for word, _ in ranked[:50]]
    return pools


def pick_blank(
    tokens: list[list], stops: set[str]
) -> tuple[str, str, int] | None:
    """Pick best token to blank.

    Returns (text, pos, char_idx) or None.
    """
    candidates = []
    fallbacks = []
    for text, pos, idx in tokens:
        if len(text) < 3:
            continue
        if "'" in text or "-" in text:
            continue
        if text.lower() in stops:
            continue
        if pos in PREFERRED_POS:
            candidates.append((text, pos, idx))
        elif pos in FALLBACK_POS:
            fallbacks.append((text, pos, idx))

    if candidates:
        return random.choice(candidates)
    if fallbacks:
        return random.choice(fallbacks)
    return None


def pick_distractors(
    answer: str, pos: str, pools: dict[str, list[str]]
) -> list[str] | None:
    """Return 2 distractors from the same-POS pool, or None."""
    pool = pools.get(pos, [])
    candidates = [w for w in pool if w.lower() != answer.lower()]
    if len(candidates) < 2:
        return None
    return random.sample(candidates, 2)


def load_cefr(lang: str) -> dict[str, str]:
    """Load CEFRLex word→level lookup. Empty dict if unavailable."""
    filename = CEFRLEX_FILES.get(lang)
    if not filename:
        return {}
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  CEFRLex file not found: {path} (using word-length fallback)")
        return {}

    lookup = {}
    with open(path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            word = row.get("word", "")
            level = row.get("level", "")
            if word and level:
                lookup[word.lower()] = level
    return lookup


def get_difficulty(
    word: str, cefr_lookup: dict[str, str]
) -> tuple[str, str | None]:
    """Assign difficulty level. CEFRLex first, word-length fallback."""
    cefr = cefr_lookup.get(word.lower())
    if cefr and cefr in CEFR_TO_LEVEL:
        return CEFR_TO_LEVEL[cefr], cefr

    length = len(word)
    if length <= 5:
        return "beginner", None
    elif length <= 8:
        return "intermediate", None
    return "advanced", None


def write_database(
    tagged: list[dict],
    pools: dict[str, list[str]],
    cefr_lookup: dict[str, str],
    stops: set[str],
    lang: str,
    output_path: Path,
) -> None:
    """Build the SQLite language pack."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)

    conn = sqlite3.connect(output_path)
    conn.execute("""
        CREATE TABLE phrases (
            id INTEGER PRIMARY KEY,
            source_id TEXT,
            phrase TEXT NOT NULL,
            translation TEXT NOT NULL,
            blank_index INTEGER NOT NULL,
            answer TEXT NOT NULL,
            answer_pos TEXT NOT NULL,
            options TEXT NOT NULL,
            level TEXT NOT NULL,
            cefr TEXT,
            topic TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    random.seed(42)
    questions = []
    skipped = 0

    for entry in tagged:
        blank = pick_blank(entry["tokens"], stops)
        if blank is None:
            skipped += 1
            continue

        text, pos, idx = blank
        distractors = pick_distractors(text, pos, pools)
        if distractors is None:
            skipped += 1
            continue

        options = [text] + distractors
        random.shuffle(options)

        level, cefr = get_difficulty(text, cefr_lookup)

        questions.append((
            entry["source_id"],
            entry["phrase"],
            entry["translation"],
            idx,
            text,
            pos,
            json.dumps(options),
            level,
            cefr,
            None,  # topic — NULL for MVP
        ))

    conn.executemany(
        "INSERT INTO phrases (source_id, phrase, translation, blank_index, "
        "answer, answer_pos, options, level, cefr, topic) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        questions,
    )

    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("language", lang),
    )
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("built_at", datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("sentence_count", str(len(questions))),
    )
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("distractor_pools", json.dumps({
            pos: words[:30] for pos, words in pools.items()
        })),
    )

    conn.commit()

    # Stats
    size_kb = output_path.stat().st_size / 1024
    print(f"\n{'='*60}")
    print(f"  {output_path} ({size_kb:.0f} KB)")
    print(f"  {len(questions):,} questions from {len(tagged):,} sentences ({skipped:,} skipped)")

    print(f"\n  By level:")
    for row in conn.execute("SELECT level, count(*) FROM phrases GROUP BY level ORDER BY count(*) DESC"):
        print(f"    {row[0]}: {row[1]:,}")

    print(f"\n  By POS:")
    for row in conn.execute("SELECT answer_pos, count(*) FROM phrases GROUP BY answer_pos ORDER BY count(*) DESC"):
        print(f"    {row[0]}: {row[1]:,}")

    print(f"\n  CEFR coverage:")
    for row in conn.execute("SELECT cefr, count(*) FROM phrases GROUP BY cefr ORDER BY cefr"):
        print(f"    {row[0] or 'unknown'}: {row[1]:,}")

    print(f"\n  Sample questions:")
    for row in conn.execute(
        "SELECT phrase, blank_index, translation, answer, options, level, cefr, answer_pos "
        "FROM phrases ORDER BY RANDOM() LIMIT 5"
    ):
        phrase, bi, trans, answer, opts, level, cefr, pos = row
        display = phrase[:bi] + "___" + phrase[bi + len(answer):]
        cefr_str = f"/{cefr}" if cefr else ""
        print(f"\n    {display}")
        print(f"    ({trans})")
        print(f"    Answer: {answer} [{pos}] | Options: {json.loads(opts)} | {level}{cefr_str}")

    print(f"\n{'='*60}")
    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build a Lexaway language pack")
    parser.add_argument("--lang", required=True, help="ISO 639-3 language code (e.g. fra)")
    parser.add_argument("--force", action="store_true", help="Rebuild from scratch")
    args = parser.parse_args()

    lang = args.lang
    print(f"\n  Building language pack: {lang}\n")

    # Download
    print("Step 1: Ensure data files...")
    ensure_downloads(lang)

    # Load & filter
    print("Step 2: Loading and filtering pairs...")
    excluded = load_excluded_ids(DATA_DIR / f"{lang}_tags.tsv.bz2")
    print(f"  {len(excluded):,} sentences excluded by tags")

    pairs = load_pairs(lang, excluded)
    print(f"  {len(pairs):,} pairs after filtering")

    # Stage 1: Tag
    cp = checkpoint_path(lang)
    if cp.exists() and not args.force:
        print(f"Step 3: Checkpoint found ({cp}), skipping tagging")
    else:
        print("Step 3: POS tagging...")
        tag_and_checkpoint(pairs, lang)

    # Stage 2: Build
    print("Step 4: Loading checkpoint...")
    tagged = load_checkpoint(lang)
    print(f"  {len(tagged):,} tagged sentences")

    print("Step 5: Building distractor pools...")
    import spacy
    nlp_stops = spacy.blank(lang[:2]).Defaults.stop_words
    pools = build_distractor_pools(tagged, nlp_stops)
    for pos, words in sorted(pools.items(), key=lambda x: -len(x[1])):
        print(f"  {pos}: {len(words)} words")

    print("Step 6: Loading CEFRLex...")
    cefr_lookup = load_cefr(lang)
    print(f"  {len(cefr_lookup):,} words with CEFR levels")

    print("Step 7: Building database...")
    output_path = PACKS_DIR / f"{lang}.db"
    write_database(tagged, pools, cefr_lookup, nlp_stops, lang, output_path)


if __name__ == "__main__":
    main()
