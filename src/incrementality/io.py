"""Leitura das tabelas. Excel via XML (stdlib) — sem openpyxl."""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .config import RAW_DIR, DATA_XLSX

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_CELL = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"
_T = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"


def _col_row(ref: str) -> tuple[int, int]:
    col = 0
    i = 0
    while i < len(ref) and ref[i].isalpha():
        col = col * 26 + (ord(ref[i].upper()) - 64)
        i += 1
    return col - 1, int(ref[i:]) - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for si in root.findall("m:si", _NS):
        strings.append("".join(t.text or "" for t in si.iter(_T)))
    return strings


def _parse_sheet(zf: zipfile.ZipFile, sheet_path: str, strings: list[str]) -> pd.DataFrame:
    rows: dict[int, dict[int, str]] = defaultdict(dict)
    max_c = -1
    max_r = -1
    with zf.open(sheet_path) as handle:
        for _event, elem in ET.iterparse(handle, events=("end",)):
            if elem.tag != _CELL:
                continue
            ref = elem.get("r")
            if not ref:
                elem.clear()
                continue
            col, row = _col_row(ref)
            cell_type = elem.get("t")
            v = elem.find("m:v", _NS)
            inline = elem.find("m:is", _NS)
            if cell_type == "s" and v is not None and v.text is not None:
                val: str | None = strings[int(v.text)]
            elif cell_type == "inlineStr" and inline is not None:
                val = "".join(t.text or "" for t in inline.iter(_T))
            elif v is not None and v.text is not None:
                val = v.text
            else:
                elem.clear()
                continue
            rows[row][col] = val
            max_c = max(max_c, col)
            max_r = max(max_r, row)
            elem.clear()
    header = [rows[0].get(c) for c in range(max_c + 1)]
    data = [[rows[r].get(c) for c in range(max_c + 1)] for r in range(1, max_r + 1)]
    return pd.DataFrame(data, columns=header)


def excel_to_parquet(xlsx: Path | None = None, out_dir: Path | None = None) -> dict[str, Path]:
    xlsx = xlsx or DATA_XLSX
    out_dir = out_dir or RAW_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    with zipfile.ZipFile(xlsx) as zf:
        strings = _shared_strings(zf)
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {rel.get("Id"): rel.get("Target") for rel in rels}
        for sheet in wb.findall("m:sheets/m:sheet", _NS):
            name = sheet.get("name")
            if name == "Dicionário de campos":
                continue
            rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rid_to_target[rid]
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            frame = _parse_sheet(zf, target, strings)
            path = out_dir / f"{name}.parquet"
            frame.to_parquet(path, index=False)
            saved[name] = path
    return saved


def load_raw(raw_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    raw_dir = raw_dir or RAW_DIR
    names = [
        "tb_produtos_atributos",
        "tb_projetos_lancamento",
        "tb_skus_similares",
        "tb_vendas",
    ]
    missing = [n for n in names if not (raw_dir / f"{n}.parquet").exists()]
    if missing:
        excel_to_parquet()
    return {n: pd.read_parquet(raw_dir / f"{n}.parquet") for n in names}
