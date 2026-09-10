"""Constantes do recorte (célula, pré mínimo, cortes de ajuste e ROI)."""

from pathlib import Path

CASE_ROOT = Path(__file__).resolve().parents[2]
DATA_XLSX = CASE_ROOT / "data" / "Dados_Case_Especialista_II.xlsx"
RAW_DIR = CASE_ROOT / "data" / "raw"
PROCESSED_DIR = CASE_ROOT / "data" / "processed"
OUTPUTS_DIR = CASE_ROOT / "outputs"
TABLES_DIR = OUTPUTS_DIR / "tables"

# Vendas têm 17 ciclos/ano (existe 202413–202417). O cadastro só usa 01–12.
CYCLES_PER_YEAR = 17
CYCLE_ORIGIN_YEAR = 2024

# Controle sintético: mínimo de história no pré e teto de RMSPE / média no pré.
MIN_PRE_CYCLES = 4
PRE_FIT_MAX_REL = 0.30
EVENT_PRE = 8
EVENT_POST = 12

# tb_skus_similares não entra no ATT; o corte só vale na auditoria da lista.
SIMILAR_SCORE_MIN = 0.70

ROI_CORTE_MIDIA = 0.0
MIN_CYCLES_FOR_SELO = 6
# Teto do ROI de lançamento = 1 ano neste calendário (meta é GMV ano 1).
# A janela efetiva é min(isso, vida do incumbente, fim da amostra).
ROI_MAX_CYCLES = CYCLES_PER_YEAR

# Célula = marca × subcategoria × faixa_preco. categoria (Cabelos, Perfumaria)
# é larga demais; P1 e P6 na mesma subcategoria também não são o mesmo mercado.
CELL_KEYS = ("marca_std", "subcategoria", "faixa_preco")
