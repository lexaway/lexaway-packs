"""Tests for the core question-generation logic in build.py."""

import json
import sqlite3
from pathlib import Path

import pytest

from build import pick_blank, pick_distractors, get_difficulty, update_manifest


STOPS = {"je", "tu", "il", "de", "le", "la", "se", "en", "au", "du", "ce", "un", "une"}


class TestPickBlank:
    def test_prefers_noun_verb_adj(self):
        tokens = [
            ["Je", "PRON", 0],
            ["mange", "VERB", 3],
            ["une", "DET", 9],
            ["pomme", "NOUN", 13],
        ]
        text, pos, idx = pick_blank(tokens, STOPS)
        assert pos in {"VERB", "NOUN"}

    def test_skips_stopwords(self):
        tokens = [
            ["Je", "PRON", 0],
            ["le", "DET", 3],
            ["mange", "VERB", 6],
        ]
        text, pos, idx = pick_blank(tokens, STOPS)
        assert text == "mange"

    def test_skips_short_tokens(self):
        tokens = [
            ["Je", "PRON", 0],
            ["va", "VERB", 3],  # only 2 chars
        ]
        result = pick_blank(tokens, STOPS)
        assert result is None

    def test_skips_apostrophe_tokens(self):
        tokens = [
            ["l'", "DET", 0],
            ["homme", "NOUN", 2],
        ]
        text, pos, idx = pick_blank(tokens, STOPS)
        assert text == "homme"

    def test_skips_hyphenated_tokens(self):
        tokens = [
            ["Veux-tu", "VERB", 0],
            ["manger", "VERB", 8],
        ]
        text, pos, idx = pick_blank(tokens, STOPS)
        assert text == "manger"

    def test_falls_back_to_adv(self):
        tokens = [
            ["Je", "PRON", 0],
            ["le", "DET", 3],
            ["sais", "VERB", 6],  # stopword? no — but let's make one that is
            ["maintenant", "ADV", 11],
        ]
        # sais is not in our stops set, so it would be picked as VERB.
        # Test the fallback by only having ADV available:
        tokens_adv_only = [
            ["le", "DET", 0],
            ["maintenant", "ADV", 3],
        ]
        text, pos, idx = pick_blank(tokens_adv_only, STOPS)
        assert pos == "ADV"
        assert text == "maintenant"

    def test_returns_none_when_all_filtered(self):
        tokens = [
            ["Je", "PRON", 0],
            ["le", "DET", 3],
            [".", "PUNCT", 5],
        ]
        result = pick_blank(tokens, STOPS)
        assert result is None


class TestPickDistractors:
    def test_returns_two(self):
        pools = {"NOUN": ["chat", "chien", "maison", "voiture", "livre"]}
        result = pick_distractors("pomme", "NOUN", pools)
        assert len(result) == 2
        assert "pomme" not in [w.lower() for w in result]

    def test_excludes_answer(self):
        pools = {"NOUN": ["chat", "pomme", "maison"]}
        result = pick_distractors("pomme", "NOUN", pools)
        assert "pomme" not in result

    def test_returns_none_if_pool_too_small(self):
        pools = {"NOUN": ["chat"]}
        result = pick_distractors("pomme", "NOUN", pools)
        assert result is None

    def test_returns_none_if_no_pool(self):
        result = pick_distractors("pomme", "NOUN", {})
        assert result is None


class TestGetDifficulty:
    def test_cefr_hit(self):
        lookup = {"manger": "A1", "abandonner": "B2", "anéantir": "C1"}
        assert get_difficulty("manger", lookup) == ("beginner", "A1")
        assert get_difficulty("abandonner", lookup) == ("intermediate", "B2")
        assert get_difficulty("anéantir", lookup) == ("advanced", "C1")

    def test_cefr_miss_short_word(self):
        level, cefr = get_difficulty("chat", {})
        assert level == "beginner"
        assert cefr is None

    def test_cefr_miss_medium_word(self):
        level, cefr = get_difficulty("maison", {})
        assert level == "intermediate"
        assert cefr is None

    def test_cefr_miss_long_word(self):
        level, cefr = get_difficulty("extraordinaire", {})
        assert level == "advanced"
        assert cefr is None

    def test_case_insensitive(self):
        lookup = {"manger": "A1"}
        assert get_difficulty("Manger", lookup) == ("beginner", "A1")


class TestUpdateManifest:
    def _make_db(self, tmp_path: Path, built_at: str, schema_version: str) -> Path:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO meta VALUES ('built_at', ?)", (built_at,))
        conn.execute("INSERT INTO meta VALUES ('schema_version', ?)", (schema_version,))
        conn.commit()
        conn.close()
        return db_path

    def test_upserts_built_at_and_schema_version(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manifest = {
            "schema_version": 1,
            "packs": [{"lang": "fra", "from_lang": "eng", "name": "French", "flag": "F"}],
        }
        Path("manifest.json").write_text(json.dumps(manifest))

        db_path = self._make_db(tmp_path, "2026-04-07T00:00:00+00:00", "1")
        update_manifest("fra", db_path)

        result = json.loads(Path("manifest.json").read_text())
        pack = result["packs"][0]
        assert pack["built_at"] == "2026-04-07T00:00:00+00:00"
        assert pack["schema_version"] == 1

    def test_raises_when_lang_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manifest = {"schema_version": 1, "packs": []}
        Path("manifest.json").write_text(json.dumps(manifest))

        db_path = self._make_db(tmp_path, "2026-04-07T00:00:00+00:00", "1")
        with pytest.raises(ValueError, match="No entry for 'fra'"):
            update_manifest("fra", db_path)

    def test_raises_when_no_manifest(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        db_path = self._make_db(tmp_path, "2026-04-07T00:00:00+00:00", "1")
        with pytest.raises(FileNotFoundError):
            update_manifest("fra", db_path)
