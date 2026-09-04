"""Ciclo comercial como texto do arquivo.

`cod_ciclo` na aba de vendas é texto. Aparece de dois jeitos: `202401` e
`2024/01`. São o mesmo ciclo. Há sequências 01–17 em 2024 e 2025.

Um `pd.to_numeric` sem tirar a barra transforma `2024/01` em nulo — isso foi
erro de limpeza, não buraco na planilha.
"""

from __future__ import annotations

import pandas as pd

from .config import CYCLE_INDEX_ORIGIN_YEAR, CYCLES_PER_YEAR


def parse_ciclo(value: object) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace("/", "")
    if not text or text.lower() in {"cod_ciclo", "nan", "none"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def ciclo_to_index(ciclo: object) -> int | None:
    parsed = parse_ciclo(ciclo)
    if parsed is None:
        return None
    year, seq = divmod(parsed, 100)
    if seq < 1:
        return None
    return (year - CYCLE_INDEX_ORIGIN_YEAR) * CYCLES_PER_YEAR + (seq - 1)


def index_to_ciclo(index: int) -> int:
    year = CYCLE_INDEX_ORIGIN_YEAR + index // CYCLES_PER_YEAR
    seq = index % CYCLES_PER_YEAR + 1
    return year * 100 + seq


def add_cycle_index(frame: pd.DataFrame, col: str, out_col: str) -> pd.DataFrame:
    out = frame.copy()
    out[out_col] = out[col].map(ciclo_to_index)
    return out
