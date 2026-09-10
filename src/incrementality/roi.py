"""Retorno do lançamento.

    MB_inc = margem do novo + Δ margem da base antiga na célula
    ROI_parcial = (MB_inc − mídia) / mídia

P&D, estoque e mídia de sustentação não vêm na planilha. Entram como
parâmetro (default 0 = não informado). Sem chute de custo 'típico'.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CELL_KEYS, MIN_CYCLES_FOR_SELO, ROI_CORTE_MIDIA, ROI_MAX_CYCLES

PAINEL_COLS = [
    "id_projeto",
    "cod_sku_lancamento",
    "marca_std",
    "subcategoria",
    "faixa_preco",
    "n_projetos_celula",
    "att_status",
    "n_post_roi",
    "ciclos_expostos",
    "janela_roi_incompleta",
    "fit_rel_pre_gmv",
    "fit_rel_pre_mb",
    "placebo_pvalue_gmv",
    "placebo_pvalue_mb",
    "gmv",
    "mb",
    "gmv_spillover_alocado",
    "mb_spillover_alocado",
    "gmv_incremental",
    "mb_incremental",
    "investimento_mkt_rs",
    "payback_parcial_midia",
    "roi_parcial_midia",
    "alerta_pouco_tempo",
    "selo",
]

_SELO_STATUS = {
    "sem_incumbente": "Não dá para medir: sem produto antigo na faixa",
    "sem_pre_periodo_suficiente": "Não dá para medir: sem histórico antes do lançamento",
    "ajuste_pre_fraco": "Não dá para medir: o espelho não colou",
    "sem_doador": "Não dá para medir: sem tríade para comparar",
    "sem_escala_pre": "Não dá para medir: base antiga sem venda no pré",
    "incumbente_fora_antes_do_t0": "Não dá para medir: incumbente já tinha saído de linha",
    "fora_da_janela_da_celula": "Não dá para medir: SKU nasceu depois da janela da célula",
}


def _selo(row: pd.Series) -> str:
    if row["ciclos_expostos"] < MIN_CYCLES_FOR_SELO:
        return "Cedo demais: menos de 6 ciclos na prateleira"
    if pd.isna(row.get("mb_incremental")):
        return _SELO_STATUS.get(row.get("att_status"), "Não dá para medir: motivo não classificado")
    n_janela = row.get("n_post_roi")
    if pd.notna(n_janela) and int(n_janela) < ROI_MAX_CYCLES:
        return "Ano 1 incompleto"
    if pd.notna(row.get("gmv_incremental")) and row["gmv_incremental"] <= 0:
        return "Comeu a base"
    if row["mb_incremental"] <= 0:
        return "Piorou o mix"
    roi = row.get("roi_parcial_midia")
    if pd.notna(roi) and roi > ROI_CORTE_MIDIA:
        return "Paga a mídia"
    return "Não paga a mídia"


def build_roi(
    projects_gmv: pd.DataFrame,
    projects_mb: pd.DataFrame,
    custo_pd: float = 0.0,
    custo_estoque: float = 0.0,
    custo_sustentacao: float = 0.0,
) -> pd.DataFrame:
    g = projects_gmv.copy()
    m = projects_mb[["id_projeto", "spillover_alocado", "incremental_estimado"]].rename(
        columns={"spillover_alocado": "mb_spillover_alocado", "incremental_estimado": "mb_incremental"}
    )
    out = g.merge(m, on="id_projeto", how="left").rename(
        columns={"spillover_alocado": "gmv_spillover_alocado", "incremental_estimado": "gmv_incremental"}
    )
    out["c_pd"] = custo_pd
    out["c_estoque"] = custo_estoque
    out["c_sustentacao"] = custo_sustentacao
    out["custo_observado_midia"] = out["investimento_mkt_rs"]
    out["custo_full_parametrizado"] = (
        out["custo_observado_midia"] + out["c_pd"] + out["c_estoque"] + out["c_sustentacao"]
    )
    out["payback_parcial_midia"] = out["mb_incremental"] - out["custo_observado_midia"]
    out["roi_parcial_midia"] = np.where(
        out["custo_observado_midia"] > 0,
        out["payback_parcial_midia"] / out["custo_observado_midia"],
        np.nan,
    )
    out["roi_full"] = np.where(
        out["custo_full_parametrizado"] > 0,
        (out["mb_incremental"] - out["custo_full_parametrizado"]) / out["custo_full_parametrizado"],
        np.nan,
    )
    out["selo"] = out.apply(_selo, axis=1)
    n_janela = pd.to_numeric(out.get("n_post_roi"), errors="coerce")
    out["alerta_pouco_tempo"] = (out["ciclos_expostos"] < 12) | (
        n_janela.notna() & (n_janela < ROI_MAX_CYCLES)
    )
    return out


def _diag_celula(att: pd.DataFrame, metric: str, cell_keys: tuple[str, ...]) -> pd.DataFrame:
    cols = [
        *cell_keys,
        "fit_rel_pre",
        "placebo_pvalue_rmspe_ratio",
    ]
    present = [c for c in cols if c in att.columns]
    out = att.loc[att["metric"] == metric, present].drop_duplicates(list(cell_keys))
    return out.rename(
        columns={
            "fit_rel_pre": f"fit_rel_pre_{metric}",
            "placebo_pvalue_rmspe_ratio": f"placebo_pvalue_{metric}",
        }
    )


def build_painel_comite(
    roi: pd.DataFrame,
    att: pd.DataFrame,
    cell_keys: tuple[str, ...] = CELL_KEYS,
) -> pd.DataFrame:
    """Painel único por projeto: ROI + diagnóstico do espelho (GMV e MB) na célula."""
    out = roi.copy()
    if "n_projetos" in out.columns:
        out = out.rename(columns={"n_projetos": "n_projetos_celula"})
    for metric in ("gmv", "mb"):
        diag = _diag_celula(att, metric, cell_keys)
        out = out.merge(diag, on=list(cell_keys), how="left")
    ordered = [c for c in PAINEL_COLS if c in out.columns]
    return out[ordered]
