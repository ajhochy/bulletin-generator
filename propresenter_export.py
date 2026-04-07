"""
propresenter_export.py
Converts Bulletin Generator items[] into ProPresenter 6 .pro6 XML files.
Each exportable item (songs, liturgy, labels) becomes one .pro6 file in a ZIP.

ProPresenter 6 uses an XML-based format that this module generates directly —
no binary protobuf encoding required.  The resulting files import into PP6 and
many PP7 installations that still accept the legacy XML format.
"""

import io
import json
import uuid
import xml.etree.ElementTree as ET
import zipfile


def _new_uuid():
    return str(uuid.uuid4()).upper()


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
    return item.get("detail") or item.get("body") or ""


def _rtf_encode(text):
    """Wrap plain text in minimal RTF for ProPresenter display."""
    escaped = (text or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return (
        r"{\rtf1\ansi\ansicpg1252\cocoartf2639"
        r"\cocoatextscaling0\cocoaplatform0"
        r"{\fonttbl\f0\fswiss\fcharset0 Helvetica;}"
        r"{\colortbl ;\red255\green255\blue255;}"
        r"\pard\tx560\tx1120\tx1680\tx2240\tx2800\tx3360\tx3920\tx4480\tx5040\tx5600\tx6160\tx6720"
        r"\pardirnatural\partightenfactor0"
        r"\f0\fs72 \cf1 " + escaped + r"}"
    )


def _build_pro6_xml(title, groups, ccli_info):
    """
    Build a ProPresenter 6 XML document (ET.Element tree).

    groups = list of { name: str, stanzas: [str] }
    ccli_info = { songTitle, artist, copyright, songNumber }
    """
    root = ET.Element("RVPresentationDocument")
    root.set("CCLISongTitle",       ccli_info.get("songTitle", title))
    root.set("CCLIArtistCredits",   ccli_info.get("artist", ""))
    root.set("CCLISongNumber",      ccli_info.get("songNumber", ""))
    root.set("CCLICopyrightInfo",   ccli_info.get("copyright", ""))
    root.set("CCLICopyrightYear",   "")
    root.set("CCLIPublisher",       "")
    root.set("CCLILicenseNumber",   "")
    root.set("backgroundColor",     "0 0 0 1")
    root.set("buildNumber",         "6022")
    root.set("category",            "Song")
    root.set("chordChartPath",      "")
    root.set("docType",             "0")
    root.set("drawingBackgroundColor", "0")
    root.set("height",              "768")
    root.set("lastDateUsed",        "")
    root.set("notes",               "")
    root.set("os",                  "1")
    root.set("resourcesDirectory",  "")
    root.set("selectedArrangementID", "")
    root.set("usedCount",           "0")
    root.set("uuid",                _new_uuid())
    root.set("versionNumber",       "600")
    root.set("width",               "1024")

    slides_array = ET.SubElement(root, "array")
    slides_array.set("rvXMLIvarName", "slides")

    for idx, group in enumerate(groups):
        grp_el = ET.SubElement(slides_array, "RVSlideGrouping")
        grp_el.set("color",                    "0 0 0 0")
        grp_el.set("name",                     group["name"])
        grp_el.set("uuid",                     _new_uuid())
        grp_el.set("serialization-array-index", str(idx))

        grp_slides = ET.SubElement(grp_el, "array")
        grp_slides.set("rvXMLIvarName", "slides")

        for s_idx, stanza_text in enumerate(group["stanzas"]):
            slide_el = ET.SubElement(grp_slides, "RVDisplaySlide")
            slide_el.set("backgroundColor",           "0 0 0 0")
            slide_el.set("enabled",                   "1")
            slide_el.set("highlightColor",            "0 0 0 0")
            slide_el.set("hotKey",                    "")
            slide_el.set("label",                     "")
            slide_el.set("notes",                     "")
            slide_el.set("slideType",                 "1")
            slide_el.set("sort_index",                str(s_idx))
            slide_el.set("uuid",                      _new_uuid())
            slide_el.set("drawingBackgroundColor",    "0")
            slide_el.set("chordChartPath",            "")
            slide_el.set("serialization-array-index", str(s_idx))

            display_elements = ET.SubElement(slide_el, "array")
            display_elements.set("rvXMLIvarName", "displayElements")

            text_el = ET.SubElement(display_elements, "RVTextElement")
            text_el.set("displayDelay",               "0")
            text_el.set("displayName",                "Lyrics")
            text_el.set("locked",                     "0")
            text_el.set("persistent",                 "0")
            text_el.set("typeID",                     "0")
            text_el.set("fromTemplate",               "0")
            text_el.set("bezelRadius",                "0")
            text_el.set("drawingFill",                "0")
            text_el.set("drawingShadow",              "0")
            text_el.set("drawingStroke",              "0")
            text_el.set("fillColor",                  "1 1 1 0")
            text_el.set("rotation",                   "0")
            text_el.set("source",                     stanza_text)
            text_el.set("uuid",                       _new_uuid())
            text_el.set("serialization-array-index",  str(s_idx))

            # Plain text source — what the import parser reads
            source_ns = ET.SubElement(text_el, "NSString")
            source_ns.set("rvXMLIvarName", "source")
            source_ns.text = stanza_text

            # RTF data for rich display
            rtf_ns = ET.SubElement(text_el, "NSString")
            rtf_ns.set("rvXMLIvarName", "RTFData")
            rtf_ns.text = _rtf_encode(stanza_text)

    return root


def _presentation_to_pro6(pres):
    """Convert presentation dict to ProPresenter 6 XML bytes (.pro6)."""
    ccli = pres.get("ccli", {})

    # Reconstruct slide groups from pres["groups"]
    groups = []
    for grp in pres.get("groups", []):
        stanzas = [slide["elements"][0]["text"]["plainText"]
                   for slide in grp.get("slides", [])
                   if slide.get("elements")]
        if stanzas:
            groups.append({"name": grp.get("name", "Slide"), "stanzas": stanzas})

    if not groups:
        groups = [{"name": "Slide", "stanzas": [pres.get("name", "")]}]

    root_el = _build_pro6_xml(
        title=pres.get("name", "Untitled"),
        groups=groups,
        ccli_info={
            "songTitle":  ccli.get("songTitle", pres.get("name", "")),
            "artist":     ccli.get("artist", ccli.get("author", "")),
            "copyright":  ccli.get("copyright", ""),
            "songNumber": str(ccli.get("songNumber", "") or ""),
        },
    )

    ET.indent(root_el, space="  ")
    tree = ET.ElementTree(root_el)
    buf = io.BytesIO()
    tree.write(buf, encoding="UTF-8", xml_declaration=True)
    return buf.getvalue()


def _build_presentation(item, song_db=None):
    """
    Convert a single bulletin item into a presentation dict.
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
                        groups.append({"name": current_section, "stanzas": section_stanzas})
                        section_stanzas = []
                    current_section = first_line
                else:
                    section_stanzas.append(stanza)
            if section_stanzas:
                groups.append({"name": current_section, "stanzas": section_stanzas})

        if not groups:
            groups = [{"name": "Verse 1", "stanzas": stanzas or [""]}]

        ccli = {
            "songTitle":  title,
            "artist":     item.get("author", ""),
            "author":     item.get("author", ""),
            "copyright":  item.get("copyright", ""),
            "songNumber": str(item.get("ccli") or item.get("ccli_number") or ""),
        }
        if isinstance(song_db, list):
            match = next(
                (s for s in song_db if (s.get("title") or "").strip().lower() == title.lower()),
                None
            )
            if match:
                ccli["artist"]     = ccli["artist"]     or match.get("author", "")
                ccli["author"]     = ccli["author"]     or match.get("author", "")
                ccli["copyright"]  = ccli["copyright"]  or match.get("copyright", "")
                ccli["songNumber"] = ccli["songNumber"] or str(match.get("ccli") or match.get("ccli_number") or "")

        # Build slides list compatible with _presentation_to_pro6
        slides_groups = []
        for grp in groups:
            slides = [
                {"elements": [{"text": {"plainText": s}}], "notes": ""}
                for s in grp["stanzas"]
            ]
            slides_groups.append({"name": grp["name"], "slides": slides})

        return {
            "uuid":     _new_uuid(),
            "name":     title,
            "groups":   slides_groups,
            "ccli":     ccli,
            "category": "Song",
        }

    if itype in ("liturgy", "label"):
        body = _item_body(item)
        stanzas = _split_stanzas(body)
        if not stanzas:
            stanzas = [title]
        slides = [{"elements": [{"text": {"plainText": s}}], "notes": ""} for s in stanzas]
        return {
            "uuid":     _new_uuid(),
            "name":     title,
            "groups":   [{"name": "Text", "slides": slides}],
            "ccli":     {},
            "category": "Liturgy",
        }

    return None


def export_items_to_zip(items, project_name="bulletin", song_db=None):
    """
    Convert exportable items to .pro6 files packaged in a ZIP.
    Returns bytes of the ZIP file.

    Each exportable item (songs, liturgy, labels) becomes one
    ProPresenter 6 XML file (.pro6) importable by ProPresenter 6
    and ProPresenter 7 in legacy-XML mode.
    """
    buf = io.BytesIO()
    counter = 1

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items or []:
            pres = _build_presentation(item, song_db=song_db)
            if pres is None:
                continue

            safe_title = _clean_filename(pres["name"])
            filename = f"{counter:02d} - {safe_title}.pro6"
            zf.writestr(filename, _presentation_to_pro6(pres))
            counter += 1

        if counter == 1:
            manifest = {
                "projectName": project_name or "bulletin",
                "message": "No exportable items found. Export supports songs, liturgy, and label items.",
            }
            zf.writestr("README.json", json.dumps(manifest, indent=2).encode("utf-8"))

    return buf.getvalue()
