#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6.0", "cryptography>=42"]
# ///
"""Inspect, fill, verify and render USCIS XFA/AcroForm hybrid PDFs.

Current USCIS PDFs carry two layers: an XFA dataset (what Adobe Acrobat/Reader
shows) and an AcroForm widget layer (what Preview, browsers, Ghostscript,
pdftotext and printers show). `fill` writes both: the XFA dataset is the source
of truth and the AcroForm layer is synced from it, so a filing copy rendered
without Adobe shows the same answers.

Subcommands:
    dump-fields PDF [--prefix P] [--acro] [--save JSON | --no-save] [--full]
    extract-values PDF [NAME...] [--prefix P] [--visible | --both] [--json] [--full]
    fill SOURCE OUTPUT MAPPING.json [--verify] [--report JSON] [--full]
    render-filing-copy SOURCE OUTPUT

Output is short by default: dump-fields prints at most 40 lines (the full list is in the
saved JSON), fill prints one capped line per kind of note, and extract-values prints one
line per name. --full prints everything.

`dump-fields` on a blank in a matter's output/working/forms/blank/ also saves the
full field list to output/working/forms/fields/<FORM>.json, so a later rerun or a
reviewer can rebuild without the session's scratch files.

`cryptography` is required because USCIS PDFs are AES-encrypted (empty user
password). `render-filing-copy` needs Ghostscript (`gs`) on PATH.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pypdf is required. Run this file with `uv run --script xfa_tools.py ...`."
    ) from exc

from forms_workflow import (
    default_field_dump_path,
    field_base,
    field_base_and_index,
    file_sha256,
    ghostscript,
    has_explicit_index,
    leaf_field_name,
    linked_checkbox_defects,
    payment_by_hand_bases,
    payment_form_of,
    qualified_base_and_index,
    widget_full_name,
)

# pypdf logs "Ignoring padding error" for some encrypted USCIS strings; it is harmless.
logging.getLogger("pypdf").setLevel(logging.ERROR)

XFA_DATA_NS = "http://www.xfa.org/schema/xfa-data/1.0/"
ET.register_namespace("xfa", XFA_DATA_NS)


# --------------------------------------------------------------------------- XFA dataset


def xfa_packet(reader: PdfReader, packet_name: str) -> bytes | None:
    acroform = reader.trailer["/Root"].get("/AcroForm")
    if not acroform:
        return None
    acroform = acroform.get_object()
    if "/XFA" not in acroform:
        return None
    xfa = acroform["/XFA"]
    for index in range(0, len(xfa), 2):
        if str(xfa[index]) == packet_name:
            return xfa[index + 1].get_object().get_data()
    return None


def xfa_dataset_bytes(pdf_path: Path) -> bytes:
    data = xfa_packet(PdfReader(str(pdf_path)), "datasets")
    if data is None:
        raise ValueError(
            f"No XFA datasets packet found in {pdf_path}. It is not a live XFA form "
            "(already rendered, or a plain AcroForm)."
        )
    return data


def dataset_root(pdf_path: Path) -> ET.Element:
    return ET.fromstring(xfa_dataset_bytes(pdf_path))


def dataset_form(root: ET.Element) -> ET.Element:
    data_node = root.find(f"{{{XFA_DATA_NS}}}data")
    if data_node is None:
        raise ValueError("XFA datasets packet is missing xfa:data")
    form_node = data_node.find("form1")
    if form_node is None:
        raise ValueError("XFA datasets packet is missing form1")
    return form_node


def node_key(field_name: str, global_names: set[str]) -> tuple[str, int]:
    """The XFA data node a mapping key binds.

    `Name` and `Name[0]` are the same node. A global field has one node that every
    widget shares, so `Name[2]` of a global field is that node too.
    """
    base, index = field_base_and_index(field_name)
    return base, 0 if base in global_names else index


def node_label(key: tuple[str, int]) -> str:
    return f"{key[0]}[{key[1]}]"


def _nth_child(parent: ET.Element, tag: str, index: int, create: bool) -> ET.Element | None:
    matches = [child for child in parent if child.tag == tag]
    if index < len(matches):
        return matches[index]
    if not create:
        return None
    while len(matches) <= index:
        matches.append(ET.SubElement(parent, tag))
    return matches[index]


def apply_fields(
    root: ET.Element,
    fields: dict[str, object],
    *,
    bindings: "FormBindings | None" = None,
    global_names: set[str] | frozenset[str] = frozenset(),
) -> None:
    """Write mapping values into the XFA dataset, each into the node Adobe reads for that box."""
    form_node = dataset_form(root)
    for field_name, value in expand_list_values(fields).items():
        if value is None:
            continue
        base, index = field_base_and_index(field_name)
        node = data_node(form_node, base, index, bindings=bindings, global_names=global_names, create=True)
        node.text = str(value)


def global_bound_names(reader: PdfReader) -> set[str]:
    """Names of template fields with <bind match="global"/>: every widget shares one value."""
    template = xfa_packet(reader, "template")
    if template is None:
        return set()
    try:
        root = ET.fromstring(template)
    except ET.ParseError:
        return set()
    names: set[str] = set()
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1]
        if local not in {"field", "exclGroup"} or not element.get("name"):
            continue
        for child in element:
            if child.tag.rsplit("}", 1)[-1] == "bind" and child.get("match") == "global":
                names.add(element.get("name"))
    return names


def _local_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


# --------------------------------------------------------------------------- XFA data binding
#
# Adobe shows each field the value of the XFA data node its template binds it to, and it reads
# nothing else. A field with normal binding inside a named subform reads from that subform's data
# group: the I-765's page subforms are named Page1 to Page7, so its date of birth lives at
# form1/Page3/Line19_DOB, not form1/Line19_DOB, and the I-485 Part 9 certifications table lives
# at form1/Table1/Row1/TextField1. Unnamed subforms and areas add no group. A global field shares
# one node directly under form1. A field with <bind match="none"/> has no data node at all, so
# Adobe shows it empty whatever the dataset holds; `fill` binds those normally before it writes
# them (rebind_unbound_fields). Every writer and reader below goes through data_node(), so
# `fill --verify`, `extract-values`, the visible-layer sync and the audit read the node Adobe reads.

TEMPLATE_FIELD_TAGS = {"field", "exclGroup"}
TEMPLATE_CONTAINER_TAGS = {"subform", "subformSet", "area"}


@dataclass(frozen=True)
class DataSlot:
    """The XFA data node one template field reads: form1/<groups>/<name>[occurrence]."""

    binding: str  # "once" (normal), "global", "none", or another <bind match="..."> value
    groups: tuple[tuple[str, int], ...]  # data groups under form1, outermost first, with occurrence
    name: str
    occurrence: int  # among the values of that name in the innermost group; -1 when not bound

    def label(self) -> str:
        if self.binding == "global":
            return f"form1/{self.name} (global)"
        if self.binding != "once":
            return f"unbound ({self.binding})"
        parts = [f"{name}[{index}]" for name, index in self.groups]
        return "/".join(["form1", *parts, f"{self.name}[{self.occurrence}]"])


@dataclass(frozen=True)
class TemplateField:
    som: str  # the qualified name of its AcroForm widget, e.g. form1[0].Page2[0].Line12b_SSN[0]
    name: str
    slot: DataSlot
    position: int  # its index among the template's <field> elements of this name, in document order


def _bind_match(element: ET.Element) -> str:
    for child in element:
        if _local_tag(child) == "bind":
            return child.get("match") or "once"
    return "once"


def template_fields(template: bytes | None) -> list[TemplateField]:
    """Every field of an XFA template with its SOM name and the data node it binds.

    SOM names follow the AcroForm names Acrobat gave the widgets: a named node is
    `Name[n]`, n counting same-named nodes in the nearest named container (unnamed subforms and
    areas are transparent), and an unnamed one is `#subform[n]` or `#area[n]`, n counting every
    node of that class there. Data binding follows XFA's direct match: a named subform with
    normal binding opens the data group of its name (the nth such subform the nth group), and the
    nth normally bound field of a name in a group reads the nth value of that name. Page sets
    (master pages: barcodes, page numbers) are skipped; their widgets repeat on every page.
    """
    if not template:
        return []
    try:
        root = ET.fromstring(template)
    except ET.ParseError:
        return []
    position_of: dict[int, int] = {}
    seen_names: dict[str, int] = defaultdict(int)
    for element in root.iter():
        if _local_tag(element) == "field":
            name = element.get("name") or ""
            position_of[id(element)] = seen_names[name]
            seen_names[name] += 1

    fields: list[TemplateField] = []

    def walk(element, som, som_counts, groups, data_counts) -> None:
        for child in element:
            tag = _local_tag(child)
            if tag not in TEMPLATE_FIELD_TAGS | TEMPLATE_CONTAINER_TAGS | {"draw"}:
                continue  # page sets, scripts, protos and properties hold no bound fields
            name = child.get("name") or ""
            class_index = som_counts[("class", tag)]
            som_counts[("class", tag)] += 1
            if name:
                index = som_counts[("name", name)]
                som_counts[("name", name)] += 1
                escaped = name.replace(".", "\\.")  # a literal dot is escaped in SOM names
                part = f"{escaped}[{index}]"
            else:
                part = f"#{tag}[{class_index}]"
            path = f"{som}.{part}"
            match = _bind_match(child)
            if tag in TEMPLATE_FIELD_TAGS:
                if match == "once" and name:
                    occurrence = data_counts[("value", name)]
                    data_counts[("value", name)] += 1
                    slot = DataSlot("once", groups, name, occurrence)
                elif match == "global":
                    slot = DataSlot("global", (), name, 0)
                else:
                    slot = DataSlot(match if name else "none", groups, name, -1)
                fields.append(TemplateField(path, name, slot, position_of.get(id(child), -1)))
                continue
            if tag == "draw":
                continue
            if tag == "subform" and name and match == "once":
                occurrence = data_counts[("group", name)]
                data_counts[("group", name)] += 1
                walk(child, path, defaultdict(int), groups + ((name, occurrence),), defaultdict(int))
            elif name:  # a named area, or a named subform bound otherwise: a SOM scope, not a data group
                walk(child, path, defaultdict(int), groups, data_counts)
            else:
                walk(child, path, som_counts, groups, data_counts)

    for top in root:
        if _local_tag(top) == "subform" and top.get("name"):
            walk(top, f"{top.get('name')}[0]", defaultdict(int), (), defaultdict(int))
    return fields


class FormBindings:
    """For every box of a form (a field base and its [n]), the template field it shows."""

    def __init__(self, fields: list[TemplateField], acro: dict[str, list["AcroField"]]):
        self.fields = fields
        by_som = {field.som: field for field in fields}
        self.boxes: dict[str, list[TemplateField | None]] = {
            base: [by_som.get(spec.full_name) for spec in specs] for base, specs in acro.items()
        }
        for field in fields:  # a field with no widget is addressed in template order
            if field.name not in acro:
                self.boxes.setdefault(field.name, []).append(field)

    @classmethod
    def from_reader(cls, reader: PdfReader, acro: dict[str, list["AcroField"]] | None = None) -> "FormBindings":
        return cls(template_fields(xfa_packet(reader, "template")), acro if acro is not None else acro_fields_by_base(reader))

    def field(self, base: str, index: int) -> TemplateField | None:
        boxes = self.boxes.get(base, [])
        return boxes[index] if 0 <= index < len(boxes) else None

    def slot(self, base: str, index: int) -> DataSlot | None:
        field = self.field(base, index)
        return field.slot if field is not None else None


def slot_node(form_node: ET.Element, slot: DataSlot, create: bool = False) -> ET.Element | None:
    node: ET.Element | None = form_node
    for group, occurrence in slot.groups:
        node = _nth_child(node, group, occurrence, create)
        if node is None:
            return None
    return _nth_child(node, slot.name, slot.occurrence, create)


def data_node(
    form_node: ET.Element,
    base: str,
    index: int,
    *,
    bindings: FormBindings | None,
    global_names: set[str] | frozenset[str],
    create: bool = False,
) -> ET.Element | None:
    """The XFA data node box `index` of field `base` shows in Adobe (created if asked).

    A global field's one node sits directly under form1. A normally bound field's node is where
    its template binds it. Anything else (no template, a field the template leaves unbound, a
    dataRef binding) falls back to the node of that name and index directly under form1, where
    earlier versions wrote; Adobe does not read that node for an unbound field.
    """
    if base in global_names:
        return _nth_child(form_node, base, 0, create)
    slot = bindings.slot(base, index) if bindings is not None else None
    if slot is not None and slot.binding == "once":
        return slot_node(form_node, slot, create)
    return _nth_child(form_node, base, index, create)


def dataset_value_names(form_node: ET.Element) -> list[str]:
    """Names of the dataset's data values (leaf nodes) at any depth, first-seen order."""
    names: dict[str, None] = {}
    for child in form_node:
        names.setdefault(child.tag, None)
    for element in form_node.iter():
        if element is not form_node and len(element) == 0:
            names.setdefault(element.tag, None)
    return list(names)


def rebind_unbound_fields(
    template: bytes, fields: list[TemplateField], targets: list[TemplateField]
) -> tuple[bytes, list[str], list[str]]:
    """Bind the template's unbound target fields normally so Adobe shows a value written for them.

    <bind match="none"/> becomes <bind match="once"/> in the filled source's template only (the
    blank and the AcroForm layer are untouched). A name is rebound in every field of its data
    group at once, so occurrence numbers stay in step, and only when no other field of that name
    in the group is bound, and no global field has that name: otherwise the new binding could
    take another field's value. The template text is edited in place, not re-serialized, and the
    result is re-parsed to confirm that exactly those fields changed.

    Returns (template, rebound names, names left unbound).
    """
    wanted = {(field.slot.groups, field.name) for field in targets if field.slot.binding == "none" and field.name}
    if not wanted:
        return template, [], []
    global_names = {field.name for field in fields if field.slot.binding == "global"}
    groups: dict[tuple, list[TemplateField]] = defaultdict(list)
    for field in fields:
        groups[(field.slot.groups, field.name)].append(field)
    rebind: list[TemplateField] = []
    left: set[str] = set()
    for key in sorted(wanted, key=lambda item: item[1]):
        members = groups[key]
        if key[1] in global_names or any(member.slot.binding != "none" for member in members):
            left.add(key[1])
        else:
            rebind.extend(members)
    if not rebind:
        return template, [], sorted(left)

    edits: list[tuple[int, int]] = []  # (offset of match="none", length) to rewrite
    for field in rebind:
        tag_re = re.compile(rb'<field\b(?=[^>]*\bname="' + re.escape(field.name.encode()) + rb'")[^>]*>')
        starts = [match for match in tag_re.finditer(template)]
        if field.position < 0 or field.position >= len(starts):
            return template, [], sorted(left | {field.name for field in rebind})
        start = starts[field.position].end()
        end = template.find(b"</field", start)
        end = len(template) if end < 0 else end
        bind = re.compile(rb'<bind\b[^>]*?\bmatch="none"').search(template, start, end)
        if bind is None:
            return template, [], sorted(left | {field.name for field in rebind})
        offset = template.index(b'match="none"', bind.start(), bind.end())
        edits.append((offset, len(b'match="none"')))
    patched = template
    for offset, length in sorted(set(edits), reverse=True):
        patched = patched[:offset] + b'match="once"' + patched[offset + length :]

    targets_som = {field.som for field in rebind}
    before = {field.som: field.slot.binding for field in fields}
    after = {field.som: field.slot.binding for field in template_fields(patched)}
    expected = {som: ("once" if som in targets_som else binding) for som, binding in before.items()}
    if after != expected:  # the text edit hit something else: keep the template as it was
        return template, [], sorted(left | {field.name for field in rebind})
    return patched, sorted({field.name for field in rebind}), sorted(left)


# --------------------------------------------------------------------------- AcroForm layer


@dataclass
class AcroField:
    full_name: str
    base: str
    acro_index: int
    field_type: str
    on_states: tuple[str, ...]
    tooltip: str = ""
    max_len: int | None = None
    pages: list[int] = field(default_factory=list)


def _states(raw: object) -> tuple[str, ...]:
    """Button on-states, or choice-list export values ([export, display] pairs)."""
    if not isinstance(raw, list):
        return ()
    states = []
    for item in raw:
        if isinstance(item, list) and item:
            item = item[0]
        text = str(item)
        if text.startswith("/"):
            text = text[1:]
        if text.strip() and text != "Off":
            states.append(text)
    return tuple(states)


def matching_state(states: tuple[str, ...], value: str) -> str | None:
    """On-state equal to value; USCIS uses padded states such as ' STE ', so compare stripped."""
    wanted = value.strip()
    if not wanted:
        return None
    for state in states:
        if state == value or state.strip() == wanted:
            return state
    return None


def acro_fields_by_base(reader: PdfReader) -> dict[str, list[AcroField]]:
    """Terminal AcroForm fields grouped by leaf base name, in field-tree order."""
    # Keyed by the escape-aware leaf of each widget's qualified name, the same key the
    # get_fields() loop below uses. A widget's own /T is not enough: the N-400 item 7.b
    # boxes are nested (P9_Line7\ > b\ > [0]), so their own /T is just "[0]".
    page_of: dict[str, list[int]] = defaultdict(list)
    max_len_of: dict[str, int] = {}
    for page_number, page in enumerate(reader.pages, start=1):
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            holder = annot
            if "/T" not in annot and annot.get("/Parent") is not None:
                holder = annot["/Parent"].get_object()
            name = leaf_field_name(widget_full_name(annot))
            if name:
                page_of[name].append(page_number)
                max_len = annot.get("/MaxLen", holder.get("/MaxLen"))
                if max_len is not None:
                    max_len_of[name] = int(max_len)

    grouped: dict[str, list[AcroField]] = defaultdict(list)
    for full_name, spec in (reader.get_fields() or {}).items():
        field_type = str(spec.get("/FT") or "")
        if not field_type:
            continue
        leaf = leaf_field_name(full_name)
        base, index = qualified_base_and_index(full_name)
        max_len = spec.get("/MaxLen", max_len_of.get(leaf))
        grouped[base].append(
            AcroField(
                full_name=full_name,
                base=base,
                acro_index=index,
                field_type=field_type,
                on_states=_states(spec.get("/_States_")),
                tooltip=str(spec.get("/TU") or ""),
                max_len=int(max_len) if max_len is not None else None,
                pages=sorted(set(page_of.get(leaf, []))),
            )
        )
    return grouped


def display_value(value: object | None) -> str:
    """A field's /V or a widget's /AS as text: a name loses its slash, and Off is blank."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith("/"):
        text = text[1:]
    return "" if text == "Off" else text


def visible_values(pdf_path: Path, *, reader: PdfReader | None = None) -> dict[str, list[str]]:
    """AcroForm (visible-layer) values grouped by base name in tree order."""
    reader = reader or PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}
    widget_state: dict[str, str] = {}
    for page in reader.pages:
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget" or "/AS" not in annot:
                continue
            name = leaf_field_name(widget_full_name(annot))
            state = str(annot["/AS"]).lstrip("/")
            if state and state != "Off":
                widget_state[name] = state
    grouped: dict[str, list[str]] = defaultdict(list)
    for full_name, spec in fields.items():
        field_type = str(spec.get("/FT") or "")
        if not field_type:
            continue
        base, _ = qualified_base_and_index(full_name)
        value = display_value(spec.get("/V"))
        if field_type == "/Btn" and not value:
            value = widget_state.get(leaf_field_name(full_name), "")
        grouped[base].append(value)
    return grouped


def acro_updates_for(
    *,
    touched_bases: set[str],
    form_node: ET.Element,
    acro: dict[str, list[AcroField]],
    global_names: set[str],
    bindings: FormBindings | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Translate the final XFA dataset values of touched bases into AcroForm updates.

    Each widget shows the data node Adobe shows for it (data_node). A widget with no node of
    its own (an unbound repeated box, such as the I-485 prior-marriage place when only the
    current-marriage place was written) is cleared rather than given another box's value.
    """
    updates: dict[str, str] = {}
    xfa_only: list[str] = []
    for base in sorted(touched_bases):
        fields = acro.get(base, [])
        if not fields:
            xfa_only.append(base)
            continue
        pairs = []
        for position, spec in enumerate(fields):
            node = data_node(form_node, base, position, bindings=bindings, global_names=global_names)
            pairs.append((spec, (node.text or "") if node is not None else ""))
        for spec, value in pairs:
            if spec.field_type == "/Btn":
                state = matching_state(spec.on_states, value)
                updates[spec.full_name] = f"/{state}" if state is not None else "/Off"
            else:
                updates[spec.full_name] = value
    return updates, xfa_only


def normalize_button_values(
    fields: dict[str, object], acro: dict[str, list[AcroField]]
) -> tuple[dict[str, object], dict[str, str]]:
    """Rewrite checkbox values to the form's exact on-state (e.g. "STE" -> " STE ").

    XFA only checks a box when the stored value equals the template's on-value
    exactly, padding included, so a near-miss would leave Adobe's view unchecked.
    """
    normalized: dict[str, object] = {}
    changes: dict[str, str] = {}
    for name, value in fields.items():
        base, _ = field_base_and_index(name)
        specs = acro.get(base, [])
        if isinstance(value, str) and specs and all(spec.field_type == "/Btn" for spec in specs):
            states = tuple(state for spec in specs for state in spec.on_states)
            state = matching_state(states, value)
            if state is not None and state != value:
                changes[name] = state
                value = state
        normalized[name] = value
    return normalized, changes


@dataclass
class SharedNode:
    """Several mapping keys that bind one XFA data node, and the value kept for it."""

    node: str
    fields: list[str]
    value: str
    ignored_empty: list[str]
    is_global: bool


def expand_list_values(fields: dict[str, object]) -> dict[str, object]:
    """Turn `"Name": [v0, v1]` into `"Name[0]": v0, "Name[1]": v1`, keeping mapping order."""
    expanded: dict[str, object] = {}
    for name, value in fields.items():
        if not isinstance(value, (list, tuple)):
            expanded[name] = value
            continue
        if has_explicit_index(name):
            raise ValueError(f"Indexed field cannot take a list value: {name}")
        for offset, item in enumerate(value):
            expanded[f"{name}[{offset}]"] = "" if item is None else item
    return expanded


def resolve_shared_nodes(
    fields: dict[str, object], global_names: set[str]
) -> tuple[dict[str, object], list[SharedNode]]:
    """Give every XFA data node exactly one value before anything is written.

    Two mapping keys can bind the same node: `Name` and `Name[0]`, or any two
    occurrences of a global field. Writing both in turn would let the later one
    silently replace the earlier one, so:

    - different non-empty values for one node are an error that names both keys;
    - an empty value never overwrites a non-empty one;
    - each shared node is reported, so `--verify` can explain what it checked.

    Returns the mapping with one key per node (global fields under their base name)
    and the list of shared nodes.
    """
    groups: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for name, value in expand_list_values(fields).items():
        if value is None:
            continue
        groups.setdefault(node_key(name, global_names), []).append((name, str(value)))

    resolved: dict[str, object] = {}
    shared: list[SharedNode] = []
    conflicts: list[str] = []
    for key, entries in groups.items():
        base, index = key
        is_global = base in global_names
        write_name = base if is_global else entries[0][0]
        if len(entries) == 1:
            resolved[write_name] = entries[0][1]
            continue
        nonempty = [(name, value) for name, value in entries if value.strip()]
        if len({value.strip() for _, value in nonempty}) > 1:
            listed = " and ".join(f"{name} = {value!r}" for name, value in nonempty)
            why = (
                f"{base} is a global field, so all its boxes share one value"
                if is_global
                else f"{base} and {base}[0] are the same node"
            )
            conflicts.append(
                f"{listed} bind the same XFA data node ({node_label(key)}; {why}). "
                "Only one value can be stored there. Keep one of them, or use the [n] index "
                "of the box you meant (check its tooltip with dump-fields --acro)."
            )
            continue
        kept_name, kept_value = nonempty[0] if nonempty else entries[0]
        resolved[write_name if is_global else kept_name] = kept_value
        shared.append(
            SharedNode(
                node=node_label(key),
                fields=[name for name, _ in entries],
                value=kept_value,
                ignored_empty=[name for name, value in entries if not value.strip()] if nonempty else [],
                is_global=is_global,
            )
        )
    if conflicts:
        raise ValueError("Conflicting mapping entries:\n- " + "\n- ".join(conflicts))
    return resolved, shared


def describe_shared_node(item: SharedNode) -> str:
    names = ", ".join(item.fields)
    text = f"{names} bind the same XFA data node ({item.node})"
    if item.is_global:
        text += " because the field is global"
    text += f". Kept {item.value!r}"
    if item.ignored_empty:
        text += f"; the empty value of {', '.join(item.ignored_empty)} was not written over it"
    return text + ". --verify checks the kept value for all of them."


def describe_linked_defect(defect: dict[str, object], value: str) -> str:
    text = f"{defect['form']} known defect: {defect['problem']} {defect['action']}"
    label = dict(defect["states"]).get(value.strip())
    if label:
        text += f" The mapping sets {defect['base']} to {value!r}, so only {label} is checked."
    return text


# pypdf (6.x) opens each text appearance stream with a clip, `x y w h re W`, and no `n`
# after it. Without a painting operator the clip never takes effect, and the rectangle stays
# the current path: Ghostscript strokes it later on the page, so the filing copy shows an
# empty box away from any field (the N-400 page 4 A-Number box over Part 5 item 5.b).
APPEARANCE_OPEN_CLIP_RE = re.compile(rb"^(q\s*/Tx BMC\s*q\s*)[-+0-9.\s]+re\s+W\s+(?!n\b)")


def unclosed_clip_paths(writer_or_reader: PdfReader | PdfWriter) -> list[tuple[object, object]]:
    """(widget, normal appearance stream) pairs whose stream leaves its clip path open."""
    found = []
    for page in writer_or_reader.pages:
        annots = page.get("/Annots")
        for annot_ref in annots.get_object() if annots is not None else []:
            annot = annot_ref.get_object()
            appearance = annot.get("/AP")
            normal = appearance.get_object().get("/N") if appearance is not None else None
            stream = normal.get_object() if normal is not None else None
            if stream is None or not hasattr(stream, "get_data"):
                continue  # no appearance, or a checkbox's dictionary of state streams
            try:
                data = stream.get_data()
            except Exception:  # noqa: BLE001 - an unreadable stream is not ours to fix
                continue
            if APPEARANCE_OPEN_CLIP_RE.match(data):
                found.append((annot, stream))
    return found


def close_appearance_clips(writer: PdfWriter) -> int:
    """Rewrite the open clip of each generated text appearance as `0 0 w h re W n`.

    The clip becomes the appearance's own box (its /BBox), closed with `n`. That is the
    clip the filing copy has always had in practice (Ghostscript ignores the open one and
    the form box clips), so text renders exactly as before, minus the stray box. Closing
    pypdf's narrower clip instead would cut text that renders whole today, such as an
    N-400 Part 7 date centred edge to edge in its 60 pt box.
    """
    fixed = 0
    for annot, stream in unclosed_clip_paths(writer):
        data = stream.get_data()
        match = APPEARANCE_OPEN_CLIP_RE.match(data)
        raw_box = stream.get("/BBox") or annot.get("/Rect")
        x0, y0, x1, y1 = (float(value) for value in raw_box)
        if stream.get("/BBox") is None:  # a /Rect is in page space; the stream's is local
            x1, y1, x0, y0 = x1 - x0, y1 - y0, 0.0, 0.0
        clip = f"{x0:.3f} {y0:.3f} {x1 - x0:.3f} {y1 - y0:.3f} re\nW\nn\n".encode()
        stream.set_data(match.group(1) + clip + data[match.end():])
        fixed += 1
    return fixed


def strip_usage_rights(writer: PdfWriter) -> None:
    """Drop the Adobe usage-rights signature; it is invalid once the file changes."""
    if "/Perms" in writer._root_object:
        del writer._root_object["/Perms"]


@dataclass
class FillResult:
    fields: dict[str, object]  # one key per XFA data node, as written
    xfa_only: list[str]  # bases with no visible widget
    normalized: dict[str, str]  # checkbox values rewritten to the exact on-state
    shared: list[SharedNode]  # mapping keys that bound one data node
    defects: list[str]  # known defects of this form edition, as warnings
    # Fields the template left unbound (<bind match="none"/>) that fill bound normally so Adobe
    # shows their values, and those it could not rebind (Adobe shows them empty):
    rebound: list[str] = field(default_factory=list)
    adobe_unbound: list[str] = field(default_factory=list)
    # Values longer than their box's maxlen (Adobe truncates them), one message each.
    length_warnings: list[str] = field(default_factory=list)
    defect_briefs: list[str] = field(default_factory=list)  # `defects`, one short line each


def write_filled_pdf(
    source_pdf: Path,
    output_pdf: Path,
    fields: dict[str, object],
) -> FillResult:
    """Write fields into the XFA dataset and the visible AcroForm layer."""
    reader = PdfReader(str(source_pdf))
    acro = acro_fields_by_base(reader)
    payment_form = payment_form_of(set(acro))
    if payment_form:
        # The payer writes the card or bank details by hand: never put one in a payment form.
        by_hand = payment_by_hand_bases(payment_form)
        typed = sorted(
            name for name, value in fields.items()
            if field_base(str(name)) in by_hand and str(value if value is not None else "").strip()
        )
        if typed:
            raise ValueError(
                f"this is a {payment_form.upper()}, and {', '.join(typed)} hold card or bank details, which only the "
                "payer writes, by hand; nothing was written"
            )
    global_names = global_bound_names(reader)
    fields, normalized = normalize_button_values(expand_list_values(fields), acro)
    fields, shared = resolve_shared_nodes(fields, global_names)

    # Where Adobe reads each box. Unbound fields that get a value are bound normally first, in
    # this file's template only, so Adobe shows them; the bindings are then worked out again.
    template = xfa_packet(reader, "template")
    in_template = template_fields(template)
    bindings = FormBindings(in_template, acro)
    unbound_targets = []
    for name, value in fields.items():
        base, index = field_base_and_index(name)
        target = bindings.field(base, index) if base not in global_names else None
        if target is not None and target.slot.binding == "none" and str(value or "").strip():
            unbound_targets.append(target)
    new_template, rebound, left_unbound = (
        rebind_unbound_fields(template, in_template, unbound_targets) if template else (template, [], [])
    )
    if rebound:
        bindings = FormBindings(template_fields(new_template), acro)
    found_defects = linked_checkbox_defects(
        {base: {state for spec in specs for state in spec.on_states} for base, specs in acro.items()}
    )
    defects = [describe_linked_defect(defect, str(fields.get(str(defect["base"])) or "")) for defect in found_defects]
    defect_briefs = [
        f"known defect, {defect['form']}: {defect.get('brief') or defect['problem']}" for defect in found_defects
    ]
    length_warnings: list[str] = []
    for name, value in fields.items():
        base, index = field_base_and_index(name)
        specs = acro.get(base, [])
        spec = specs[index] if index < len(specs) else None
        if spec and spec.max_len and isinstance(value, str) and len(value) > spec.max_len:
            length_warnings.append(
                f"{name} is {len(value)} characters but the box allows {spec.max_len} "
                f"(...{spec.tooltip[-70:]!r}); Adobe will truncate it, and the audit reports it as an "
                "error. Check the field choice, or move the answer to Additional Information."
            )

    datasets = xfa_packet(reader, "datasets")
    if datasets is None:
        raise ValueError(f"No XFA datasets packet found in {source_pdf}")
    root = ET.fromstring(datasets)
    apply_fields(root, fields, bindings=bindings, global_names=global_names)
    new_dataset = ET.tostring(root, encoding="utf-8", xml_declaration=False)

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    acroform = writer._root_object["/AcroForm"].get_object()
    xfa = acroform["/XFA"]
    for index in range(0, len(xfa), 2):
        if str(xfa[index]) == "datasets":
            stream = DecodedStreamObject()
            stream.set_data(new_dataset)
            xfa[index + 1] = writer._add_object(stream)
            break
    else:
        raise ValueError(f"No XFA datasets packet found in {source_pdf}")
    if rebound:
        for index in range(0, len(xfa), 2):
            if str(xfa[index]) == "template":
                stream = DecodedStreamObject()
                stream.set_data(new_template)
                xfa[index + 1] = writer._add_object(stream.flate_encode())
                break

    touched = {field_base_and_index(name)[0] for name, value in fields.items() if value is not None}
    updates, xfa_only = acro_updates_for(
        touched_bases=touched,
        form_node=dataset_form(root),
        acro=acro,
        global_names=global_names,
        bindings=bindings,
    )
    if updates:
        check_font_coverage(reader, updates)
        writer.update_page_form_field_values(None, updates, auto_regenerate=True)
    close_appearance_clips(writer)

    strip_usage_rights(writer)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as fh:
        writer.write(fh)
    return FillResult(
        fields, xfa_only, normalized, shared, defects, rebound, left_unbound, length_warnings, defect_briefs
    )


def check_font_coverage(reader: PdfReader, updates: dict[str, object]) -> None:
    """Refuse unsupported glyphs before pypdf can silently substitute or corrupt them.

The pinned pypdf font decoder supplies the field's actual encoding. Unknown CID
fonts require a Unicode map; encoding UTF-16 alone does not prove glyph coverage.
"""
    from pypdf._cmap import get_encoding
    acro = reader.trailer["/Root"]["/AcroForm"].get_object()
    resources = acro.get("/DR", {}).get_object() if hasattr(acro.get("/DR", {}), "get_object") else acro.get("/DR", {})
    fonts = resources.get("/Font", {})
    fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
    for name, spec in (reader.get_fields() or {}).items():
        if spec.get("/FT") != "/Tx" or name not in updates:
            continue
        value = str(updates[name] or "")
        chars = {c for c in value if ord(c) > 127}
        if not chars:
            continue
        da = str(spec.get("/DA") or acro.get("/DA") or "")
        match = re.search(r"(/[^\s]+)\s+[\d.]+\s+Tf", da)
        resource = fonts.get(match[1]) if match else None
        supported: set[str] = set()
        if resource is not None:
            font = resource.get_object()
            encoding, character_map = get_encoding(font)
            supported.update(v for v in character_map.values() if isinstance(v, str))
            if isinstance(encoding, dict):
                supported.update(encoding.values())
            elif font.get("/Subtype") != "/Type0" and encoding not in {"utf-16-be", "utf-16"}:
                for c in chars:
                    try:
                        c.encode(encoding, errors="strict")
                        supported.add(c)
                    except (UnicodeError, LookupError):
                        pass
        missing = chars - supported
        if missing:
            codes = ", ".join(f"U+{ord(c):04X}" for c in sorted(missing))
            raise ValueError(f"Field {leaf_field_name(name)} cannot safely render {codes}. Nothing was written. "
                             "Use a verified font-capable form workflow or attorney-reviewed manual completion; never silently transliterate a name.")


def resolve_mapping(pdf_path: Path, fields: dict[str, object]) -> dict[str, object]:
    """A mapping as `fill` writes it into this form: list values expanded, checkbox values
    set to the form's exact on-states, and keys that share a data node merged. This is what
    `verify_output` checks, so a filled source can be re-verified without refilling it."""
    reader = PdfReader(str(pdf_path))
    fields, _ = normalize_button_values(expand_list_values(fields), acro_fields_by_base(reader))
    fields, _ = resolve_shared_nodes(fields, global_bound_names(reader))
    return fields


def _names(items: list[str], limit: int) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f", +{len(items) - limit} more" if len(items) > limit else "")


def fill_messages(result: FillResult, *, full: bool = False) -> list[str]:
    """What fill has to tell the preparer, one line per kind of note ("note: ..." or
    "warning: ..."). Short by default: name lists are capped. full=True lists every name."""
    limit = 10**6 if full else 6
    lines: list[str] = []
    if result.normalized:
        if full:
            lines.extend(
                f"note: {name} written as the form's exact on-state {state!r}"
                for name, state in result.normalized.items()
            )
        else:
            examples = [f"{name}={state!r}" for name, state in result.normalized.items()]
            lines.append(
                f"note: {len(examples)} checkbox value(s) written as the form's exact on-state "
                f"({_names(examples, 3)})"
            )
    for text in result.length_warnings[: None if full else 4]:
        lines.append(f"warning: {text}")
    if not full and len(result.length_warnings) > 4:
        lines.append(f"warning: +{len(result.length_warnings) - 4} more values longer than their box")
    if result.xfa_only:
        lines.append(
            f"note: {len(result.xfa_only)} field(s) have no visible AcroForm widget (XFA-only: Adobe "
            f"shows them, a rendered copy will not): {_names(result.xfa_only, limit)}"
        )
    if result.rebound:
        lines.append(
            f"note: {len(result.rebound)} filled field(s) are unbound in the blank's XFA template "
            '(<bind match="none"/>); fill bound them in this file so Adobe shows them (blank and '
            f"filing copy unchanged): {_names(result.rebound, limit)}"
        )
    if result.adobe_unbound:
        lines.append(
            f"warning: {len(result.adobe_unbound)} filled field(s) are unbound in the form's XFA template "
            "and could not be bound without taking another field's data, so Adobe opening the XFA source "
            "shows them empty; the filing copy and other viewers show them. Check these on the filing "
            f"copy, and do not save the source from Adobe: {_names(result.adobe_unbound, limit)}"
        )
    shared = result.shared if full else result.shared[:3]
    lines.extend(f"warning: {describe_shared_node(item)}" for item in shared)
    if len(result.shared) > len(shared):
        lines.append(f"warning: +{len(result.shared) - len(shared)} more mapping keys that share a data node")
    briefs = result.defect_briefs if not full and len(result.defect_briefs) == len(result.defects) else result.defects
    lines.extend(f"warning: {text}" for text in briefs)
    return lines


def verify_lines(mismatches: dict, *, limit: int = 5) -> list[str]:
    """One line per mismatch from verify_output, capped."""
    lines: list[str] = []
    for layer in ("xfa", "visible"):
        for name, detail in dict(mismatches.get(layer) or {}).items():
            detail = dict(detail)
            expected = detail.pop("expected", "")
            got = "; ".join(f"{key.replace('_', ' ')} {value!r}" for key, value in detail.items())
            got = got.replace("'(nothing: ", "(nothing: ").replace("unbound)'", "unbound)")
            lines.append(f"  {layer}: {name}: expected {expected!r}, {got}")
    if len(lines) > limit:
        lines = lines[:limit] + [f"  +{len(lines) - limit} more"]
    return lines


def render_filing_copy(source_pdf: Path, output_pdf: Path) -> None:
    gs = ghostscript()
    if gs is None:
        raise SystemExit(
            "Ghostscript is required to render a filing copy and was not found on PATH. "
            "Install it (macOS: `brew install ghostscript`; Debian/Ubuntu: "
            "`apt install ghostscript`; Windows: the ghostscript.com installer, then put "
            "gswin64c on PATH)."
        )
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_pdf.with_name(f"{output_pdf.stem}.rendering.tmp{output_pdf.suffix}")
    temp_output.unlink(missing_ok=True)
    subprocess.run(
        [gs, "-o", str(temp_output), "-sDEVICE=pdfwrite", "-dNOPAUSE", "-dBATCH", "-dQUIET", str(source_pdf)], check=True
    )
    temp_output.replace(output_pdf)


# --------------------------------------------------------------------------- verification


@dataclass
class LiveForm:
    """A filled form read once for every check made on it: its AcroForm, its XFA data and the
    template's bindings."""

    reader: PdfReader
    data: ET.Element | None  # form1 of the XFA dataset; None when the PDF has none (a rendered copy)
    acro: dict[str, list[AcroField]]
    global_names: set[str]
    bindings: FormBindings

    @classmethod
    def read(cls, pdf_path: Path) -> "LiveForm":
        reader = PdfReader(str(pdf_path))
        datasets = xfa_packet(reader, "datasets")
        data = dataset_form(ET.fromstring(datasets)) if datasets is not None else None
        acro = acro_fields_by_base(reader)
        return cls(reader, data, acro, global_bound_names(reader), FormBindings.from_reader(reader, acro))


def extract_values(
    pdf_path: Path, field_names: list[str], *, per_widget: bool = True, live: LiveForm | None = None
) -> dict[str, str]:
    """Stored XFA values. `Name` and `Name[0]` read the same node.

    A global field has one node for all its widgets, so every `[n]` reads that value.
    For a global checkbox group (per_widget=True) `Name[n]` reads as box n's state:
    the group's value when it selects box n, else blank. That matches what
    `--visible` returns for the same name, so the two layers can be compared index
    by index. `Name` alone returns the group's value. With per_widget=False every
    name reads its data node as stored (what `fill --verify` checks).

    Each name reads the node Adobe reads for that box (data_node), so a value stored where
    Adobe does not look reads as blank here too.
    """
    live = live or LiveForm.read(pdf_path)
    if live.data is None:
        raise ValueError(
            f"No XFA datasets packet found in {pdf_path}. It is not a live XFA form "
            "(already rendered, or a plain AcroForm)."
        )
    global_names = live.global_names
    result: dict[str, str] = {}
    for name in field_names:
        lookup = name.replace("\\", "")
        base, index = node_key(lookup, global_names)
        node = data_node(live.data, base, index, bindings=live.bindings, global_names=global_names)
        value = (node.text or "") if node is not None else ""
        specs = live.acro.get(base, []) if per_widget else []
        _, widget = field_base_and_index(lookup)
        if (
            base in global_names
            and has_explicit_index(lookup)
            and specs
            and all(spec.field_type == "/Btn" for spec in specs)
            and widget < len(specs)
        ):
            value = value if matching_state(specs[widget].on_states, value) is not None else ""
        result[name] = value
    return result


def adobe_view(pdf_path: Path, field_names: list[str], *, live: LiveForm | None = None) -> dict[str, str | None]:
    """What Adobe shows for each name when it opens the XFA source.

    That is the value of the data node the template binds the box to, or None when the
    template leaves the box unbound (Adobe keeps no data for it, whatever the dataset holds).
    A name the template does not describe reads the node fill would use.
    """
    live = live or LiveForm.read(pdf_path)
    if live.data is None:
        return {}
    shown: dict[str, str | None] = {}
    for name in field_names:
        base, index = node_key(name, live.global_names)
        slot = live.bindings.slot(base, index) if base not in live.global_names else None
        if slot is not None and slot.binding not in {"once", "global"}:
            shown[name] = None
            continue
        node = data_node(live.data, base, index, bindings=live.bindings, global_names=live.global_names)
        shown[name] = (node.text or "") if node is not None else ""
    return shown


def stored_values(pdf_path: Path) -> dict[str, str]:
    """Every box's stored XFA value, read where Adobe reads it, for the audit.

    Keys follow the audit's convention: `Name`, or `Name[n]` when the form has several boxes of
    that name; a global field is one key, its base name. Data values directly under form1 that
    no box reads (XFA-only fields) keep their own names, numbered when they repeat.
    """
    try:
        live = LiveForm.read(pdf_path)
    except (ET.ParseError, ValueError):
        return {}
    if live.data is None:
        return {}
    form_node, global_names, acro, bindings = live.data, live.global_names, live.acro, live.bindings
    values: dict[str, str] = {}
    for base, specs in acro.items():
        if base in global_names:
            node = _nth_child(form_node, base, 0, create=False)
            if node is not None:
                values[base] = (node.text or "").strip()
            continue
        for index in range(len(specs)):
            node = data_node(form_node, base, index, bindings=bindings, global_names=global_names)
            key = base if len(specs) == 1 else f"{base}[{index}]"
            values[key] = (node.text or "").strip() if node is not None else ""
    loose = [child for child in form_node if child.tag not in acro and len(child) == 0]
    counts: dict[str, int] = defaultdict(int)
    for child in loose:
        counts[child.tag] += 1
    seen: dict[str, int] = defaultdict(int)
    for child in loose:
        index = seen[child.tag]
        seen[child.tag] += 1
        key = child.tag if counts[child.tag] == 1 else f"{child.tag}[{index}]"
        values[key] = (child.text or "").strip()
    return values


def extract_visible(pdf_path: Path, field_names: list[str]) -> dict[str, object]:
    grouped = visible_values(pdf_path)
    result: dict[str, object] = {}
    for name in field_names:
        base, index = field_base_and_index(name)
        values = grouped.get(base)
        if values is None:
            result[name] = None
        elif has_explicit_index(name):
            result[name] = values[index] if index < len(values) else None
        else:
            result[name] = values[0] if len(values) == 1 else values
    return result


def verify_output(output_pdf: Path, fields: dict[str, object], *, check_visible: bool) -> dict:
    expected: dict[str, str] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            base, _ = field_base_and_index(key)
            for offset, item in enumerate(value):
                expected[f"{base}[{offset}]"] = "" if item is None else str(item)
        else:
            expected[key] = str(value)

    live = LiveForm.read(output_pdf)
    stored = extract_values(output_pdf, list(expected), per_widget=False, live=live)
    xfa_mismatches = {
        key: {"expected": expected[key], "stored": stored.get(key, "")}
        for key in expected
        if stored.get(key, "") != expected[key]
    }
    # What Adobe shows: a value stored where the template does not bind it, or in a box the
    # template leaves unbound, passes the check above but shows blank in Adobe.
    shown = adobe_view(output_pdf, [key for key in expected if expected[key].strip()], live=live)
    for key, value in shown.items():
        if key not in xfa_mismatches and value != expected[key]:
            xfa_mismatches[key] = {
                "expected": expected[key],
                "adobe_shows": value if value is not None else "(nothing: the template leaves this box unbound)",
            }

    visible_mismatches: dict[str, object] = {}
    if check_visible:
        acro, global_names = live.acro, live.global_names
        grouped = visible_values(output_pdf, reader=live.reader)
        for key, value in expected.items():
            base, index = field_base_and_index(key)
            fields_for_base = acro.get(base)
            if not fields_for_base:
                continue
            shown = grouped.get(base, [])
            want = value.strip()
            shown_stripped = [item.strip() for item in shown]
            if fields_for_base[0].field_type == "/Btn":
                if base in global_names or not has_explicit_index(key):
                    ok = (want in shown_stripped) if want else not any(shown_stripped)
                else:
                    ok = index < len(shown) and shown_stripped[index] == want
            elif base in global_names:
                ok = all(item == want for item in shown_stripped)
            else:
                ok = index < len(shown) and shown_stripped[index] == want
            if not ok:
                visible_mismatches[key] = {"expected": value, "visible": shown}
    return {"xfa": xfa_mismatches, "visible": visible_mismatches}


# --------------------------------------------------------------------------- commands


def field_dump(pdf_path: Path) -> dict[str, object]:
    """Every visible widget and XFA node name of a form, as `dump-fields --save` writes it.

    No stored values are included, so a dump of a filled form holds no client facts.
    """
    reader = PdfReader(str(pdf_path))
    global_names = global_bound_names(reader)
    acro = acro_fields_by_base(reader)
    bindings = FormBindings.from_reader(reader, acro)
    widgets: list[dict[str, object]] = []
    for base, specs in acro.items():
        for position, spec in enumerate(specs):
            slot = bindings.slot(base, position)
            if base in global_names:
                data = f"form1/{base} (global)"
            else:
                data = slot.label() if slot is not None else f"form1/{base}[{position}] (not in the template)"
            widgets.append(
                {
                    "name": base if len(specs) == 1 else f"{base}[{position}]",
                    "base": base,
                    "type": spec.field_type.lstrip("/"),
                    "states" if spec.field_type != "/Ch" else "options": list(spec.on_states),
                    "maxlen": spec.max_len,
                    "global": base in global_names,
                    "pages": spec.pages,
                    "tooltip": spec.tooltip,
                    "data": data,  # the XFA data node Adobe shows in this box
                }
            )
    datasets = xfa_packet(reader, "datasets")
    nodes = dataset_value_names(dataset_form(ET.fromstring(datasets))) if datasets else []
    return {
        "pdf": str(pdf_path.resolve()),
        "pdf_sha256": file_sha256(pdf_path),
        "dumped_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "fields": widgets,
        "xfa_nodes": nodes,
    }


def save_field_dump(pdf_path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(field_dump(pdf_path), indent=2), encoding="utf-8")
    return destination


DUMP_LINE_LIMIT = 40
TOOLTIP_LIMIT = 100


def list_fields(
    pdf_path: Path,
    prefix: str | None,
    acro: bool,
    save: Path | None = None,
    no_save: bool = False,
    full: bool = False,
) -> int:
    """Print the form's fields, at most DUMP_LINE_LIMIT lines unless full, and save the
    whole list as JSON (the matter's output/working/forms/fields/<FORM>.json by default)."""
    lines: list[str] = []
    if acro:
        reader = PdfReader(str(pdf_path))
        global_names = global_bound_names(reader)
        for base, specs in acro_fields_by_base(reader).items():
            if prefix and not base.startswith(prefix):
                continue
            for position, spec in enumerate(specs):
                name = base if len(specs) == 1 else f"{base}[{position}]"
                label = "options" if spec.field_type == "/Ch" else "states"
                tooltip = " ".join(spec.tooltip.split())
                if not full and len(tooltip) > TOOLTIP_LIMIT:
                    # The item's own words come last; the part heading in front repeats.
                    tooltip = "..." + tooltip[-(TOOLTIP_LIMIT - 3):]
                parts = [
                    name,
                    spec.field_type.lstrip("/"),
                    f"{label}=" + json.dumps(list(spec.on_states)) if spec.on_states else "",
                    f"maxlen={spec.max_len}" if spec.max_len else "",
                    "global" if base in global_names else "",
                    "p" + ",".join(str(page) for page in spec.pages) if spec.pages else "",
                    tooltip,
                ]
                lines.append("\t".join(parts))
    else:
        form_node = dataset_form(dataset_root(pdf_path))
        for child in form_node:
            if prefix and not child.tag.startswith(prefix):
                continue
            lines.append(child.tag)

    shown = lines if full else lines[:DUMP_LINE_LIMIT]
    for line in shown:
        print(line)

    destination = None if no_save else (save or default_field_dump_path(pdf_path))
    if destination is not None:
        save_field_dump(pdf_path, destination)
    if len(shown) < len(lines):
        where = f"read {destination}" if destination else "pass --save PATH to keep the full list"
        print(
            f"... {len(lines) - len(shown)} more of {len(lines)} lines not shown: narrow with --prefix, "
            f"{where}, or pass --full.",
            file=sys.stderr,
        )
    if destination is not None:
        print(f"fields saved: {destination}", file=sys.stderr)
    elif not no_save:
        print(
            "note: field list not saved. Blanks in a matter's output/working/forms/blank/ are "
            "saved to output/working/forms/fields/ automatically; pass --save PATH otherwise.",
            file=sys.stderr,
        )
    return 0


EXTRACT_LINE_LIMIT = 80


def widget_names(pdf_path: Path, prefix: str) -> list[str]:
    """Every box name on the form that starts with prefix, as dump-fields --acro writes it."""
    reader = PdfReader(str(pdf_path))
    names: list[str] = []
    for base, specs in acro_fields_by_base(reader).items():
        if base.startswith(prefix):
            names.extend(base if len(specs) == 1 else f"{base}[{n}]" for n in range(len(specs)))
    return names


def _shown(value: object) -> str:
    if value is None:
        return "(no such box)"
    if isinstance(value, list):
        return json.dumps(value)
    return repr(str(value)) if str(value) != str(value).strip() else str(value)


def extract_command(args: argparse.Namespace) -> int:
    names = list(args.field_names or [])
    if args.prefix:
        names.extend(name for name in widget_names(args.pdf, args.prefix) if name not in names)
    if not names:
        raise SystemExit("Give field names, or --prefix to read every box whose name starts with it.")
    if args.both:
        stored = extract_values(args.pdf, names)
        visible = extract_visible(args.pdf, names)
        result: dict[str, object] = {name: {"stored": stored[name], "visible": visible[name]} for name in names}
    elif args.visible:
        result = extract_visible(args.pdf, names)
    else:
        result = extract_values(args.pdf, names)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    lines: list[str] = []
    differ = 0
    for name in names:
        if args.both:
            stored_value, visible_value = result[name]["stored"], result[name]["visible"]
            same = visible_value is not None and str(stored_value).strip() == str(visible_value).strip()
            if same:
                lines.append(f"{name}\t{_shown(stored_value)}")
            else:
                differ += 1
                lines.append(f"{name}\tstored={_shown(stored_value)}\tvisible={_shown(visible_value)}\tDIFFERS")
        else:
            lines.append(f"{name}\t{_shown(result[name])}")
    shown = lines if args.full else lines[:EXTRACT_LINE_LIMIT]
    for line in shown:
        print(line)
    if len(shown) < len(lines):
        print(f"... {len(lines) - len(shown)} more names: narrow the list, or pass --full or --json.", file=sys.stderr)
    if args.both:
        print(f"{len(names)} names, {differ} differ between the stored and visible layers", file=sys.stderr)
    return 0


def fill_pdf(
    source_pdf: Path,
    output_pdf: Path,
    mapping_json: Path,
    verify: bool,
    *,
    full: bool = False,
    report: Path | None = None,
) -> int:
    fields = json.loads(mapping_json.read_text(encoding="utf-8"))
    if not isinstance(fields, dict):
        raise SystemExit("Mapping JSON must be an object of field names to values.")

    result = write_filled_pdf(source_pdf, output_pdf, fields)
    print(output_pdf)
    messages = fill_messages(result, full=full)
    for line in messages:
        print(line, file=sys.stderr)

    code = 0
    mismatches: dict = {}
    if verify:
        mismatches = verify_output(output_pdf, result.fields, check_visible=True)
        failed = sum(len(mismatches[layer]) for layer in ("xfa", "visible"))
        if failed:
            print(f"verify FAILED: {failed} value(s) differ from the mapping", file=sys.stderr)
            if full:
                print(json.dumps(mismatches, indent=2), file=sys.stderr)
            else:
                for line in verify_lines(mismatches):
                    print(line, file=sys.stderr)
            code = 1
        else:
            print(
                f"verify: stored XFA values and visible AcroForm values match the mapping ({len(result.fields)} values)",
                file=sys.stderr,
            )
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "output": str(output_pdf),
                    "notes": fill_messages(result, full=True),
                    "verify": mismatches if verify else None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and fill USCIS XFA PDF datasets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dump_parser = subparsers.add_parser("dump-fields", help="List XFA dataset field names.")
    dump_parser.add_argument("pdf", type=Path)
    dump_parser.add_argument("--prefix")
    dump_parser.add_argument(
        "--acro",
        action="store_true",
        help="List visible AcroForm widgets with type, on-states, max length, page and tooltip.",
    )
    save_group = dump_parser.add_mutually_exclusive_group()
    save_group.add_argument(
        "--save",
        type=Path,
        help="Write the full field list as JSON here. Default for a blank in "
        "<matter>/output/working/forms/blank/: <matter>/output/working/forms/fields/<FORM>.json.",
    )
    save_group.add_argument("--no-save", action="store_true", help="Print only; write no JSON.")
    dump_parser.add_argument(
        "--full", action="store_true", help=f"Print every line (default: at most {DUMP_LINE_LIMIT}) and whole tooltips."
    )

    fill_parser = subparsers.add_parser("fill", help="Fill an XFA PDF from a JSON mapping.")
    fill_parser.add_argument("source_pdf", type=Path)
    fill_parser.add_argument("output_pdf", type=Path)
    fill_parser.add_argument("mapping_json", type=Path)
    fill_parser.add_argument("--verify", action="store_true")
    fill_parser.add_argument("--report", type=Path, help="Write every note and verify mismatch here as JSON.")
    fill_parser.add_argument("--full", action="store_true", help="Print every note and mismatch in full.")

    extract_parser = subparsers.add_parser(
        "extract-values", help="Extract specific field values from an XFA PDF."
    )
    extract_parser.add_argument("pdf", type=Path)
    extract_parser.add_argument("field_names", nargs="*")
    extract_parser.add_argument("--prefix", help="Also read every box whose name starts with this.")
    layer = extract_parser.add_mutually_exclusive_group()
    layer.add_argument("--visible", action="store_true", help="Read the AcroForm (visible) layer instead.")
    layer.add_argument(
        "--both", action="store_true", help="Read both layers and mark the names whose values differ."
    )
    extract_parser.add_argument("--json", action="store_true", help="Print JSON instead of name<TAB>value lines.")
    extract_parser.add_argument(
        "--full", action="store_true", help=f"Print every name (default: at most {EXTRACT_LINE_LIMIT})."
    )

    render_parser = subparsers.add_parser(
        "render-filing-copy",
        help="Render a static filing copy from a prepared XFA source PDF (needs Ghostscript).",
    )
    render_parser.add_argument("source_pdf", type=Path)
    render_parser.add_argument("output_pdf", type=Path)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(parser, args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.command == "dump-fields":
        return list_fields(
            args.pdf, args.prefix, args.acro, args.save, args.no_save, args.full
        )
    if args.command == "fill":
        return fill_pdf(
            args.source_pdf,
            args.output_pdf,
            args.mapping_json,
            args.verify,
            full=args.full,
            report=args.report,
        )
    if args.command == "extract-values":
        return extract_command(args)
    if args.command == "render-filing-copy":
        render_filing_copy(args.source_pdf, args.output_pdf)
        print(args.output_pdf)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
