"""Incrementalidade na célula (marca × subcategoria × faixa_preco).

O lançamento não tem pré. O contrafactual é a base antiga da mesma célula.
Doadores = células que nunca receberam projeto nesta tabela.

Zero depois do `cod_ciclo_phase_out` do incumbente não entra no ATT: o
produto saiu de linha, não é canibalização contra um espelho ainda vivo.

O match é no índice do pré (média = 1), depois volta para R$. Ajuste em
nível mistura célula pequena com doador grande e fabrica canibalização.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import (
    CELL_KEYS,
    EVENT_POST,
    EVENT_PRE,
    MIN_PRE_CYCLES,
    PRE_FIT_MAX_REL,
    ROI_MAX_CYCLES,
    SIMILAR_SCORE_MIN,
)
from .roi import build_roi


def _pesos(y_pre: np.ndarray, y0_pre: np.ndarray) -> np.ndarray:
    _, j = y0_pre.shape
    if j == 0 or len(y_pre) == 0:
        raise ValueError("doador vazio")

    def loss(w: np.ndarray) -> float:
        return float(np.sum((y_pre - y0_pre @ w) ** 2))

    w0 = np.full(j, 1.0 / j)
    result = minimize(
        loss,
        w0,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * j,
        constraints={"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        options={"maxiter": 800, "ftol": 1e-14},
    )
    w = np.clip(result.x, 0.0, 1.0)
    total = w.sum()
    return w / total if total > 0 else w0


def _rmspe(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((a - b) ** 2)))


def _sintetico(
    y: np.ndarray,
    donor_mat: np.ndarray,
    pre_pos: list[int],
    donor_keys: list[tuple],
) -> tuple[np.ndarray, np.ndarray, list[tuple]] | None:
    escala = float(np.mean(y[pre_pos]))
    if abs(escala) < 1e-9:
        return None
    donor_esc = donor_mat[pre_pos, :].mean(axis=0)
    valid = np.abs(donor_esc) >= 1e-9
    if int(valid.sum()) == 0:
        return None
    w = _pesos(y[pre_pos] / escala, donor_mat[pre_pos, :][:, valid] / donor_esc[valid])
    synth = (donor_mat[:, valid] / donor_esc[valid] @ w) * escala
    keys = [k for k, keep in zip(donor_keys, valid) if keep]
    return synth, w, keys


def _chave(row: pd.Series, keys: tuple[str, ...]) -> tuple:
    return tuple(row[k] for k in keys)


def _rotulo(key: tuple) -> str:
    return "|".join(str(x) for x in key)


def _serie(panel: pd.DataFrame, key: tuple, keys: tuple[str, ...], grid: np.ndarray) -> np.ndarray:
    sub = panel
    for col, val in zip(keys, key):
        sub = sub[sub[col] == val]
    return sub.set_index("ciclo_idx")["valor"].reindex(grid, fill_value=0.0).to_numpy(dtype=float)


def painel_incumbente(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    value_col: str,
    cell_keys: tuple[str, ...] = CELL_KEYS,
) -> pd.DataFrame:
    """GMV ou margem da base antiga, por célula e ciclo."""
    cols = ["cod_sku", *cell_keys]
    base = produtos.loc[produtos["is_incumbent"].fillna(False), cols]
    return (
        vendas.loc[~vendas["flag_ciclo_nulo"] & vendas["cod_sku"].isin(base["cod_sku"])]
        .merge(base, on="cod_sku", how="left")
        .groupby([*cell_keys, "ciclo_idx", "cod_ciclo"], as_index=False)
        .agg(valor=(value_col, "sum"))
    )


def _tratar_e_doar(
    produtos: pd.DataFrame,
    projetos: pd.DataFrame,
    cell_keys: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lanc = projetos.merge(
        produtos[["cod_sku", *cell_keys, "phase_in_idx", "cod_ciclo_phase_in"]],
        left_on="cod_sku_lancamento",
        right_on="cod_sku",
        how="left",
    )
    starts = lanc.groupby(list(cell_keys), as_index=False).agg(
        t0_idx=("phase_in_idx", "min"),
        t0_ciclo=("cod_ciclo_phase_in", "min"),
        n_projetos=("id_projeto", "nunique"),
        projetos=("id_projeto", lambda s: ",".join(sorted(s.astype(str)))),
        skus=("cod_sku_lancamento", lambda s: ",".join(sorted(s.astype(str)))),
    )
    n_inc = produtos.groupby(list(cell_keys), as_index=False).agg(n_incumbent=("is_incumbent", "sum"))
    starts = starts.merge(n_inc, on=list(cell_keys), how="left")
    starts["n_incumbent"] = starts["n_incumbent"].fillna(0)

    # Último ciclo em linha: se algum incumbente não tem phase_out, a série segue
    # até o fim da base. Se todos saíram, o ATT para nesse ciclo — zero depois
    # disso não é canibalização, é produto fora do cadastro.
    inc_po = produtos.loc[
        produtos["is_incumbent"].fillna(False),
        list(cell_keys) + ["phase_out_idx"],
    ]
    if len(inc_po):
        shelf = (
            inc_po.groupby(list(cell_keys), as_index=False)
            .agg(
                n_sem_phase_out=("phase_out_idx", lambda s: int(s.isna().sum())),
                shelf_end_idx=("phase_out_idx", "max"),
            )
        )
        shelf.loc[shelf["n_sem_phase_out"] > 0, "shelf_end_idx"] = np.nan
        starts = starts.merge(shelf[list(cell_keys) + ["shelf_end_idx"]], on=list(cell_keys), how="left")
    else:
        starts["shelf_end_idx"] = np.nan

    cells = produtos.groupby(list(cell_keys), as_index=False).agg(
        n_project=("is_project", "sum"),
        n_incumbent=("is_incumbent", "sum"),
    )
    donors = cells.loc[(cells["n_project"] == 0) & (cells["n_incumbent"] > 0)].copy()
    return starts, donors


def _att(
    panel: pd.DataFrame,
    starts: pd.DataFrame,
    donors: pd.DataFrame,
    metric: str,
    cell_keys: tuple[str, ...],
    with_paths: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    grid = np.array(sorted(panel["ciclo_idx"].dropna().unique()), dtype=int)
    donor_keys = [_chave(row, cell_keys) for _, row in donors.iterrows()]
    donor_mat = (
        np.column_stack([_serie(panel, k, cell_keys, grid) for k in donor_keys])
        if donor_keys
        else np.zeros((len(grid), 0))
    )
    idx_pos = {int(k): i for i, k in enumerate(grid)}
    att_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []

    for _, cell in starts.iterrows():
        t0 = cell["t0_idx"]
        if pd.isna(t0):
            continue
        t0 = int(t0)
        key = _chave(cell, cell_keys)
        y = _serie(panel, key, cell_keys, grid)
        pre_keys = [k for k in grid if k < t0]
        shelf = cell.get("shelf_end_idx")
        if pd.notna(shelf):
            post_keys = [k for k in grid if t0 <= k <= int(shelf)]
        else:
            post_keys = [k for k in grid if k >= t0]
        n_post_calendario = int((grid >= t0).sum())
        roi_end = t0 + ROI_MAX_CYCLES - 1
        roi_keys = [k for k in post_keys if k <= roi_end]
        n_inc = int(cell["n_incumbent"])
        if n_inc == 0:
            status = "sem_incumbente"
        elif len(pre_keys) < MIN_PRE_CYCLES:
            status = "sem_pre_periodo_suficiente"
        elif donor_mat.shape[1] == 0:
            status = "sem_doador"
        elif len(post_keys) == 0:
            status = "incumbente_fora_antes_do_t0"
        else:
            status = "ok"

        rec: dict[str, Any] = {
            "metric": metric,
            "t0_idx": t0,
            "t0_ciclo": int(cell["t0_ciclo"]),
            "n_projetos_celula": int(cell["n_projetos"]),
            "projetos": cell["projetos"],
            "n_pre": len(pre_keys),
            "n_post": len(post_keys),
            "n_post_roi": len(roi_keys),
            "n_post_calendario": n_post_calendario,
            "n_post_excluido_phase_out": n_post_calendario - len(post_keys),
            "janela_roi_incompleta": len(roi_keys) < ROI_MAX_CYCLES,
            "shelf_end_idx": None if pd.isna(shelf) else int(shelf),
            "n_donors": int(donor_mat.shape[1]),
            "status": status,
            "cell_id": _rotulo(key),
        }
        for col in cell_keys:
            rec[col] = cell[col]
        if status != "ok":
            att_rows.append(rec)
            continue

        pre_pos = [idx_pos[k] for k in pre_keys]
        post_pos = [idx_pos[k] for k in post_keys]
        fitted = _sintetico(y, donor_mat, pre_pos, donor_keys)
        if fitted is None:
            rec["status"] = "sem_escala_pre"
            att_rows.append(rec)
            continue
        synth, weights, used_keys = fitted
        gap = y - synth
        rmspe_pre = _rmspe(y[pre_pos], synth[pre_pos])
        y_pre = float(y[pre_pos].mean())
        fit_rel = rmspe_pre / abs(y_pre) if abs(y_pre) > 0 else float("inf")
        if fit_rel > PRE_FIT_MAX_REL:
            rec["status"] = "ajuste_pre_fraco"
        rec.update(
            {
                "rmspe_pre": rmspe_pre,
                "rmspe_post": _rmspe(y[post_pos], synth[post_pos]),
                "fit_rel_pre": float(fit_rel),
                "att_media_ciclo": float(gap[post_pos].mean()),
                "att_soma_pos": float(gap[post_pos].sum()),
                "att_soma_roi": float(gap[[idx_pos[k] for k in roi_keys]].sum()) if roi_keys else 0.0,
                "y_pre_media": y_pre,
                "synth_pre_media": float(synth[pre_pos].mean()),
                "y_post_media": float(y[post_pos].mean()),
                "synth_post_media": float(synth[post_pos].mean()),
                "pesos": {_rotulo(k): float(w) for k, w in zip(used_keys, weights) if w >= 0.01},
            }
        )
        if rec["status"] != "ok":
            att_rows.append(rec)
            continue

        treated_ratio = rec["rmspe_post"] / rec["rmspe_pre"] if rec["rmspe_pre"] > 0 else np.inf
        placebo: list[float] = []
        for j in range(donor_mat.shape[1]):
            fitted_p = _sintetico(
                donor_mat[:, j],
                np.delete(donor_mat, j, axis=1),
                pre_pos,
                [k for i, k in enumerate(donor_keys) if i != j],
            )
            if fitted_p is None:
                continue
            synth_p, _, _ = fitted_p
            pre_r = _rmspe(donor_mat[pre_pos, j], synth_p[pre_pos])
            post_r = _rmspe(donor_mat[post_pos, j], synth_p[post_pos])
            if pre_r > 0:
                placebo.append(post_r / pre_r)
        rec["placebo_pvalue_rmspe_ratio"] = (
            float(np.mean(np.array(placebo) >= treated_ratio)) if placebo else None
        )
        rec["n_placebos"] = len(placebo)
        rec["rmspe_ratio"] = float(treated_ratio) if np.isfinite(treated_ratio) else None
        rec["placebo_ratio_mediana"] = float(np.median(placebo)) if placebo else None
        rec["placebo_ratios"] = placebo
        att_rows.append(rec)

        if with_paths:
            for k in grid:
                e = int(k - t0)
                if e < -EVENT_PRE or e > EVENT_POST:
                    continue
                if pd.notna(shelf) and k > int(shelf):
                    continue
                pos = idx_pos[int(k)]
                row: dict[str, Any] = {
                    "metric": metric,
                    "event_time": e,
                    "ciclo_idx": int(k),
                    "observado": float(y[pos]),
                    "sintetico": float(synth[pos]),
                    "gap": float(y[pos] - synth[pos]),
                    "cell_id": _rotulo(key),
                }
                for col in cell_keys:
                    row[col] = cell[col]
                path_rows.append(row)

    return pd.DataFrame(att_rows), pd.DataFrame(path_rows)


def _metricas_diretas(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    projetos: pd.DataFrame,
    att: pd.DataFrame,
    cell_keys: tuple[str, ...],
) -> pd.DataFrame:
    """Sell-out do SKU novo na janela do ROI (mesmos ciclos do ATT)."""
    keep = [
        "cod_sku", "marca_std", "categoria", "subcategoria", "faixa_preco",
        "preco_regular", "margem_bruta_pct", "cod_ciclo_phase_in", "cod_ciclo_phase_out",
        "phase_in_idx", "phase_out_idx",
    ]
    lanc = projetos.merge(produtos[keep], left_on="cod_sku_lancamento", right_on="cod_sku", how="left")
    janela = att.loc[
        att["metric"] == "gmv",
        list(cell_keys) + ["t0_idx", "n_post_roi"],
    ].drop_duplicates(list(cell_keys))
    lanc = lanc.merge(janela, on=list(cell_keys), how="left")
    v = vendas.loc[~vendas["flag_ciclo_nulo"], ["cod_sku", "ciclo_idx", "vlr_venda_praticado", "margem_bruta", "qt_venda"]]
    vida = (
        v.groupby("cod_sku")
        .agg(
            gmv_vida=("vlr_venda_praticado", "sum"),
            mb_vida=("margem_bruta", "sum"),
            min_idx=("ciclo_idx", "min"),
            max_idx=("ciclo_idx", "max"),
            n_ciclos=("ciclo_idx", "nunique"),
        )
        .reset_index()
    )
    out = lanc.merge(vida, left_on="cod_sku_lancamento", right_on="cod_sku", how="left")
    gmv_w, mb_w, qty_w = [], [], []
    for _, row in out.iterrows():
        sku = row["cod_sku_lancamento"]
        sv = v.loc[v["cod_sku"] == sku]
        t0, n = row["t0_idx"], row["n_post_roi"]
        if pd.isna(t0) or pd.isna(n) or int(n) <= 0:
            gmv_w.append(np.nan)
            mb_w.append(np.nan)
            qty_w.append(np.nan)
            continue
        t1 = int(t0) + int(n) - 1
        svw = sv.loc[sv["ciclo_idx"].between(int(t0), t1)]
        gmv_w.append(float(svw["vlr_venda_praticado"].sum()))
        mb_w.append(float(svw["margem_bruta"].sum()))
        qty_w.append(float(svw["qt_venda"].sum()))
    out["gmv"] = gmv_w
    out["mb"] = mb_w
    out["qty"] = qty_w
    out["ciclos_expostos"] = (out["max_idx"] - out["phase_in_idx"] + 1).clip(lower=0)
    out["ciclos_janela_roi"] = out["n_post_roi"]
    out["atingimento_bruto_vs_exp"] = out["gmv"] / out["expectativa_gmv_ano1"]
    return out


def _alocar(projects: pd.DataFrame, att: pd.DataFrame, metric: str, cell_keys: tuple[str, ...]) -> pd.DataFrame:
    """Rateia o ATT da janela de ROI pelo GMV de cada projeto nessa janela."""
    sub = att.loc[att["metric"] == metric]
    col_att = "att_soma_roi" if "att_soma_roi" in sub.columns else "att_soma_pos"
    att_map = sub.set_index(list(cell_keys))[col_att]
    status_map = sub.set_index(list(cell_keys))["status"]
    n_map = sub.set_index(list(cell_keys))["n_post_roi"] if "n_post_roi" in sub.columns else None
    inc_map = sub.set_index(list(cell_keys))["janela_roi_incompleta"] if "janela_roi_incompleta" in sub.columns else None
    out = projects.copy()
    keys = [_chave(row, cell_keys) for _, row in out.iterrows()]
    out["att_status"] = [status_map.get(k) for k in keys]
    out["att_soma"] = [att_map.get(k) for k in keys]
    if n_map is not None:
        out["n_post_roi"] = [n_map.get(k) for k in keys]
    if inc_map is not None:
        out["janela_roi_incompleta"] = [inc_map.get(k) for k in keys]
    cell_gmv = out.groupby(list(cell_keys))["gmv"].transform("sum")
    out["peso_alocacao_gmv"] = np.where(cell_gmv > 0, out["gmv"] / cell_gmv, np.nan)
    out["spillover_alocado"] = out["att_soma"] * out["peso_alocacao_gmv"]
    out.loc[out["att_status"] != "ok", "spillover_alocado"] = np.nan
    t0 = pd.to_numeric(out.get("t0_idx"), errors="coerce")
    n_w = pd.to_numeric(out.get("n_post_roi"), errors="coerce")
    pin = pd.to_numeric(out.get("phase_in_idx"), errors="coerce")
    depois = pin.notna() & t0.notna() & n_w.notna() & (pin > t0 + n_w - 1)
    out.loc[depois, "att_status"] = "fora_da_janela_da_celula"
    out.loc[depois, "spillover_alocado"] = np.nan
    valor = out["gmv"] if metric == "gmv" else out["mb"]
    out["incremental_estimado"] = valor + out["spillover_alocado"]
    out.loc[depois, "incremental_estimado"] = np.nan
    return out


def estimar(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    projetos: pd.DataFrame,
    cell_keys: tuple[str, ...] = CELL_KEYS,
) -> dict[str, Any]:
    """ATT da base antiga + sell-out do novo + ROI por projeto."""
    starts, donors = _tratar_e_doar(produtos, projetos, cell_keys)
    panel_gmv = painel_incumbente(vendas, produtos, "vlr_venda_praticado", cell_keys)
    panel_mb = painel_incumbente(vendas, produtos, "margem_bruta", cell_keys)
    att_gmv, paths = _att(panel_gmv, starts, donors, "gmv", cell_keys, with_paths=True)
    att_mb, _ = _att(panel_mb, starts, donors, "mb", cell_keys, with_paths=False)
    att = pd.concat([att_gmv, att_mb], ignore_index=True)

    direto = _metricas_diretas(vendas, produtos, projetos, att, cell_keys)
    proj_gmv = _alocar(direto, att, "gmv", cell_keys)
    proj_mb = _alocar(direto.copy(), att, "mb", cell_keys)
    roi = build_roi(proj_gmv, proj_mb).merge(
        starts[list(cell_keys) + ["n_projetos"]],
        on=list(cell_keys),
        how="left",
    )
    ev_med = pd.DataFrame()
    if len(paths):
        ev_med = (
            paths.groupby("event_time", as_index=False)
            .agg(observado=("observado", "mean"), sintetico=("sintetico", "mean"), gap=("gap", "mean"))
            .sort_values("event_time")
        )
    return {
        "starts": starts,
        "donors": donors,
        "att": att,
        "roi": roi,
        "paths_gmv": paths,
        "event_study_medio": ev_med,
        "panel_gmv": panel_gmv,
        "cell_keys": cell_keys,
        "label": "marca × subcategoria × faixa_preco",
    }


def pares_usaveis(similares: pd.DataFrame, produtos: pd.DataFrame) -> pd.DataFrame:
    """Auditoria de tb_skus_similares. Não entra no ATT nem no ROI."""
    prod = produtos.set_index("cod_sku")
    rows = []
    for _, row in similares.iterrows():
        a, b = row["cod_sku_principal"], row["cod_sku_similar"]
        if a not in prod.index or b not in prod.index:
            continue
        pa, pb = prod.loc[a], prod.loc[b]
        reasons = []
        if pd.isna(row["score_similaridade_par"]):
            reasons.append("score_nulo")
        elif row["score_similaridade_par"] < SIMILAR_SCORE_MIN:
            reasons.append("score_abaixo_corte")
        if pa["subcategoria"] != pb["subcategoria"]:
            reasons.append("subcategoria_diferente")
        if pb["is_incumbent"] is False:
            reasons.append("similar_nao_incumbente")
        rows.append(
            {
                "cod_sku_principal": a,
                "cod_sku_similar": b,
                "score": row["score_similaridade_par"],
                "usable": not reasons,
                "motivo_exclusao": ",".join(reasons) if reasons else None,
            }
        )
    return pd.DataFrame(rows)


def cesta(vendas: pd.DataFrame, produtos: pd.DataFrame, projetos: pd.DataFrame) -> pd.DataFrame:
    """No ticket do lançamento, o cliente levou incumbente da mesma subcategoria?

    Retrato de cesta, não identificador. Sem experimento não dá para chamar
    de substituição causal.
    """
    launch = projetos.merge(
        produtos[["cod_sku", "marca_std", "subcategoria"]],
        left_on="cod_sku_lancamento",
        right_on="cod_sku",
        how="left",
    )
    incumbents = produtos.loc[produtos["is_incumbent"], ["cod_sku", "marca_std", "subcategoria"]]
    v = vendas.loc[~vendas["flag_ciclo_nulo"], ["id_venda", "cod_sku"]]
    inc_by = {
        (m, s): set(g["cod_sku"])
        for (m, s), g in incumbents.groupby(["marca_std", "subcategoria"])
    }
    ticket_skus = v.groupby("id_venda")["cod_sku"].apply(set)
    rows = []
    for _, proj in launch.iterrows():
        sku = proj["cod_sku_lancamento"]
        inc_set = inc_by.get((proj["marca_std"], proj["subcategoria"]), set())
        tickets = [tid for tid, skus in ticket_skus.items() if sku in skus]
        if not tickets:
            rows.append(
                {
                    "id_projeto": proj["id_projeto"],
                    "cod_sku_lancamento": sku,
                    "tickets_com_lancamento": 0,
                    "tickets_sozinho": 0,
                    "tickets_com_incumbente_tipo": 0,
                    "share_sozinho": None,
                    "share_com_incumbente_tipo": None,
                }
            )
            continue
        alone = with_inc = 0
        for tid in tickets:
            others = ticket_skus[tid] - {sku}
            if not others:
                alone += 1
            if others & inc_set:
                with_inc += 1
        n = len(tickets)
        rows.append(
            {
                "id_projeto": proj["id_projeto"],
                "cod_sku_lancamento": sku,
                "tickets_com_lancamento": n,
                "tickets_sozinho": alone,
                "tickets_com_incumbente_tipo": with_inc,
                "share_sozinho": alone / n,
                "share_com_incumbente_tipo": with_inc / n,
            }
        )
    return pd.DataFrame(rows)
