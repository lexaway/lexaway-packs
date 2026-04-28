"""Authoritative voice catalog for Lexaway TTS.

Mirrors the bundled fallback in the Flutter app's `kBaselineVoiceCatalog`.
Source of truth at distribution time — `update_voices.py` injects this dict
into `manifest.json` so the app picks up new voices without an app update.

Keys are ISO 639-3 lang codes. Each entry is a list of Piper VITS models
hosted on the same TTS bucket as the espeak-ng-data archive.
"""

VOICES: dict[str, list[dict]] = {
    "eng": [
        {"model_id": "hfc_male", "display_name": "HFC Male", "archive_name": "vits-piper-en_US-hfc_male-medium", "onnx_file": "en_US-hfc_male-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "lessac", "display_name": "Lessac", "archive_name": "vits-piper-en_US-lessac-medium", "onnx_file": "en_US-lessac-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "amy", "display_name": "Amy", "archive_name": "vits-piper-en_US-amy-low", "onnx_file": "en_US-amy-low.onnx", "approximate_size_mb": 16},
        {"model_id": "ryan", "display_name": "Ryan", "archive_name": "vits-piper-en_US-ryan-medium", "onnx_file": "en_US-ryan-medium.onnx", "approximate_size_mb": 61},
    ],
    "fra": [
        {"model_id": "siwis", "display_name": "Siwis", "archive_name": "vits-piper-fr_FR-siwis-medium", "onnx_file": "fr_FR-siwis-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "tom", "display_name": "Tom", "archive_name": "vits-piper-fr_FR-tom-medium", "onnx_file": "fr_FR-tom-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "gilles", "display_name": "Gilles", "archive_name": "vits-piper-fr_FR-gilles-low", "onnx_file": "fr_FR-gilles-low.onnx", "approximate_size_mb": 16},
        {"model_id": "miro", "display_name": "Miro", "archive_name": "vits-piper-fr_FR-miro-high", "onnx_file": "fr_FR-miro-high.onnx", "approximate_size_mb": 61},
    ],
    "deu": [
        {"model_id": "thorsten", "display_name": "Thorsten", "archive_name": "vits-piper-de_DE-thorsten-medium", "onnx_file": "de_DE-thorsten-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "eva_k", "display_name": "Eva", "archive_name": "vits-piper-de_DE-eva_k-x_low", "onnx_file": "de_DE-eva_k-x_low.onnx", "approximate_size_mb": 16},
        {"model_id": "kerstin", "display_name": "Kerstin", "archive_name": "vits-piper-de_DE-kerstin-low", "onnx_file": "de_DE-kerstin-low.onnx", "approximate_size_mb": 16},
        {"model_id": "thorsten_emotional", "display_name": "Thorsten Emotional", "archive_name": "vits-piper-de_DE-thorsten_emotional-medium", "onnx_file": "de_DE-thorsten_emotional-medium.onnx", "approximate_size_mb": 61},
    ],
    "spa": [
        {"model_id": "sharvard", "display_name": "Sharvard", "archive_name": "vits-piper-es_ES-sharvard-medium", "onnx_file": "es_ES-sharvard-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "davefx", "display_name": "Davefx", "archive_name": "vits-piper-es_ES-davefx-medium", "onnx_file": "es_ES-davefx-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "carlfm", "display_name": "Carlfm", "archive_name": "vits-piper-es_ES-carlfm-x_low", "onnx_file": "es_ES-carlfm-x_low.onnx", "approximate_size_mb": 16},
    ],
    "ita": [
        {"model_id": "riccardo", "display_name": "Riccardo", "archive_name": "vits-piper-it_IT-riccardo-x_low", "onnx_file": "it_IT-riccardo-x_low.onnx", "approximate_size_mb": 16},
        {"model_id": "paola", "display_name": "Paola", "archive_name": "vits-piper-it_IT-paola-medium", "onnx_file": "it_IT-paola-medium.onnx", "approximate_size_mb": 61},
    ],
    "por": [
        {"model_id": "faber", "display_name": "Faber", "archive_name": "vits-piper-pt_BR-faber-medium", "onnx_file": "pt_BR-faber-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "cadu", "display_name": "Cadu", "archive_name": "vits-piper-pt_BR-cadu-medium", "onnx_file": "pt_BR-cadu-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "edresson", "display_name": "Edresson", "archive_name": "vits-piper-pt_BR-edresson-low", "onnx_file": "pt_BR-edresson-low.onnx", "approximate_size_mb": 16},
    ],
    "nld": [
        {"model_id": "pim", "display_name": "Pim", "archive_name": "vits-piper-nl_NL-pim-medium", "onnx_file": "nl_NL-pim-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "ronnie", "display_name": "Ronnie", "archive_name": "vits-piper-nl_NL-ronnie-medium", "onnx_file": "nl_NL-ronnie-medium.onnx", "approximate_size_mb": 61},
        {"model_id": "nathalie", "display_name": "Nathalie (BE)", "archive_name": "vits-piper-nl_BE-nathalie-medium", "onnx_file": "nl_BE-nathalie-medium.onnx", "approximate_size_mb": 61},
    ],
}
