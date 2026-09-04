"""Limpeza com regras auditáveis. Não imputa grandeza de negócio ausente."""

from __future__ import annotations

import pandas as pd

from .cycles import add_cycle_index, parse_ciclo


def _parse_decimal(value: object) -> float | None:
    """Número com ponto OU vírgula decimal (31,34 → 31.34). Não trata milhar."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", ""}:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _norm_marca(value: object) -> str:
    text = str(value).strip().lower()
    if text in {"o boticário", "o boticario"}:
        return "O Boticário"
    if text == "eudora":
        return "Eudora"
    return str(value).strip()


def clean_produtos(prod: pd.DataFrame, launch_skus: set[str]) -> pd.DataFrame:
    out = prod.copy()
    numeric_money = ["preco_regular", "margem_bruta_pct"]
    for col in numeric_money:
        out[col] = out[col].map(_parse_decimal)
    out["cod_ciclo_phase_in"] = out["cod_ciclo_phase_in"].map(parse_ciclo)
    out["cod_ciclo_phase_out"] = out["cod_ciclo_phase_out"].map(parse_ciclo)
    out["marca_std"] = out["marca"].map(_norm_marca)
    out["is_project"] = out["cod_sku"].isin(launch_skus)
    # Incumbente = já existia antes do painel e não é projeto da tabela de inovação.
    out["is_incumbent"] = (~out["is_project"]) & (out["cod_ciclo_phase_in"] < 202401)
    out["is_other_innovation"] = (~out["is_project"]) & (out["cod_ciclo_phase_in"] >= 202401)
    out = add_cycle_index(out, "cod_ciclo_phase_in", "phase_in_idx")
    out = add_cycle_index(out, "cod_ciclo_phase_out", "phase_out_idx")
    return out


def clean_projetos(proj: pd.DataFrame) -> pd.DataFrame:
    out = proj.copy()
    out["investimento_mkt_rs"] = pd.to_numeric(out["investimento_mkt_rs"], errors="coerce")
    out["expectativa_gmv_ano1"] = pd.to_numeric(out["expectativa_gmv_ano1"], errors="coerce")
    return out


def clean_similares(sim: pd.DataFrame) -> pd.DataFrame:
    out = sim.copy()
    out["score_similaridade_par"] = pd.to_numeric(out["score_similaridade_par"], errors="coerce")
    return out


def clean_vendas(vnd: pd.DataFrame) -> pd.DataFrame:
    out = vnd.copy()
    out["cod_ciclo_bruto"] = out["cod_ciclo"].astype(str).str.strip()
    out["cod_ciclo"] = out["cod_ciclo"].map(parse_ciclo)
    for col in [
        "qt_venda",
        "vlr_venda_tabela",
        "vlr_venda_desconto",
        "vlr_venda_praticado",
        "margem_bruta",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["canal_std"] = out["canal_venda"].astype(str).str.strip().str.upper()
    out["vlr_venda_desconto"] = out["vlr_venda_desconto"].fillna(0.0)
    out["flag_ciclo_nulo"] = out["cod_ciclo"].isna()
    out["ciclo_mm"] = out["cod_ciclo"] % 100
    out["flag_ciclo_seq_13_a_17"] = out["ciclo_mm"] > 12
    out["flag_ciclo_alem_dicionario"] = out["cod_ciclo"] > 202606
    out = add_cycle_index(out, "cod_ciclo", "ciclo_idx")
    return out


def sku_active_mask(prod: pd.DataFrame, ciclo_idx: int) -> pd.Series:
    started = prod["phase_in_idx"].fillna(10**9) <= ciclo_idx
    not_ended = prod["phase_out_idx"].isna() | (prod["phase_out_idx"] >= ciclo_idx)
    return started & not_ended
