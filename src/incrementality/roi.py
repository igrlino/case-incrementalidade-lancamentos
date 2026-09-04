"""ROI incremental da inovação.

Equação oficial proposta usa só variáveis observadas no case + parâmetros
explícitos para custos NÃO presentes na base. Não imputamos P&D, estoque
ou mídia de sustentação.

Identidade:
    MB_inc = MB_direto_lancamento + ΔMB_incumbentes_nicho

    Custo_observado = investimento_mkt_rs

    Custo_full = investimento_mkt_rs + C_pd + C_estoque + C_sustentacao
                 (C_* entram como parâmetros, default 0 = "não informado")

    ROI_parcial = (MB_inc - investimento_mkt_rs) / investimento_mkt_rs
    ROI_full    = (MB_inc - Custo_full) / Custo_full

Gate (só com janela mínima e ATT estimável):
    VALUE_CREATOR  : MB_inc > 0 e ROI_parcial > hurdle
    MIX_DESTROYER  : GMV_inc > 0 e MB_inc <= 0
    CANNIBAL       : GMV_inc <= 0
    INCONCLUSIVO   : sem pré-período, janela curta ou ATT não estimável
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MIN_CYCLES_FOR_GATE, ROI_HURDLE_MIDIA


def classify_gate(row: pd.Series) -> str:
    if row["ciclos_expostos"] < MIN_CYCLES_FOR_GATE:
        return "INCONCLUSIVO_JANELA"
    if pd.isna(row.get("mb_incremental")):
        return "INCONCLUSIVO_IDENTIFICACAO"
    gmv_inc = row.get("gmv_incremental")
    mb_inc = row["mb_incremental"]
    roi = row.get("roi_parcial_midia")
    if pd.notna(gmv_inc) and gmv_inc <= 0:
        return "CANNIBAL"
    if mb_inc <= 0:
        return "MIX_DESTROYER"
    if pd.notna(roi) and roi > ROI_HURDLE_MIDIA:
        return "VALUE_CREATOR"
    return "ABAIXO_HURDLE"


def build_roi(
    projects_gmv: pd.DataFrame,
    projects_mb: pd.DataFrame,
    custo_pd: float = 0.0,
    custo_estoque: float = 0.0,
    custo_sustentacao: float = 0.0,
) -> pd.DataFrame:
    g = projects_gmv.copy()
    m = projects_mb[["id_projeto", "spillover_alocado", "incremental_estimado"]].rename(
        columns={
            "spillover_alocado": "mb_spillover_alocado",
            "incremental_estimado": "mb_incremental",
        }
    )
    out = g.merge(m, on="id_projeto", how="left")
    out = out.rename(
        columns={
            "spillover_alocado": "gmv_spillover_alocado",
            "incremental_estimado": "gmv_incremental",
        }
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
        (out["mb_incremental"] - out["custo_full_parametrizado"])
        / out["custo_full_parametrizado"],
        np.nan,
    )
    out["gate"] = out.apply(classify_gate, axis=1)
    out["alerta_janela_curta"] = out["ciclos_expostos"] < 12
    return out
