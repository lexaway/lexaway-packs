"""Bundle a music pack into a deterministic tar.bz2 + refresh manifest.json.

Source files live under `music/<pack_id>_raw/` (any nested layout). For each
pack in `_PACKS`:

  1. Rename each track to a stable slug (flat on-device layout).
  2. Write tracks into `music/<archive_name>.tar.bz2`, sorting entries and
     zeroing tar metadata for byte-identical rebuilds.
  3. Patch the `music` array in `manifest.json`; other top-level sections
     preserved untouched.

Edit `_PACKS` to curate biome tags / add packs. Run `uv run python build_music.py`.
"""

from __future__ import annotations

import io
import json
import os
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent
MUSIC_DIR = ROOT / "music"
MANIFEST_PATH = ROOT / "manifest.json"


@dataclass
class TrackSpec:
    """A single track in a pack. `source` is a path under the pack's raw dir."""

    source: str
    slug: str
    title: str
    biomes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    loopable: bool = True


@dataclass
class PackSpec:
    pack_id: str
    display_name: str
    archive_name: str
    raw_dir: str
    tracks: list[TrackSpec]


# Empty `biomes` = filler (plays when no biome-specific track available).
# App biomes: grassland, tropics, winter.
_PACKS: list[PackSpec] = [
    PackSpec(
        pack_id="towballs_crossing_deluxe",
        display_name="Towball's Crossing Deluxe",
        archive_name="music-towballs-crossing-deluxe-v1",
        raw_dir="towballs_crossing_deluxe_raw",
        tracks=[
            # Loopable variants — preferred for ambient loops.
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/01 Welcome To Towballs Crossing Deluxe! (Loopable Version).m4a",
                slug="welcome_to_towballs",
                title="Welcome to Towball's Crossing",
                biomes=["grassland"],
                tags=["intro"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/02 Enjoying the Sunrise (Loopable Version).m4a",
                slug="enjoying_the_sunrise",
                title="Enjoying the Sunrise",
                biomes=["grassland"],
                tags=["dawn"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/03 Spring is in the Air! (Loopable Version).m4a",
                slug="spring_in_the_air",
                title="Spring is in the Air",
                biomes=["grassland"],
                tags=["day"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/04 Island Life (Loopable Version).m4a",
                slug="island_life",
                title="Island Life",
                biomes=["tropics"],
                tags=["day"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/05 At the Farmers Market (Loopable Version).m4a",
                slug="farmers_market",
                title="At the Farmer's Market",
                biomes=["grassland"],
                tags=["day"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/06 Tax Office (Loopable Version).m4a",
                slug="tax_office",
                title="Tax Office",
                tags=["quirky"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/07 Afternoon Boredom (Loopable Version).m4a",
                slug="afternoon_boredom",
                title="Afternoon Boredom",
                tags=["day"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/08 Spooky Time! (Loopable Version).m4a",
                slug="spooky_time",
                title="Spooky Time",
                tags=["spooky"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/09 Snowed In (Loopable Version).m4a",
                slug="snowed_in",
                title="Snowed In",
                biomes=["winter"],
                tags=["day"],
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Loopable Tracks/10 Goodnight and Sweet Dreams (Loopable Version).m4a",
                slug="goodnight",
                title="Goodnight and Sweet Dreams",
                tags=["night"],
            ),
            # Standard (non-loopable) versions: same songs as the loopable
            # variants but with original endings — one-shot picks with a
            # clean fade-out. Same biome tags as their counterparts.
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/01 Welcome To Towballs Crossing Deluxe!.m4a",
                slug="welcome_to_towballs_std",
                title="Welcome to Towball's Crossing (Standard)",
                biomes=["grassland"],
                tags=["intro"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/02 Enjoying the Sunrise.m4a",
                slug="enjoying_the_sunrise_std",
                title="Enjoying the Sunrise (Standard)",
                biomes=["grassland"],
                tags=["dawn"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/03 Spring is in the Air!.m4a",
                slug="spring_in_the_air_std",
                title="Spring is in the Air (Standard)",
                biomes=["grassland"],
                tags=["day"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/04 Island Life.m4a",
                slug="island_life_std",
                title="Island Life (Standard)",
                biomes=["tropics"],
                tags=["day"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/05 At the Farmers market.m4a",
                slug="farmers_market_std",
                title="At the Farmer's Market (Standard)",
                biomes=["grassland"],
                tags=["day"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/06 The Tax Office.m4a",
                slug="tax_office_std",
                title="Tax Office (Standard)",
                tags=["quirky"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/07 Afternoon Boredom.m4a",
                slug="afternoon_boredom_std",
                title="Afternoon Boredom (Standard)",
                tags=["day"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/08 Spooky Time!.m4a",
                slug="spooky_time_std",
                title="Spooky Time (Standard)",
                tags=["spooky"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/09 Snowed In.m4a",
                slug="snowed_in_std",
                title="Snowed In (Standard)",
                biomes=["winter"],
                tags=["day"],
                loopable=False,
            ),
            TrackSpec(
                source="Towballs Crossing Deluxe! Standard Tracks/10 Goodnight and Sweet Dreams.m4a",
                slug="goodnight_std",
                title="Goodnight and Sweet Dreams (Standard)",
                tags=["night"],
                loopable=False,
            ),
            # Original time-of-day tracks. Tagged by diurnal phase, no biome
            # (town-themed fillers). Source file 06 is named "10pm" but sits
            # between 9am and 11am — it's the 10am track (filename typo).
            TrackSpec(
                source="Towball's Crossing/02 6am _ Towballs Crossing.m4a",
                slug="town_06h",
                title="6 AM",
                tags=["dawn"],
            ),
            TrackSpec(
                source="Towball's Crossing/03 7am _ Towballs Crossing.m4a",
                slug="town_07h",
                title="7 AM",
                tags=["dawn"],
            ),
            TrackSpec(
                source="Towball's Crossing/04 8am _ Towballs Crossing.m4a",
                slug="town_08h",
                title="8 AM",
                tags=["dawn"],
            ),
            TrackSpec(
                source="Towball's Crossing/05 9am _ Towballs Crossing.m4a",
                slug="town_09h",
                title="9 AM",
                tags=["dawn"],
            ),
            TrackSpec(
                source="Towball's Crossing/06 10pm _ Towball's Crossing.m4a",
                slug="town_10h",
                title="10 AM",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/07 11am _ Towball's Crossing.m4a",
                slug="town_11h",
                title="11 AM",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/08 Noon _ Towball's Crossing.m4a",
                slug="town_12h",
                title="Noon",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/09 1pm _ Towball's Crossing.m4a",
                slug="town_13h",
                title="1 PM",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/10 2pm _ Towball's Crossing.m4a",
                slug="town_14h",
                title="2 PM",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/11 3pm _ Towballs Crossing.m4a",
                slug="town_15h",
                title="3 PM",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/12 4pm _ Towball's Crossing.m4a",
                slug="town_16h",
                title="4 PM",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/13 5pm _ Towball's Crossing.m4a",
                slug="town_17h",
                title="5 PM",
                tags=["day"],
            ),
            TrackSpec(
                source="Towball's Crossing/14 From Day to Night _ Towball's Crossing.m4a",
                slug="town_day_to_night",
                title="From Day to Night",
                tags=["dusk"],
            ),
            TrackSpec(
                source="Towball's Crossing/15 6pm _ Towball's Crossing 1.m4a",
                slug="town_18h",
                title="6 PM",
                tags=["dusk"],
            ),
            TrackSpec(
                source="Towball's Crossing/16 7pm _ Towball's Crossing.m4a",
                slug="town_19h",
                title="7 PM",
                tags=["dusk"],
            ),
            TrackSpec(
                source="Towball's Crossing/17  8pm _ Towball's Crossing.m4a",
                slug="town_20h",
                title="8 PM",
                tags=["evening"],
            ),
            TrackSpec(
                source="Towball's Crossing/18 9pm _ Towball's Crossing.m4a",
                slug="town_21h",
                title="9 PM",
                tags=["evening"],
            ),
            TrackSpec(
                source="Towball's Crossing/19  10pm _ Towball's Crossing.m4a",
                slug="town_22h",
                title="10 PM",
                tags=["evening"],
            ),
            TrackSpec(
                source="Towball's Crossing/20 11pm _ Towball's Crossing.m4a",
                slug="town_23h",
                title="11 PM",
                tags=["evening"],
            ),
            TrackSpec(
                source="Towball's Crossing/21 Midnight _ Towball's Crossing.m4a",
                slug="town_00h",
                title="Midnight",
                tags=["night"],
            ),
            TrackSpec(
                source="Towball's Crossing/22 1am _ Towball's Crossing.m4a",
                slug="town_01h",
                title="1 AM",
                tags=["night"],
            ),
            TrackSpec(
                source="Towball's Crossing/23 2am _ Towball's Crossing.m4a",
                slug="town_02h",
                title="2 AM",
                tags=["night"],
            ),
            TrackSpec(
                source="Towball's Crossing/24 3am _ Towball's Crossing.m4a",
                slug="town_03h",
                title="3 AM",
                tags=["night"],
            ),
            TrackSpec(
                source="Towball's Crossing/25 4am _ Towball's Crossing.m4a",
                slug="town_04h",
                title="4 AM",
                tags=["night"],
            ),
            TrackSpec(
                source="Towball's Crossing/26 5am - Goodbye _ Towball's Crossing.m4a",
                slug="town_05h_goodbye",
                title="5 AM (Goodbye)",
                tags=["dawn"],
            ),
        ],
    ),
]


def _build_archive(pack: PackSpec) -> Path:
    """Write `<archive_name>.tar.bz2` with each track renamed to its slug.
    Deterministic: sorted entries, fixed mtime, no user/group metadata."""
    raw_root = MUSIC_DIR / pack.raw_dir
    if not raw_root.is_dir():
        raise FileNotFoundError(
            f"Pack source not found: {raw_root}. "
            f"Move source music there first (see plan)."
        )

    archive_path = MUSIC_DIR / f"{pack.archive_name}.tar.bz2"
    tmp_path = archive_path.with_suffix(".tar.bz2.tmp")

    # Sort by slug so archive bytes are stable regardless of declaration order.
    tracks = sorted(pack.tracks, key=lambda t: t.slug)

    # USTAR over PAX: PAX writes timestamped header records that defeat
    # bit-for-bit reproducibility. USTAR is older but flat and deterministic
    # for the short, ASCII-only filenames we emit.
    with tarfile.open(tmp_path, "w:bz2", format=tarfile.USTAR_FORMAT) as tar:
        for track in tracks:
            src = raw_root / track.source
            if not src.is_file():
                raise FileNotFoundError(f"Missing track source: {src}")

            ext = src.suffix
            arcname = f"{track.slug}{ext}"
            data = src.read_bytes()

            info = tarfile.TarInfo(name=arcname)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))

    os.replace(tmp_path, archive_path)
    return archive_path


def _track_to_manifest(track: TrackSpec) -> dict:
    return {
        "id": track.slug,
        "file": f"{track.slug}{Path(track.source).suffix}",
        "title": track.title,
        "biomes": track.biomes,
        "tags": track.tags,
        "loopable": track.loopable,
    }


def _pack_to_manifest(pack: PackSpec, archive_path: Path) -> dict:
    size_mb = max(1, round(archive_path.stat().st_size / (1024 * 1024)))
    return {
        "id": pack.pack_id,
        "display_name": pack.display_name,
        "archive_name": pack.archive_name,
        "approximate_size_mb": size_mb,
        "tracks": [_track_to_manifest(t) for t in pack.tracks],
    }


def _update_manifest(packs: list[PackSpec], archive_paths: list[Path]) -> None:
    """Patch `manifest.json` in place. Preserves every other top-level key
    so this can run independently of `build.py` / `update_voices.py`."""
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest["music"] = [
        _pack_to_manifest(pack, archive)
        for pack, archive in zip(packs, archive_paths, strict=True)
    ]
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    MUSIC_DIR.mkdir(exist_ok=True)
    archives: list[Path] = []
    for pack in _PACKS:
        print(f"==> Building music pack: {pack.pack_id}")
        archive = _build_archive(pack)
        size_mb = archive.stat().st_size / (1024 * 1024)
        print(f"    {archive.relative_to(ROOT)}  ({size_mb:.1f} MB, {len(pack.tracks)} tracks)")
        archives.append(archive)

    print("==> Updating manifest.json")
    _update_manifest(_PACKS, archives)
    print("Done.")


if __name__ == "__main__":
    main()
