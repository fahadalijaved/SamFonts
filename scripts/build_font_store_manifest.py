#!/usr/bin/env python3
"""
Walks fonts/<section>/*.ttf|*.otf (any depth under each top-level section
folder) and, for EACH section, builds its OWN zip + manifest — not one big
zip for everything. Also writes catalog.json, a small index of every section
(id/label/fontCount/manifestUrl) with no font data in it at all.

This is what actually lets a user download only the category they want: the
app fetches catalog.json first (tiny — just names and counts), and only
fetches a given section's own manifest.json + zip once the user actually
opens that category. An Arabic-only user never touches the Latin zip.

`id`/`displayName` heuristics are deliberately dumb here for the same reason
as before (see the previous single-zip version of this script, if you have
it in history) — FontNameUtils.kt's prettyNameFromFileName is the real,
tested source of truth for display names; this script's displayName is only
ever a fallback.

Usage: build_font_store_manifest.py <fonts_dir> <out_dir>
Writes <out_dir>/catalog.json, <out_dir>/<section>.zip, <out_dir>/<section>.manifest.json for every section.
"""
import hashlib
import json
import os
import re
import sys
import zipfile

FONT_EXTENSIONS = (".ttf", ".otf")


def slugify(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    if not cleaned:
        cleaned = "font"
    if cleaned[0].isdigit():
        cleaned = "f_" + cleaned
    return cleaned[:58]


def pretty_fallback(stem: str) -> str:
    spaced = stem.replace("_", " ").replace("-", " ")
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", spaced)
    spaced = re.sub(r"\s+", " ", spaced).strip()
    return spaced.title() if spaced else stem


def section_label(section_id: str) -> str:
    # Same spacing/title-casing as pretty_fallback, so "ios_emojis" ->
    # "Ios Emojis" instead of a bare first-letter capitalization.
    return pretty_fallback(section_id)


def build_section(section_id: str, section_path: str, out_dir: str) -> dict:
    zip_path = os.path.join(out_dir, f"{section_id}.zip")
    manifest_path = os.path.join(out_dir, f"{section_id}.manifest.json")

    entries = []
    seen_ids = {}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(section_path):
            for fname in sorted(files):
                if not fname.lower().endswith(FONT_EXTENSIONS):
                    continue

                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, section_path).replace(os.sep, "/")
                zf.write(abs_path, rel_path)

                stem = os.path.splitext(fname)[0]
                base_id = slugify(stem)
                occurrence = seen_ids.get(base_id, 0) + 1
                seen_ids[base_id] = occurrence
                entry_id = base_id if occurrence == 1 else f"{base_id}_{occurrence}"

                entries.append({
                    "id": entry_id,
                    "displayName": pretty_fallback(stem),
                    "fileName": rel_path,
                    "category": section_id,
                })

    with open(zip_path, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    manifest = {
        "version": 1,
        "zipUrl": "",  # filled in by build-font-store.yml once the release tag is known
        "zipSha256": sha256,
        "entries": entries,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return {
        "id": section_id,
        "label": section_label(section_id),
        "fontCount": len(entries),
        "manifestUrl": "",  # filled in by build-font-store.yml
        "zipSizeBytes": os.path.getsize(zip_path),
    }


def main() -> None:
    fonts_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    categories = []
    for section_id in sorted(os.listdir(fonts_dir)):
        section_path = os.path.join(fonts_dir, section_id)
        if not os.path.isdir(section_path):
            continue  # ignore stray files directly under fonts/
        info = build_section(section_id, section_path, out_dir)
        if info["fontCount"] > 0:
            categories.append(info)
        else:
            # Empty folder (e.g. a .gitkeep-only placeholder) - drop its zip/manifest,
            # nothing for the app to fetch and nothing worth listing in the catalog.
            os.remove(os.path.join(out_dir, f"{section_id}.zip"))
            os.remove(os.path.join(out_dir, f"{section_id}.manifest.json"))

    catalog = {"version": 1, "categories": categories}
    with open(os.path.join(out_dir, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    total = sum(c["fontCount"] for c in categories)
    print(f"{len(categories)} categories, {total} fonts total")
    for c in categories:
        print(f"  {c['id']}: {c['fontCount']} fonts, {c['zipSizeBytes']} bytes")


if __name__ == "__main__":
    main()
