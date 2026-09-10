"""Leitura da planilha e limpeza.

O Excel mistura texto e número (ciclo `2024/01`, preço `31,34`). Sem tratar
isso, o pandas apaga valor. Desconto em branco vira zero porque, nessas
linhas, praticado = tabela — conferido, não convenção.
"""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .config import CASE_ROOT, CYCLE_ORIGIN_YEAR, CYCLES_PER_YEAR, DATA_XLSX, RAW_DIR

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_CELL = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"
_T = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"


# --- Excel (stdlib; evita dependência de openpyxl) -------------------------

def _col_row(ref: str) -> tuple[int, int]:
    col, i = 0, 0
    while i < len(ref) and ref[i].isalpha():
        col = col * 26 + (ord(ref[i].upper()) - 64)
        i += 1
    return col - 1, int(ref[i:]) - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(_T)) for si in root.findall("m:si", _NS)]


def _parse_sheet(zf: zipfile.ZipFile, sheet_path: str, strings: list[str]) -> pd.DataFrame:
    rows: dict[int, dict[int, str]] = defaultdict(dict)
    max_c = max_r = -1
    with zf.open(sheet_path) as handle:
        for _, elem in ET.iterparse(handle, events=("end",)):
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
            max_c, max_r = max(max_c, col), max(max_r, row)
            elem.clear()
    header = [rows[0].get(c) for c in range(max_c + 1)]
    data = [[rows[r].get(c) for c in range(max_c + 1)] for r in range(1, max_r + 1)]
    return pd.DataFrame(data, columns=header)


def _xlsx_para_parquet(xlsx: Path | None = None, out_dir: Path | None = None) -> None:
    xlsx = xlsx or DATA_XLSX
    out_dir = out_dir or RAW_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
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
            _parse_sheet(zf, target, strings).to_parquet(out_dir / f"{name}.parquet", index=False)


def load_raw(raw_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    raw_dir = raw_dir or RAW_DIR
    names = ["tb_produtos_atributos", "tb_projetos_lancamento", "tb_skus_similares", "tb_vendas"]
    if any(not (raw_dir / f"{n}.parquet").exists() for n in names):
        _xlsx_para_parquet()
    return {n: pd.read_parquet(raw_dir / f"{n}.parquet") for n in names}


# --- Ciclo comercial -------------------------------------------------------

def parse_ciclo(value: object) -> int | None:
    """`202401` e `2024/01` → o mesmo inteiro. A barra, se não sair, vira NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace("/", "")
    if not text or text.lower() in {"cod_ciclo", "nan", "none"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def ciclo_idx(ciclo: object) -> int | None:
    parsed = parse_ciclo(ciclo)
    if parsed is None:
        return None
    year, seq = divmod(parsed, 100)
    if seq < 1:
        return None
    return (year - CYCLE_ORIGIN_YEAR) * CYCLES_PER_YEAR + (seq - 1)


# --- Limpeza ---------------------------------------------------------------

def _decimal(value: object) -> float | None:
    """Aceita vírgula decimal (`31,34`). Não trata milhar."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _marca(value: object) -> str:
    text = str(value).strip().lower()
    if text in {"o boticário", "o boticario"}:
        return "O Boticário"
    if text == "eudora":
        return "Eudora"
    return str(value).strip()


def carregar(raw_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Produtos, projetos, similares e vendas prontos para o modelo."""
    raw = load_raw(raw_dir)

    projetos = raw["tb_projetos_lancamento"].copy()
    projetos["investimento_mkt_rs"] = pd.to_numeric(projetos["investimento_mkt_rs"], errors="coerce")
    projetos["expectativa_gmv_ano1"] = pd.to_numeric(projetos["expectativa_gmv_ano1"], errors="coerce")
    launch = set(projetos["cod_sku_lancamento"])

    produtos = raw["tb_produtos_atributos"].copy()
    for col in ["preco_regular", "margem_bruta_pct"]:
        produtos[col] = produtos[col].map(_decimal)
    produtos["cod_ciclo_phase_in"] = produtos["cod_ciclo_phase_in"].map(parse_ciclo)
    produtos["cod_ciclo_phase_out"] = produtos["cod_ciclo_phase_out"].map(parse_ciclo)
    produtos["marca_std"] = produtos["marca"].map(_marca)
    produtos["is_project"] = produtos["cod_sku"].isin(launch)
    produtos["is_incumbent"] = (~produtos["is_project"]) & (produtos["cod_ciclo_phase_in"] < 202401)
    produtos["is_other_innovation"] = (~produtos["is_project"]) & (produtos["cod_ciclo_phase_in"] >= 202401)
    produtos["phase_in_idx"] = produtos["cod_ciclo_phase_in"].map(ciclo_idx)
    produtos["phase_out_idx"] = produtos["cod_ciclo_phase_out"].map(ciclo_idx)

    similares = raw["tb_skus_similares"].copy()
    similares["score_similaridade_par"] = pd.to_numeric(similares["score_similaridade_par"], errors="coerce")

    vendas = raw["tb_vendas"].copy()
    vendas["cod_ciclo_bruto"] = vendas["cod_ciclo"].astype(str).str.strip()
    vendas["cod_ciclo"] = vendas["cod_ciclo"].map(parse_ciclo)
    for col in ["qt_venda", "vlr_venda_tabela", "vlr_venda_desconto", "vlr_venda_praticado", "margem_bruta"]:
        vendas[col] = pd.to_numeric(vendas[col], errors="coerce")
    vendas["canal_std"] = vendas["canal_venda"].astype(str).str.strip().str.upper()
    vendas["vlr_venda_desconto"] = vendas["vlr_venda_desconto"].fillna(0.0)
    vendas["flag_ciclo_nulo"] = vendas["cod_ciclo"].isna()
    vendas["ciclo_idx"] = vendas["cod_ciclo"].map(ciclo_idx)

    return produtos, projetos, similares, vendas


def auditar(produtos: pd.DataFrame, projetos: pd.DataFrame, similares: pd.DataFrame, vendas: pd.DataFrame) -> dict[str, Any]:
    """Identidades que a limpeza precisa respeitar (tabela, desconto, margem)."""
    merged = vendas.merge(
        produtos[["cod_sku", "preco_regular", "margem_bruta_pct"]],
        on="cod_sku",
        how="left",
    )
    priced = merged["preco_regular"].notna()
    d_tab = (merged["vlr_venda_tabela"] - merged["preco_regular"] * merged["qt_venda"]).abs()
    d_prat = (merged["vlr_venda_praticado"] - (merged["vlr_venda_tabela"] - merged["vlr_venda_desconto"])).abs()
    d_mb = (merged["margem_bruta"] - merged["vlr_venda_praticado"] * merged["margem_bruta_pct"]).abs()
    v_ok = vendas.loc[~vendas["flag_ciclo_nulo"]]
    return {
        "n_produtos": int(len(produtos)),
        "n_projetos": int(len(projetos)),
        "n_incumbentes": int(produtos["is_incumbent"].sum()),
        "n_outra_inovacao": int(produtos["is_other_innovation"].sum()),
        "n_ciclos": int(v_ok["cod_ciclo"].nunique()),
        "ciclo_min": int(v_ok["cod_ciclo"].min()),
        "ciclo_max": int(v_ok["cod_ciclo"].max()),
        "ciclo_nulo": int(vendas["flag_ciclo_nulo"].sum()),
        "erro_tabela_gt_0_05": int(((d_tab > 0.05) & priced).sum()),
        "erro_praticado_gt_0_05": int((d_prat > 0.05).sum()),
        "erro_margem_gt_0_02": int((d_mb > 0.02).sum()),
        "projetos_sem_lista_similar": int((~projetos["cod_sku_lancamento"].isin(similares["cod_sku_principal"])).sum()),
    }
