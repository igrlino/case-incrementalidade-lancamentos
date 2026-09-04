"""Parâmetros explícitos. Nada aqui é dado inventado — só regras de recorte."""

from pathlib import Path

CASE_ROOT = Path(__file__).resolve().parents[2]


def _xlsx_path() -> Path:
    here = CASE_ROOT / "data" / "Dados_Case_Especialista_II.xlsx"
    sibling = CASE_ROOT.parent / "Dados_Case_Especialista_II.xlsx"
    if here.exists():
        return here
    return sibling


DATA_XLSX = _xlsx_path()
RAW_DIR = CASE_ROOT / "data" / "raw"
PROCESSED_DIR = CASE_ROOT / "data" / "processed"
OUTPUTS_DIR = CASE_ROOT / "outputs"
TABLES_DIR = OUTPUTS_DIR / "tables"
FIGURES_DIR = OUTPUTS_DIR / "figures"

# Dicionário declara vendas em [202401, 202606]. O painel observado vai além.
DICT_CICLO_MIN = 202401
DICT_CICLO_MAX = 202606

# O painel de vendas tem 17 "meses" por ano (202413–202417, 202513–202517).
# O cadastro de produto só usa 01–12. Tratamos vendas como ciclo comercial
# ordenado, não como calendário gregoriano. Ver docs/01_eda.md.
CYCLES_PER_YEAR = 17
CYCLE_INDEX_ORIGIN_YEAR = 2024

# Pré-período mínimo para controle sintético (ciclos comerciais).
MIN_PRE_CYCLES = 4
# RMSPE pré / média pré acima disso = ajuste rejeitado (níveis incompatíveis).
PRE_FIT_MAX_REL = 0.35
EVENT_PRE = 8
EVENT_POST = 12

# Similaridade fornecida só entra como robustez, nunca como definição primária.
SIMILAR_SCORE_MIN = 0.70

# Hurdle de ROI incremental (parcial, só mídia observada) para Gate.
ROI_HURDLE_MIDIA = 0.0
MIN_CYCLES_FOR_GATE = 6
