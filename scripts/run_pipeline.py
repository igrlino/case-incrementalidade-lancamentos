"""Pipeline reproduzível do case: EDA → causal → ROI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from incrementality.basket import basket_substitution  # noqa: E402
from incrementality.causal import (  # noqa: E402
    allocate_cell_att_to_projects,
    build_incumbent_panel,
    cell_treatment_starts,
    event_paths,
    never_treated_cells,
    project_direct_metrics,
    similar_robustness,
    synthetic_control_cells,
)
from incrementality.clean import (  # noqa: E402
    clean_produtos,
    clean_projetos,
    clean_similares,
    clean_vendas,
)
from incrementality.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR, TABLES_DIR  # noqa: E402
from incrementality.eda import run_eda  # noqa: E402
from incrementality.io import load_raw  # noqa: E402
from incrementality.roi import build_roi  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    raw = load_raw()
    projetos = clean_projetos(raw["tb_projetos_lancamento"])
    produtos = clean_produtos(raw["tb_produtos_atributos"], set(projetos["cod_sku_lancamento"]))
    similares = clean_similares(raw["tb_skus_similares"])
    vendas = clean_vendas(raw["tb_vendas"])

    csv_dir = ROOT / "data" / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    ciclos_ok = (
        vendas.groupby(["cod_ciclo_bruto", "cod_ciclo"], dropna=False)
        .size()
        .reset_index(name="n_linhas")
        .sort_values(["cod_ciclo", "cod_ciclo_bruto"])
    )
    ciclos_ok.to_csv(csv_dir / "ciclos_mapeados.csv", index=False)
    vendas["cod_ciclo"].value_counts().sort_index().rename_axis("cod_ciclo").reset_index(
        name="n_linhas"
    ).to_csv(csv_dir / "ciclos_normalizados.csv", index=False)

    produtos.to_parquet(PROCESSED_DIR / "produtos.parquet", index=False)
    projetos.to_parquet(PROCESSED_DIR / "projetos.parquet", index=False)
    similares.to_parquet(PROCESSED_DIR / "similares.parquet", index=False)
    vendas.to_parquet(PROCESSED_DIR / "vendas.parquet", index=False)

    audit = run_eda(produtos, projetos, similares, vendas)
    _write_json(OUTPUTS_DIR / "eda_audit.json", audit)

    donors = never_treated_cells(produtos)
    starts = cell_treatment_starts(produtos, projetos)
    inc_count = produtos.groupby(["marca_std", "subcategoria"], as_index=False).agg(
        n_incumbent=("is_incumbent", "sum")
    )
    starts = starts.merge(inc_count, on=["marca_std", "subcategoria"], how="left")
    starts.to_csv(TABLES_DIR / "celulas_tratamento.csv", index=False)
    donors.to_csv(TABLES_DIR / "celulas_doadoras.csv", index=False)

    panel_gmv = build_incumbent_panel(vendas, produtos, "vlr_venda_praticado")
    panel_mb = build_incumbent_panel(vendas, produtos, "margem_bruta")
    panel_gmv.to_csv(TABLES_DIR / "painel_incumbente_gmv.csv", index=False)

    att_gmv = synthetic_control_cells(panel_gmv, starts, donors, "gmv")
    att_mb = synthetic_control_cells(panel_mb, starts, donors, "mb")
    att = pd.concat([att_gmv, att_mb], ignore_index=True)
    att.drop(columns=["pesos"], errors="ignore").to_csv(TABLES_DIR / "att_nicho.csv", index=False)
    _write_json(
        OUTPUTS_DIR / "att_pesos.json",
        att_gmv.loc[att_gmv["status"] == "ok", ["marca_std", "subcategoria", "pesos"]].to_dict(
            orient="records"
        ),
    )

    paths_gmv = event_paths(panel_gmv, starts, donors, "gmv")
    paths_gmv.to_csv(TABLES_DIR / "event_study_gmv.csv", index=False)

    direct = project_direct_metrics(vendas, produtos, projetos)
    proj_gmv = allocate_cell_att_to_projects(direct, att, "gmv")
    # reutiliza as colunas de spillover de MB
    direct_mb = direct.copy()
    proj_mb = allocate_cell_att_to_projects(direct_mb, att, "mb")

    roi = build_roi(proj_gmv, proj_mb)
    roi = roi.merge(
        starts[["marca_std", "subcategoria", "n_projetos"]],
        on=["marca_std", "subcategoria"],
        how="left",
    )
    roi.to_csv(TABLES_DIR / "roi_projetos.csv", index=False)
    keep = [
        c
        for c in [
            "id_projeto",
            "cod_sku_lancamento",
            "marca_std",
            "subcategoria",
            "cod_ciclo_phase_in",
            "ciclos_expostos",
            "gmv",
            "mb",
            "expectativa_gmv_ano1",
            "atingimento_bruto_vs_exp",
            "investimento_mkt_rs",
            "att_nicho_status",
            "n_projetos",
            "gmv_spillover_alocado",
            "gmv_incremental",
            "mb_spillover_alocado",
            "mb_incremental",
            "roi_parcial_midia",
            "payback_parcial_midia",
            "alerta_janela_curta",
            "gate",
        ]
        if c in roi.columns
    ]
    roi[keep].to_csv(TABLES_DIR / "roi_projetos_resumo.csv", index=False)

    similar_flag = similar_robustness(similares, produtos)
    similar_flag.to_csv(TABLES_DIR / "similares_usaveis.csv", index=False)

    baskets = basket_substitution(vendas, produtos, projetos)
    baskets.to_csv(TABLES_DIR / "cesta_substituicao.csv", index=False)

    ev_agg = (
        paths_gmv.groupby("event_time", as_index=False)
        .agg(observado=("observado", "mean"), sintetico=("sintetico", "mean"), gap=("gap", "mean"))
        .sort_values("event_time")
    )
    ev_agg.to_csv(TABLES_DIR / "event_study_gmv_medio.csv", index=False)

    estim = roi.loc[roi["mb_incremental"].notna()]
    headline = {
        "gmv_direto_projetos": float(roi["gmv"].sum()),
        "mb_direto_projetos": float(roi["mb"].sum()),
        "midia_total": float(roi["investimento_mkt_rs"].sum()),
        "gmv_incremental_soma_estimavel": float(roi["gmv_incremental"].sum(skipna=True)),
        "mb_incremental_soma_estimavel": float(roi["mb_incremental"].sum(skipna=True)),
        "midia_projetos_estimaveis": float(estim["investimento_mkt_rs"].sum()),
        "payback_parcial_estimavel": float(estim["payback_parcial_midia"].sum()),
        "n_gate": roi["gate"].value_counts(dropna=False).to_dict(),
        "n_celulas_sc_ok": int((att_gmv["status"] == "ok").sum()),
        "n_celulas_nao_identificadas": int((att_gmv["status"] != "ok").sum()),
        "n_pares_similares_usaveis": int(similar_flag["usable"].sum()),
        "n_pares_similares_total": int(len(similar_flag)),
        "n_ciclo_nulo_apos_mapa": int(vendas["flag_ciclo_nulo"].sum()),
        "n_ciclos_distintos": int(vendas["cod_ciclo"].nunique()),
        "event_study_gap": ev_agg.to_dict(orient="records"),
    }
    _write_json(OUTPUTS_DIR / "headline.json", headline)
    print(json.dumps(headline, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
