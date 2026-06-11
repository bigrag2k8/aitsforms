"""
Convert the official ODOT forms (RE 46 Title Report, RE 46-1 Title Chain) into
docxtpl/Jinja2 templates.

It performs surgical edits on the underlying WordprocessingML so the OFFICIAL
layout is preserved exactly (fonts, borders, page furniture) while the fillable
parts become Jinja placeholders:

  * Legacy Word FORMTEXT / FORMCHECKBOX fields  ->  {{ key }} placeholders
  * RE 46-1 Title Chain blank rows              ->  a {%tr%} repeating row-pair
  * RE 46 tax table blank row                   ->  a {%tr%} repeating row
  * RE 46-1 page header (DIST/CRS/PARCEL/PID)   ->  shared-field placeholders

Run once (re-run any time the source forms change):
    python build_templates.py
"""
from __future__ import annotations
import os
import re
import zipfile
import shutil
from lxml import etree

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "forms_source")
OUT = os.path.join(ROOT, "templates_docx")

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W}


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


# Checked / unchecked box glyphs (render in a box in both states).
CHK = "☒"   # ballot box with X
UNCHK = "☐"  # empty ballot box

# ---------------------------------------------------------------------------
# RE 46 form-field name -> Jinja context key.
# A list value means "differentiate by occurrence order in the document".
# ---------------------------------------------------------------------------
RE46_TEXT_FIELDS = {
    "CRS": "crs",
    "PARCEL": "parcel",
    "PID": "pid",
    "OWNER": "owner_name",
    "MartialStatus": "owner_marital",
    "Interest": "owner_interest",
    "Text44": "mail_addr1",
    "Text45": "mail_addr2",
    "PhoneNumber": "owner_phone",
    "Text46": "prop_addr1",
    "Text47": "prop_addr2",
    "FeeDescription": "fee_description",
    "MortgagesNameAddress": "mortgages_name",
    "Text48": "mortgages_date",
    "AmountTypeOfLien": "mortgages_amount",
    "LeasesNameAddress": "leases_name",
    "Text49": "leases_type",
    "Terms": "leases_term",
    "EasementsNameAddress": "easements_name",
    "EasementsType": "easements_type",
    "Defects": "defects",
    "County1": "county",
    "Township": "township",
    "SchoolDistrict": "school_district",
    "CauvComments": "cauv_comments",
    "Date1": "cover_from",
    "Date2": "cover_to",
    "County2": "county",
    "DateTime": ["sign_datetime", "update_datetime"],  # appears twice
    "AgentName": "agent_name",
    "Date3": "update_from",
    "Date4": "update_to",
    "County3": "county",
    "UpdateAgentName": "update_agent_name",
    "Text39": "update_comments",
}

# Word REF cross-reference fields in the certification sentences -> placeholders.
RE46_REF_FIELDS = {
    "parcel": "parcel",
    "owner": "owner_name",
}

# Fields to remove entirely. Also strips the literal "-" run that the original
# layout placed before the field (e.g. "PARCEL <val> - <SUFFIX>") so the doc
# doesn't end up with an orphan dash.
DROP_FORM_FIELDS = {"SUFFIX"}
DROP_REF_TARGETS = {"suffix"}

# Checkboxes -> full Jinja expression that emits a checked/unchecked glyph.
RE46_CHECKBOXES = {
    "Check4": f"{{{{ '{CHK}' if report_type == '42year' else '{UNCHK}' }}}}",
    "Check3": f"{{{{ '{CHK}' if report_type == 'abbreviated' else '{UNCHK}' }}}}",
    "Check5": f"{{{{ '{CHK}' if report_type == 'update' else '{UNCHK}' }}}}",
    "Check1": f"{{{{ '{CHK}' if cauv else '{UNCHK}' }}}}",
    "Check2": f"{{{{ '{UNCHK}' if cauv else '{CHK}' }}}}",
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def read_parts(path: str) -> dict[str, bytes]:
    parts = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            parts[name] = z.read(name)
    return parts


def write_docx(src_path: str, out_path: str, changed: dict[str, bytes]) -> None:
    """Copy src_path into out_path, overwriting the named parts."""
    with zipfile.ZipFile(src_path) as zin, zipfile.ZipFile(
        out_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = changed.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)


def parse(xml_bytes: bytes) -> etree._Element:
    return etree.fromstring(xml_bytes)


def serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def make_run(text: str, rpr: etree._Element | None = None) -> etree._Element:
    r = etree.Element(qn("r"))
    if rpr is not None:
        r.append(etree.fromstring(etree.tostring(rpr)))
    t = etree.SubElement(r, qn("t"))
    t.set(f"{{{XML}}}space", "preserve")
    t.text = text
    return r


def cell_first_p(tc: etree._Element) -> etree._Element:
    p = tc.find(qn("p"))
    if p is None:
        p = etree.SubElement(tc, qn("p"))
    return p


def set_cell_text(tc: etree._Element, text: str, rpr: etree._Element | None = None) -> None:
    """Replace a cell's content with a single run carrying `text`.

    Removes every run anywhere in the cell (including runs nested in hyperlinks
    or smart-tags) so no original label text leaks through.
    """
    p = cell_first_p(tc)
    for r in tc.findall(f".//{qn('r')}"):
        r.getparent().remove(r)
    p.append(make_run(text, rpr))


def first_run_rpr(tc: etree._Element) -> etree._Element | None:
    r = tc.find(f".//{qn('r')}")
    if r is not None:
        rpr = r.find(qn("rPr"))
        if rpr is not None:
            return rpr
    return None


def clone(el: etree._Element) -> etree._Element:
    return etree.fromstring(etree.tostring(el))


def _strip_leading_dash(begin_run: etree._Element) -> None:
    """If the run immediately before begin_run contains only '-' (with optional
    whitespace), remove that run. Bookmarks and other non-run siblings are skipped.
    Used when dropping a field whose original layout had a literal '-' separator
    in front of it (e.g. between PARCEL and SUFFIX)."""
    parent = begin_run.getparent()
    sibs = list(parent)
    idx = sibs.index(begin_run)
    for j in range(idx - 1, -1, -1):
        el = sibs[j]
        if el.tag == qn("r"):
            text = "".join(t.text or "" for t in el.findall(qn("t")))
            if text.strip() == "-":
                parent.remove(el)
            return


def make_marker_row(template_row: etree._Element, tag_text: str) -> etree._Element:
    """A standalone <w:tr> whose only purpose is to carry a {%tr ... %} tag.

    docxtpl replaces the whole row that contains a {%tr%} tag with the bare
    Jinja statement, so for/endfor must each sit in their own row.
    """
    row = clone(template_row)
    cells = row.findall(qn("tc"))
    for i, tc in enumerate(cells):
        set_cell_text(tc, tag_text if i == 0 else "")
    return row


# ---------------------------------------------------------------------------
# Form-field replacement (FORMTEXT / FORMCHECKBOX -> Jinja)
# ---------------------------------------------------------------------------
def replace_form_fields(root: etree._Element) -> int:
    seen: dict[str, int] = {}
    count = 0

    # Collect the "begin" runs first; mutating while iterating is unsafe.
    begins = []
    for r in root.iter(qn("r")):
        fc = r.find(qn("fldChar"))
        if fc is not None and fc.get(qn("fldCharType")) == "begin":
            begins.append(r)

    for begin_run in begins:
        fc = begin_run.find(qn("fldChar"))
        ff = fc.find(qn("ffData"))

        parent = begin_run.getparent()
        sibs = list(parent)
        start = sibs.index(begin_run)
        end = None
        for j in range(start, len(sibs)):
            el = sibs[j]
            if el.tag == qn("r"):
                fce = el.find(qn("fldChar"))
                if fce is not None and fce.get(qn("fldCharType")) == "end":
                    end = j
                    break
        if end is None:
            continue

        instr = "".join(
            (it.text or "")
            for j in range(start, end + 1)
            if sibs[j].tag == qn("r")
            for it in sibs[j].findall(qn("instrText"))
        )

        # Resolve placeholder text.
        placeholder: str | None = None
        if ff is not None:
            name_el = ff.find(qn("name"))
            fname = name_el.get(qn("val")) if name_el is not None else None
            if not fname:
                continue
            if fname in DROP_FORM_FIELDS:
                _strip_leading_dash(begin_run)
                placeholder = ""  # drop the field complex entirely
            elif ff.find(qn("checkBox")) is not None:
                placeholder = RE46_CHECKBOXES.get(fname)
                if placeholder is None:
                    continue
            else:
                mapping = RE46_TEXT_FIELDS.get(fname, fname)
                if isinstance(mapping, list):
                    idx = seen.get(fname, 0)
                    seen[fname] = idx + 1
                    key = mapping[min(idx, len(mapping) - 1)]
                else:
                    key = mapping
                placeholder = "{{ %s }}" % key
        else:
            # Non form-field: REF cross-reference or SEQ numbering.
            ref = re.search(r"\bREF\s+(\w+)", instr, re.I)
            if ref:
                target = ref.group(1).lower()
                if target in DROP_REF_TARGETS:
                    _strip_leading_dash(begin_run)
                    placeholder = ""
                else:
                    key = RE46_REF_FIELDS.get(target)
                    if not key:
                        continue
                    placeholder = "{{ %s }}" % key
            elif "SEQ" in instr.upper():
                placeholder = ""  # strip stray chapter-sequence numbers
            else:
                continue

        rpr = begin_run.find(qn("rPr"))
        if rpr is None:
            for j in range(start, end + 1):
                if sibs[j].tag == qn("r"):
                    cand = sibs[j].find(qn("rPr"))
                    if cand is not None:
                        rpr = cand
                        break

        if placeholder:
            begin_run.addprevious(make_run(placeholder, rpr))
        for j in range(start, end + 1):
            if sibs[j].tag == qn("r"):
                parent.remove(sibs[j])
        count += 1

    return count


# ---------------------------------------------------------------------------
# RE 46 tax table -> repeating row
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# RE 46 header -> shift the C/R/S / PARCEL / PID labels + values left a touch.
# Width is taken from the "TITLE REPORT" column (left of the labels) and given
# to the value column (right), so the label+value block slides left while the
# table's overall width and position stay the same.
# ---------------------------------------------------------------------------
HEADER_SHIFT_TWIPS = 144  # ~0.1", roughly 2 spaces


def _adjust_w(el: etree._Element, delta: int) -> None:
    cur = int(el.get(qn("w")))
    el.set(qn("w"), str(cur + delta))


CRS_FONT_HALF_POINTS = "16"  # 8pt — keeps long CRS values (e.g. FRA-CR14-0.05) one per line


def set_crs_font_size(root: etree._Element, half_points: str = CRS_FONT_HALF_POINTS) -> bool:
    for r in root.iter(qn("r")):
        t = r.find(qn("t"))
        if t is None or not t.text or "{{ crs }}" not in t.text:
            continue
        rpr = r.find(qn("rPr"))
        if rpr is None:
            rpr = etree.Element(qn("rPr"))
            r.insert(0, rpr)
        for tag in ("sz", "szCs"):
            for e in rpr.findall(qn(tag)):
                rpr.remove(e)
        etree.SubElement(rpr, qn("sz")).set(qn("val"), half_points)
        etree.SubElement(rpr, qn("szCs")).set(qn("val"), half_points)
        return True
    return False


def shift_header_block_left(root: etree._Element, twips: int = HEADER_SHIFT_TWIPS) -> bool:
    tbl = root.find(f".//{qn('tbl')}")
    if tbl is None:
        return False
    grid = tbl.find(qn("tblGrid"))
    cols = grid.findall(qn("gridCol")) if grid is not None else []
    if len(cols) < 4:
        return False
    _adjust_w(cols[1], -twips)   # TITLE REPORT column narrower
    _adjust_w(cols[3], +twips)   # value column wider
    for tr in tbl.findall(qn("tr")):
        tcs = tr.findall(qn("tc"))
        if len(tcs) < 4:
            continue
        for idx, delta in ((1, -twips), (3, +twips)):
            tcpr = tcs[idx].find(qn("tcPr"))
            tcw = tcpr.find(qn("tcW")) if tcpr is not None else None
            if tcw is not None:
                _adjust_w(tcw, delta)
    return True


def template_tax_table(root: etree._Element) -> bool:
    for tbl in root.iter(qn("tbl")):
        if "AUD. PAR. NO(S)" not in "".join(tbl.itertext()):
            continue
        rows = tbl.findall(qn("tr"))
        if len(rows) < 2:
            return False
        data = rows[1]
        cells = data.findall(qn("tc"))
        # cols: 0=aud par, 1=land, 3=building, 5=total, 7=taxes (2/4/6 spacers)
        set_cell_text(cells[0], "{{ t.aud_par_no }}")
        set_cell_text(cells[1], "{{ t.land }}")
        set_cell_text(cells[3], "{{ t.building }}")
        set_cell_text(cells[5], "{{ t.total }}")
        set_cell_text(cells[7], "{{ t.taxes }}")
        data.addprevious(make_marker_row(data, "{%tr for t in taxes %}"))
        data.addnext(make_marker_row(data, "{%tr endfor %}"))
        return True
    return False


# ---------------------------------------------------------------------------
# RE 46 (3-C) Easements row -> repeating row (one entry per row)
# ---------------------------------------------------------------------------
def blank_para(half_points: str = "18") -> etree._Element:
    """An empty paragraph (a blank line) matching the easement font size."""
    p = etree.Element(qn("p"))
    ppr = etree.SubElement(p, qn("pPr"))
    rpr = etree.SubElement(ppr, qn("rPr"))
    etree.SubElement(rpr, qn("sz")).set(qn("val"), half_points)
    etree.SubElement(rpr, qn("szCs")).set(qn("val"), half_points)
    return p


# Blank lines appended below each easement entry. This separates consecutive
# easements AND separates the last easement from the (4) Defects section.
EASEMENT_TRAILING_BLANKS = 2


def template_easements_row(root: etree._Element) -> bool:
    """Find the row containing the {{ easements_name }} / {{ easements_type }}
    placeholders (placed earlier by replace_form_fields) and make it repeat
    once per item in the `easements` list."""
    name_tok = "{{ easements_name }}"
    type_tok = "{{ easements_type }}"
    for tr in list(root.iter(qn("tr"))):
        if name_tok not in "".join(tr.itertext()):
            continue
        for t in tr.findall(f".//{qn('t')}"):
            if not t.text:
                continue
            if name_tok in t.text:
                t.text = t.text.replace(name_tok, "{{ e.name }}")
            if type_tok in t.text:
                t.text = t.text.replace(type_tok, "{{ e.type }}")
        # Append blank lines to the first cell so each repeated easement is
        # spaced from the next (and the last from the Defects section below).
        first_cell = tr.find(qn("tc"))
        if first_cell is not None:
            for _ in range(EASEMENT_TRAILING_BLANKS):
                first_cell.append(blank_para())
        tr.addprevious(make_marker_row(tr, "{%tr for e in easements %}"))
        tr.addnext(make_marker_row(tr, "{%tr endfor %}"))
        return True
    return False


# ---------------------------------------------------------------------------
# RE 46-1 Title Chain table -> repeating row-pair
# ---------------------------------------------------------------------------
def template_chain_table(root: etree._Element) -> bool:
    tbl = root.find(f".//{qn('tbl')}")
    if tbl is None:
        return False
    rows = tbl.findall(qn("tr"))
    if len(rows) < 3:
        return False

    data_row = rows[1]      # 7 columns
    desc_row = rows[2]      # 3 cells, wide cell holds the label

    dcells = data_row.findall(qn("tc"))
    set_cell_text(dcells[0], "{{ e.grantor }}")
    set_cell_text(dcells[1], "{{ e.grantee }}")
    set_cell_text(dcells[2], "{{ e.date_signed }}")
    set_cell_text(dcells[3], "{{ e.date_recorded }}")
    set_cell_text(dcells[4], "{{ e.volume_page }}")
    set_cell_text(dcells[5], "{{ e.conveyance_fee }}")
    set_cell_text(dcells[6], "{{ e.instrument_type }}")

    ccells = desc_row.findall(qn("tc"))
    wide = max(ccells, key=lambda c: len("".join(c.itertext())) + 1)
    set_cell_text(wide, "Brief Land Description & Remarks:  {{ e.description }}")

    # Delete the remaining blank rows (entries 2..4 = rows 3..end).
    for extra in rows[3:]:
        tbl.remove(extra)

    # The data row + description row repeat together as one entry.
    data_row.addprevious(make_marker_row(data_row, "{%tr for e in chain %}"))
    desc_row.addnext(make_marker_row(data_row, "{%tr endfor %}"))
    return True


# ---------------------------------------------------------------------------
# RE 46-1 page header -> shared-field placeholders
# ---------------------------------------------------------------------------
def remove_plus_sign_note(root: etree._Element) -> bool:
    """Drop the obsolete 'click the PLUS SIGN to add rows' instruction."""
    for p in list(root.iter(qn("p"))):
        if "PLUS SIGN" in "".join(p.itertext()).upper():
            p.getparent().remove(p)
            return True
    return False


def template_chain_header(root: etree._Element) -> bool:
    cells = root.findall(f".//{qn('tc')}")
    pending = None
    label_rpr = None
    filled = 0
    for tc in cells:
        text = "".join(tc.itertext()).strip()
        if text == "DIST":
            pending, label_rpr = "{{ district }}", first_run_rpr(tc)
        elif text == "CRS":
            pending, label_rpr = "{{ crs }}", first_run_rpr(tc)
        elif text == "PID":
            pending, label_rpr = "{{ pid }}", first_run_rpr(tc)
        elif text == "PARCEL":
            pending, label_rpr = "PARCEL_COMBO", first_run_rpr(tc)
        elif pending is not None:
            if pending == "PARCEL_COMBO":
                set_cell_text(tc, "{{ parcel }}", label_rpr)
            else:
                set_cell_text(tc, pending, label_rpr)
            pending = None
            filled += 1
    return filled > 0


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------
def build_re46() -> None:
    src = os.path.join(SRC, "RE46_source.docx")
    out = os.path.join(OUT, "re46_template.docx")
    parts = read_parts(src)
    doc = parse(parts["word/document.xml"])
    n = replace_form_fields(doc)
    tax = template_tax_table(doc)
    eas = template_easements_row(doc)
    hdr = shift_header_block_left(doc)
    crs = set_crs_font_size(doc)
    changed = {"word/document.xml": serialize(doc)}
    write_docx(src, out, changed)
    print(f"[RE 46]   fields replaced: {n}; tax: {tax}; easements: {eas}; header shifted: {hdr}; crs font: {crs}")
    print(f"          -> {out}")


def build_chain() -> None:
    src = os.path.join(SRC, "RE46-1_source.docx")
    out = os.path.join(OUT, "re46_1_template.docx")
    parts = read_parts(src)
    doc = parse(parts["word/document.xml"])
    replace_form_fields(doc)  # strips stray SEQ chapter numbers ("1Grantor")
    chain_ok = template_chain_table(doc)
    remove_plus_sign_note(doc)
    changed = {"word/document.xml": serialize(doc)}
    # Header that carries the shared fields (DIST/CRS/PARCEL/PID).
    hdr_ok = False
    for name in parts:
        if name.startswith("word/header") and name.endswith(".xml"):
            h = parse(parts[name])
            if "PARCEL" in "".join(h.itertext()):
                if template_chain_header(h):
                    changed[name] = serialize(h)
                    hdr_ok = True
    write_docx(src, out, changed)
    print(f"[RE 46-1] chain table templated: {chain_ok}; header templated: {hdr_ok}")
    print(f"          -> {out}")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    build_re46()
    build_chain()
    print("Done.")
