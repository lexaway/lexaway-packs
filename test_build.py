"""Tests for the core question-generation logic in build.py."""

import json
import sqlite3
from pathlib import Path

import pytest

from build import (
    content_word_coverage,
    decode_int_pairs,
    encode_int_pairs,
    get_difficulty,
    pick_blank,
    pick_distractors,
    token_offsets,
    update_manifest,
)


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


class TestContentWordCoverage:
    def _tokens(self, pairs):
        """[(text, pos), ...] → checkpoint [[text, pos, char_idx], ...]."""
        out = []
        idx = 0
        for text, pos in pairs:
            out.append([text, pos, idx])
            idx += len(text) + 1
        return out

    def test_full_coverage(self):
        toks = self._tokens([("Je", "PRON"), ("mange", "VERB"), ("pomme", "NOUN")])
        # VERB=idx1, NOUN=idx2 both aligned
        coverage, n = content_word_coverage(toks, [(0, 1), (1, 2)], set())
        assert coverage == 1.0
        assert n == 2

    def test_half_coverage(self):
        toks = self._tokens([
            ("chat", "NOUN"), ("mange", "VERB"),
            ("pomme", "NOUN"), ("rouge", "ADJ"),
        ])
        # Only idx 0 and idx 1 aligned out of 4 content words.
        coverage, n = content_word_coverage(toks, [(0, 0), (1, 1)], set())
        assert coverage == 0.5
        assert n == 4

    def test_no_content_words_returns_unity(self):
        toks = self._tokens([("Je", "PRON"), ("le", "DET")])
        coverage, n = content_word_coverage(toks, [], set())
        assert coverage == 1.0
        assert n == 0

    def test_pronouns_and_determiners_ignored(self):
        toks = self._tokens([("Je", "PRON"), ("le", "DET"), ("vois", "VERB")])
        # Only VERB counts; it's aligned.
        coverage, n = content_word_coverage(toks, [(0, 2)], set())
        assert coverage == 1.0
        assert n == 1

    def test_content_stops_excluded_from_denominator(self):
        # French "ne"/"pas" get POS-tagged ADV by fr_core_news_md. Without
        # filtering, a short negated sentence like "Je ne sais pas." where
        # only "sais" is aligned would score 1/3 = 33%.
        toks = self._tokens([
            ("Je", "PRON"),
            ("ne", "ADV"),
            ("sais", "VERB"),
            ("pas", "ADV"),
        ])
        aligns = [(0, 2)]  # only "sais" aligned
        # Without filter: 1/3 (ne + sais + pas counted).
        cov_unfiltered, n_unf = content_word_coverage(toks, aligns, set())
        assert n_unf == 3
        # With filter: 1/1.
        cov_filtered, n_f = content_word_coverage(toks, aligns, {"ne", "pas"})
        assert n_f == 1
        assert cov_filtered == 1.0
        assert cov_filtered > cov_unfiltered

    def test_content_stops_case_insensitive(self):
        toks = self._tokens([("Ne", "ADV"), ("vois", "VERB")])
        coverage, n = content_word_coverage(toks, [(0, 1)], {"ne"})
        assert n == 1  # "Ne" filtered by lowercased lookup
        assert coverage == 1.0


class TestTokenOffsets:
    def test_target_tokens(self):
        # [text, pos, char_idx]
        toks = [["Je", "PRON", 0], ["mange", "VERB", 3], [".", "PUNCT", 8]]
        offsets = token_offsets(toks, "Je mange.")
        assert offsets == [[0, 2], [3, 8], [8, 9]]

    def test_source_tokens(self):
        # [text, char_idx] (no POS)
        toks = [["I", 0], ["eat", 2], [".", 5]]
        offsets = token_offsets(toks, "I eat.")
        assert offsets == [[0, 1], [2, 5], [5, 6]]

    def test_unicode_codepoints(self):
        toks = [["café", "NOUN", 0], ["ouvert", "ADJ", 5]]
        offsets = token_offsets(toks, "café ouvert")
        # len("café") == 4 codepoints, so end = 4
        assert offsets == [[0, 4], [5, 11]]


class TestEncodeIntPairs:
    def test_round_trip_offsets(self):
        offsets = [[0, 2], [3, 8], [9, 12], [13, 18], [18, 19]]
        assert decode_int_pairs(encode_int_pairs(offsets)) == offsets

    def test_round_trip_alignments(self):
        pairs = [[0, 0], [1, 1], [2, 2], [3, 4]]
        assert decode_int_pairs(encode_int_pairs(pairs)) == pairs

    def test_empty(self):
        assert encode_int_pairs([]) == ""
        assert decode_int_pairs("") == []

    def test_single_pair(self):
        assert decode_int_pairs(encode_int_pairs([[0, 5]])) == [[0, 5]]

    def test_adjacent_tokens_no_gap(self):
        # spaCy elision splits like "l'homme" → [[0, 2], [2, 7]]
        offsets = [[0, 2], [2, 7]]
        assert decode_int_pairs(encode_int_pairs(offsets)) == offsets

    def test_format_is_flat_csv(self):
        # Sanity-check the on-disk shape so we notice accidental changes.
        assert encode_int_pairs([[0, 2], [3, 8], [9, 12]]) == "0,2,3,8,9,12"

    def test_rejects_odd_length(self):
        with pytest.raises(ValueError):
            decode_int_pairs("1,2,3")

    def test_smaller_than_json(self):
        import json
        offsets = [[0, 2], [3, 8], [9, 12], [13, 18], [18, 19]]
        assert len(encode_int_pairs(offsets)) < len(json.dumps(offsets))


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
        update_manifest("fra", "eng", db_path)

        result = json.loads(Path("manifest.json").read_text())
        pack = result["packs"][0]
        assert pack["built_at"] == "2026-04-07T00:00:00+00:00"
        assert pack["schema_version"] == 1

    def test_does_not_match_different_from_lang(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manifest = {
            "schema_version": 1,
            "packs": [{"lang": "fra", "from_lang": "eng", "name": "French", "flag": "F"}],
        }
        Path("manifest.json").write_text(json.dumps(manifest))

        db_path = self._make_db(tmp_path, "2026-04-07T00:00:00+00:00", "1")
        with pytest.raises(ValueError, match="No entry for 'spa→fra'"):
            update_manifest("fra", "spa", db_path)

    def test_raises_when_lang_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manifest = {"schema_version": 1, "packs": []}
        Path("manifest.json").write_text(json.dumps(manifest))

        db_path = self._make_db(tmp_path, "2026-04-07T00:00:00+00:00", "1")
        with pytest.raises(ValueError, match="No entry for 'eng→fra'"):
            update_manifest("fra", "eng", db_path)

    def test_raises_when_no_manifest(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        db_path = self._make_db(tmp_path, "2026-04-07T00:00:00+00:00", "1")
        with pytest.raises(FileNotFoundError):
            update_manifest("fra", "eng", db_path)
