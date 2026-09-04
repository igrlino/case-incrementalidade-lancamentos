"""Pilha causal de incrementalidade.

Identificação (o que o case pede isolar):
    GMV/MB incremental = vendas do lançamento
                         + variação dos incumbentes do nicho vs contrafactual.

O lançamento não tem pré-período (é novo). O objeto contrafactual é a *base
regular do nicho* (marca × subcategoria), não o próprio SKU novo.

Por que não usar só tb_skus_similares:
    13/25 projetos não têm pares; os pares cruzam categoria; incluem SKU
    descontinuado antes do painel. Vira enviesado por construção.

Por que não TWFE ingênuo:
    20/25 projetos compartilham nicho com outro projeto (quebra SUTVA no SKU).
    Tratamento escalonado + TWFE clássico é viesado (Goodman-Bacon).

O que fazemos:
    1. Célula de concorrência = marca_std × subcategoria.
    2. Desfecho = GMV e MB dos incumbentes da célula (phase_in < 202401,
       fora da tabela de projetos). Outras inovações não-rotuladas saem do
       desfecho para não contaminar o residual.
    3. Tratamento da célula = primeiro ciclo com projeto ativo na célula.
    4. Doadores = células nunca tratadas (nenhum projeto na tabela).
    5. Controle sintético de Abadie no pré-período da célula.
    6. ATT da célula = média pós-tratamento (observado − sintético).
    7. Alocação da canibalização entre projetos do mesmo nicho é *contábil*
       (peso = GMV direto do projeto no pós), não causal isolada. Explicitamos.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import EVENT_POST, EVENT_PRE, MIN_PRE_CYCLES, PRE_FIT_MAX_REL, SIMILAR_SCORE_MIN


def _fit_weights(y1_pre: np.ndarray, y0_pre: np.ndarray) -> np.ndarray:
    t, j = y0_pre.shape
    if j == 0 or t == 0:
        raise ValueError("doador vazio")
    def loss(w: np.ndarray) -> float:
        return float(np.sum((y1_pre - y0_pre @ w) ** 2))
    cons = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = [(0.0, 1.0)] * j
    w0 = np.full(j, 1.0 / j)
    result = minimize(
        loss,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 800, "ftol": 1e-14},
    )
    weights = np.clip(result.x, 0.0, 1.0)
    total = weights.sum()
    return weights / total if total > 0 else w0


def _rmspe(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((a - b) ** 2)))


def _synth_index(
    y: np.ndarray,
    donor_mat: np.ndarray,
    pre_pos: list[int],
    donor_keys: list[tuple[str, str]],
) -> tuple[np.ndarray, np.ndarray, list[tuple[str, str]], float] | None:
    """Controle sintético na *trajetória* (índice do pré), reconstruído em nível.

    Nichos têm escalas muito diferentes. Ajustar pesos no GMV absoluto faz o
    sintético herdar o tamanho dos doadores e inventa canibalização. Indexar
    pela média pré compara só o formato da série — o que o negócio chama de
    'a base regular acompanhou ou descolou do resto do portfólio'.
    """
    y_scale = float(np.mean(y[pre_pos]))
    if abs(y_scale) < 1e-9:
        return None
    donor_scales = donor_mat[pre_pos, :].mean(axis=0)
    valid = np.abs(donor_scales) >= 1e-9
    if int(valid.sum()) == 0:
        return None
    y_idx = y / y_scale
    d_idx = donor_mat[:, valid] / donor_scales[valid]
    weights = _fit_weights(y_idx[pre_pos], d_idx[pre_pos, :])
    synth_level = (d_idx @ weights) * y_scale
    keys = [k for k, keep in zip(donor_keys, valid) if keep]
    return synth_level, weights, keys, y_scale


def build_incumbent_panel(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    value_col: str,
) -> pd.DataFrame:
    incumbents = produtos.loc[produtos["is_incumbent"], ["cod_sku", "marca_std", "subcategoria"]]
    panel = (
        vendas.loc[~vendas["flag_ciclo_nulo"] & vendas["cod_sku"].isin(incumbents["cod_sku"])]
        .merge(incumbents, on="cod_sku", how="left")
        .groupby(["marca_std", "subcategoria", "ciclo_idx", "cod_ciclo"], as_index=False)
        .agg(valor=(value_col, "sum"))
    )
    return panel


def cell_treatment_starts(produtos: pd.DataFrame, projetos: pd.DataFrame) -> pd.DataFrame:
    lanc = projetos.merge(
        produtos[["cod_sku", "marca_std", "subcategoria", "phase_in_idx", "cod_ciclo_phase_in"]],
        left_on="cod_sku_lancamento",
        right_on="cod_sku",
        how="left",
    )
    starts = (
        lanc.groupby(["marca_std", "subcategoria"], as_index=False)
        .agg(
            t0_idx=("phase_in_idx", "min"),
            t0_ciclo=("cod_ciclo_phase_in", "min"),
            n_projetos=("id_projeto", "nunique"),
            projetos=("id_projeto", lambda s: ",".join(sorted(s))),
            skus=("cod_sku_lancamento", lambda s: ",".join(sorted(s))),
        )
    )
    return starts


def never_treated_cells(produtos: pd.DataFrame) -> pd.DataFrame:
    cells = produtos.groupby(["marca_std", "subcategoria"], as_index=False).agg(
        n_project=("is_project", "sum"),
        n_incumbent=("is_incumbent", "sum"),
    )
    return cells.loc[(cells["n_project"] == 0) & (cells["n_incumbent"] > 0)].copy()


def _cell_series(panel: pd.DataFrame, marca: str, sub: str, index_grid: np.ndarray) -> np.ndarray:
    subp = panel[(panel["marca_std"] == marca) & (panel["subcategoria"] == sub)]
    mapped = subp.set_index("ciclo_idx")["valor"]
    return mapped.reindex(index_grid, fill_value=0.0).to_numpy(dtype=float)


def synthetic_control_cells(
    panel: pd.DataFrame,
    starts: pd.DataFrame,
    donors: pd.DataFrame,
    metric_name: str,
) -> pd.DataFrame:
    index_grid = np.array(sorted(panel["ciclo_idx"].dropna().unique()), dtype=int)
    donor_keys = list(zip(donors["marca_std"], donors["subcategoria"]))
    donor_mat = np.column_stack(
        [_cell_series(panel, m, s, index_grid) for m, s in donor_keys]
    )
    rows: list[dict[str, Any]] = []
    idx_pos = {int(k): i for i, k in enumerate(index_grid)}

    for _, cell in starts.iterrows():
        y = _cell_series(panel, cell["marca_std"], cell["subcategoria"], index_grid)
        t0 = cell["t0_idx"]
        if pd.isna(t0):
            continue
        t0 = int(t0)
        pre_keys = [k for k in index_grid if k < t0]
        post_keys = [k for k in index_grid if k >= t0]
        n_pre = len(pre_keys)
        n_inc = int(cell["n_incumbent"]) if "n_incumbent" in cell.index and pd.notna(cell["n_incumbent"]) else None
        if n_inc == 0:
            status = "sem_incumbente"
        elif n_pre < MIN_PRE_CYCLES:
            status = "sem_pre_periodo_suficiente"
        else:
            status = "ok"

        record: dict[str, Any] = {
            "metric": metric_name,
            "marca_std": cell["marca_std"],
            "subcategoria": cell["subcategoria"],
            "t0_idx": t0,
            "t0_ciclo": int(cell["t0_ciclo"]),
            "n_projetos_nicho": int(cell["n_projetos"]),
            "projetos": cell["projetos"],
            "n_pre": n_pre,
            "n_post": len(post_keys),
            "status": status,
        }
        if status != "ok":
            rows.append(record)
            continue

        pre_pos = [idx_pos[k] for k in pre_keys]
        post_pos = [idx_pos[k] for k in post_keys]
        fitted = _synth_index(y, donor_mat, pre_pos, donor_keys)
        if fitted is None:
            record["status"] = "sem_escala_pre"
            rows.append(record)
            continue
        synth, weights, used_keys, _scale = fitted
        gap = y - synth
        rmspe_pre = _rmspe(y[pre_pos], synth[pre_pos])
        y_pre = float(y[pre_pos].mean())
        fit_rel = rmspe_pre / abs(y_pre) if abs(y_pre) > 0 else float("inf")
        if fit_rel > PRE_FIT_MAX_REL:
            record["status"] = "ajuste_pre_fraco"
        record.update(
            {
                "rmspe_pre": rmspe_pre,
                "rmspe_post": _rmspe(y[post_pos], synth[post_pos]),
                "fit_rel_pre": float(fit_rel),
                "att_media_ciclo": float(gap[post_pos].mean()),
                "att_soma_pos": float(gap[post_pos].sum()),
                "y_pre_media": y_pre,
                "synth_pre_media": float(synth[pre_pos].mean()),
                "y_post_media": float(y[post_pos].mean()),
                "synth_post_media": float(synth[post_pos].mean()),
                "pesos": {
                    f"{m}|{s}": float(w)
                    for (m, s), w in zip(used_keys, weights)
                    if w >= 0.01
                },
            }
        )
        if record["status"] != "ok":
            rows.append(record)
            continue
        placebo_ratios: list[float] = []
        treated_ratio = record["rmspe_post"] / record["rmspe_pre"] if record["rmspe_pre"] > 0 else np.inf
        for j in range(donor_mat.shape[1]):
            y_p = donor_mat[:, j]
            y0_p = np.delete(donor_mat, j, axis=1)
            keys_p = [k for i, k in enumerate(donor_keys) if i != j]
            fitted_p = _synth_index(y_p, y0_p, pre_pos, keys_p)
            if fitted_p is None:
                continue
            synth_p, _, _, _ = fitted_p
            pre_r = _rmspe(y_p[pre_pos], synth_p[pre_pos])
            post_r = _rmspe(y_p[post_pos], synth_p[post_pos])
            if pre_r > 0:
                placebo_ratios.append(post_r / pre_r)
        record["placebo_pvalue_rmspe_ratio"] = (
            float(np.mean(np.array(placebo_ratios) >= treated_ratio))
            if placebo_ratios
            else None
        )
        record["n_placebos"] = len(placebo_ratios)
        record["rmspe_ratio"] = float(treated_ratio) if np.isfinite(treated_ratio) else None
        rows.append(record)
    return pd.DataFrame(rows)


def event_paths(
    panel: pd.DataFrame,
    starts: pd.DataFrame,
    donors: pd.DataFrame,
    metric_name: str,
) -> pd.DataFrame:
    """Caminhos observados vs sintéticos em tempo de evento, só células OK."""
    index_grid = np.array(sorted(panel["ciclo_idx"].dropna().unique()), dtype=int)
    donor_keys = list(zip(donors["marca_std"], donors["subcategoria"]))
    donor_mat = np.column_stack(
        [_cell_series(panel, m, s, index_grid) for m, s in donor_keys]
    )
    idx_pos = {int(k): i for i, k in enumerate(index_grid)}
    rows: list[dict[str, Any]] = []
    for _, cell in starts.iterrows():
        t0 = cell["t0_idx"]
        if pd.isna(t0):
            continue
        t0 = int(t0)
        n_inc = int(cell["n_incumbent"]) if "n_incumbent" in cell.index and pd.notna(cell["n_incumbent"]) else 1
        if n_inc == 0:
            continue
        pre_keys = [k for k in index_grid if k < t0]
        if len(pre_keys) < MIN_PRE_CYCLES:
            continue
        y = _cell_series(panel, cell["marca_std"], cell["subcategoria"], index_grid)
        pre_pos = [idx_pos[k] for k in pre_keys]
        fitted = _synth_index(y, donor_mat, pre_pos, donor_keys)
        if fitted is None:
            continue
        synth, _, _, _ = fitted
        rmspe_pre = _rmspe(y[pre_pos], synth[pre_pos])
        y_pre = abs(float(y[pre_pos].mean()))
        if y_pre == 0 or (rmspe_pre / y_pre) > PRE_FIT_MAX_REL:
            continue
        for k in index_grid:
            e = int(k - t0)
            if e < -EVENT_PRE or e > EVENT_POST:
                continue
            pos = idx_pos[int(k)]
            rows.append(
                {
                    "metric": metric_name,
                    "marca_std": cell["marca_std"],
                    "subcategoria": cell["subcategoria"],
                    "event_time": e,
                    "ciclo_idx": int(k),
                    "observado": float(y[pos]),
                    "sintetico": float(synth[pos]),
                    "gap": float(y[pos] - synth[pos]),
                }
            )
    return pd.DataFrame(rows)


def project_direct_metrics(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    projetos: pd.DataFrame,
) -> pd.DataFrame:
    lanc = projetos.merge(
        produtos[
            [
                "cod_sku",
                "marca_std",
                "categoria",
                "subcategoria",
                "faixa_preco",
                "preco_regular",
                "margem_bruta_pct",
                "cod_ciclo_phase_in",
                "cod_ciclo_phase_out",
                "phase_in_idx",
                "phase_out_idx",
            ]
        ],
        left_on="cod_sku_lancamento",
        right_on="cod_sku",
        how="left",
    )
    v = vendas.loc[~vendas["flag_ciclo_nulo"]]
    agg = (
        v.groupby("cod_sku")
        .agg(
            gmv=("vlr_venda_praticado", "sum"),
            mb=("margem_bruta", "sum"),
            qty=("qt_venda", "sum"),
            min_idx=("ciclo_idx", "min"),
            max_idx=("ciclo_idx", "max"),
            n_ciclos=("ciclo_idx", "nunique"),
        )
        .reset_index()
    )
    out = lanc.merge(agg, left_on="cod_sku_lancamento", right_on="cod_sku", how="left")
    panel_max = int(v["ciclo_idx"].max())
    out["ciclos_expostos"] = (out["max_idx"] - out["phase_in_idx"] + 1).clip(lower=0)
    out["window_completa_17"] = out["ciclos_expostos"] >= 17
    # Run-rate apenas como referência descritiva, nunca como contrafactual.
    out["gmv_runrate_17_descritivo"] = np.where(
        out["ciclos_expostos"] > 0,
        out["gmv"] * (17.0 / out["ciclos_expostos"]),
        np.nan,
    )
    out["atingimento_bruto_vs_exp"] = out["gmv"] / out["expectativa_gmv_ano1"]
    out["painel_max_idx"] = panel_max
    return out


def allocate_cell_att_to_projects(
    projects: pd.DataFrame,
    att_cells: pd.DataFrame,
    metric: str,
) -> pd.DataFrame:
    """Alocação contábil do ATT do nicho. Não é efeito causal do SKU isolado."""
    att = att_cells.loc[att_cells["metric"] == metric].copy()
    att_map = att.set_index(["marca_std", "subcategoria"])["att_soma_pos"]
    status_map = att.set_index(["marca_std", "subcategoria"])["status"]
    out = projects.copy()
    keys = list(zip(out["marca_std"], out["subcategoria"]))
    out["att_nicho_status"] = [status_map.get(k) for k in keys]
    out["att_nicho_soma"] = [att_map.get(k) for k in keys]
    cell_gmv = out.groupby(["marca_std", "subcategoria"])["gmv"].transform("sum")
    out["peso_alocacao_gmv"] = np.where(cell_gmv > 0, out["gmv"] / cell_gmv, np.nan)
    out["spillover_alocado"] = out["att_nicho_soma"] * out["peso_alocacao_gmv"]
    # Só aloca quando o SC foi estimável.
    out.loc[out["att_nicho_status"] != "ok", "spillover_alocado"] = np.nan
    if metric == "gmv":
        out["incremental_estimado"] = out["gmv"] + out["spillover_alocado"]
    else:
        out["incremental_estimado"] = out["mb"] + out["spillover_alocado"]
    return out


def similar_robustness(
    similares: pd.DataFrame,
    produtos: pd.DataFrame,
) -> pd.DataFrame:
    """Pares utilizáveis como robustez — filtros explícitos, sem imputar score."""
    prod = produtos.set_index("cod_sku")
    rows = []
    for _, row in similares.iterrows():
        a, b = row["cod_sku_principal"], row["cod_sku_similar"]
        if a not in prod.index or b not in prod.index:
            continue
        pa, pb = prod.loc[a], prod.loc[b]
        usable = True
        reasons = []
        if pd.isna(row["score_similaridade_par"]):
            usable = False
            reasons.append("score_nulo")
        elif row["score_similaridade_par"] < SIMILAR_SCORE_MIN:
            usable = False
            reasons.append("score_abaixo_corte")
        if pa["subcategoria"] != pb["subcategoria"]:
            usable = False
            reasons.append("subcategoria_diferente")
        if pb["is_incumbent"] is False:
            usable = False
            reasons.append("similar_nao_incumbente")
        rows.append(
            {
                "cod_sku_principal": a,
                "cod_sku_similar": b,
                "score": row["score_similaridade_par"],
                "usable": usable,
                "motivo_exclusao": ",".join(reasons) if reasons else None,
            }
        )
    return pd.DataFrame(rows)
