"""
propresenter_export.py
Converts Bulletin Generator items[] into ProPresenter 7 .pro files.
Phase 1 MVP: songs and liturgy only.
"""

import io
import json
import uuid
import zipfile


def _new_uuid():
    return str(uuid.uuid4()).upper()


def _rtf_wrap(text):
    """Wrap plain text in minimal RTF for ProPresenter."""
    escaped = (text or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return (
        r"{\rtf1\ansi\ansicpg1252\cocoartf2639"
        r"\cocoatextscaling0\cocoaplatform0"
        r"{\fonttbl\f0\fswiss\fcharset0 Helvetica;}"
        r"{\colortbl ;\red255\green255\blue255;}"
        r"\pard\tx560\tx1120\tx1680\tx2240\tx2800\tx3360\tx3920\tx4480\tx5040\tx5600\tx6160\tx6720\pardirnatural\partightenfactor0"
        r"\f0\fs60 \cf1 " + escaped + r"}"
    )


def _split_stanzas(text):
    """Split lyrics/body text into stanzas on blank lines."""
    if not text:
        return []
    stanzas = []
    current = []
    for line in str(text).splitlines():
        if line.strip() == "":
            if current:
                stanzas.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        stanzas.append("\n".join(current))
    return stanzas or [str(text)]


def _clean_filename(name, fallback="Untitled"):
    safe = "".join(ch if ch.isalnum() or ch in " ._()-" else "-" for ch in (name or fallback))
    safe = " ".join(safe.split()).strip(" .")
    return (safe or fallback)[:60]


def _item_body(item):
    # Current app items store the printable text in `detail`; keep `body` as a fallback
    # so the module also works with the plan's example payloads.
    return item.get("detail") or item.get("body") or ""


def _build_slide_group(name, stanzas, color="0 0 0 0"):
    """Build a ProPresenter SlideGroup dict for serialization."""
    slides = []
    for stanza in stanzas:
        slide = {
            "uuid": _new_uuid(),
            "elements": [{
                "uuid": _new_uuid(),
                "text": {
                    "rtfData": _rtf_wrap(stanza),
                    "plainText": stanza,
                },
            }],
            "notes": "",
        }
        slides.append(slide)
    return {
        "uuid": _new_uuid(),
        "name": name,
        "slides": slides,
        "color": color,
    }


def _build_presentation(item, song_db=None):
    """
    Convert a single bulletin item into a ProPresenter presentation dict.
    Returns None if the item type is not exportable.
    """
    itype = item.get("type", "")
    title = (item.get("title", "Untitled") or "Untitled").strip()

    if itype == "song":
        body = _item_body(item)
        stanzas = _split_stanzas(body)

        groups = []
        if stanzas:
            current_section = "Verse 1"
            section_stanzas = []
            for stanza in stanzas:
                first_line = stanza.splitlines()[0].strip() if stanza else ""
                is_header = (
                    any(first_line.lower().startswith(kw) for kw in (
                        "verse", "chorus", "bridge", "pre-chorus",
                        "prechorus", "tag", "intro", "outro", "refrain"
                    ))
                    and len(first_line) < 40
                    and len(stanza.splitlines()) <= 2
                )
                if is_header:
                    if section_stanzas:
                        groups.append(_build_slide_group(current_section, section_stanzas))
                        section_stanzas = []
                    current_section = first_line
                else:
                    section_stanzas.append(stanza)
            if section_stanzas:
                groups.append(_build_slide_group(current_section, section_stanzas))

        if not groups:
            groups.append(_build_slide_group("Verse 1", stanzas or [""]))

        ccli = {
            "songTitle": title,
            "artist": item.get("author", ""),
            "author": item.get("author", ""),
            "copyright": item.get("copyright", ""),
            "songNumber": str(item.get("ccli") or item.get("ccli_number") or ""),
        }
        if isinstance(song_db, list):
            match = next((song for song in song_db if (song.get("title") or "").strip().lower() == title.lower()), None)
            if match:
                ccli["artist"] = ccli["artist"] or match.get("author", "")
                ccli["author"] = ccli["author"] or match.get("author", "")
                ccli["copyright"] = ccli["copyright"] or match.get("copyright", "")
                ccli["songNumber"] = ccli["songNumber"] or str(match.get("ccli") or match.get("ccli_number") or "")

        return {
            "uuid": _new_uuid(),
            "name": title,
            "groups": groups,
            "ccli": ccli,
            "category": "Song",
        }

    if itype in ("liturgy", "label"):
        body = _item_body(item)
        stanzas = _split_stanzas(body)
        groups = [_build_slide_group("Text", stanzas)] if stanzas else [_build_slide_group("Text", [title])]
        return {
            "uuid": _new_uuid(),
            "name": title,
            "groups": groups,
            "ccli": {},
            "category": "Liturgy",
        }

    return None


def _presentation_to_json(pres):
    """
    Serialize presentation dict to the JSON format ProPresenter 7 uses.
    ProPresenter 7 actually stores .pro files as binary protobuf, but for MVP
    we output a JSON representation. NOTE: Real ProPresenter won't open these
    until the protobuf encoding step is added. This JSON is useful for testing
    the data pipeline.
    """
    return json.dumps(pres, indent=2, ensure_ascii=False).encode("utf-8")


def export_items_to_zip(items, project_name="bulletin", song_db=None):
    """
    Convert exportable items to .pro files packaged in a ZIP.
    Returns bytes of the ZIP file.

    For Phase 1 MVP, each exportable item becomes one JSON file named
    NN - TITLE.pro.json (real protobuf encoding is Phase 2).
    """
    buf = io.BytesIO()
    counter = 1

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items or []:
            pres = _build_presentation(item, song_db=song_db)
            if pres is None:
                continue

            safe_title = _clean_filename(pres["name"])
            filename = f"{counter:02d} - {safe_title}.pro.json"
            zf.writestr(filename, _presentation_to_json(pres))
            counter += 1

        if counter == 1:
            manifest = {
                "projectName": project_name or "bulletin",
                "message": "No exportable items found. Phase 1 supports songs, liturgy, and label items.",
            }
            zf.writestr("README.json", json.dumps(manifest, indent=2).encode("utf-8"))

    return buf.getvalue()
