"""Recalcula as tabelas em outputs/ a partir da planilha."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from incrementality.config import OUTPUTS_DIR, PROCESSED_DIR, TABLES_DIR  # noqa: E402
from incrementality.model import cesta, estimar, pares_usaveis  # noqa: E402
from incrementality.prepare import auditar, carregar  # noqa: E402
from incrementality.roi import build_painel_comite  # noqa: E402

ROI_COLS = [
    "id_projeto",
    "cod_sku_lancamento",
    "marca_std",
    "subcategoria",
    "faixa_preco",
    "cod_ciclo_phase_in",
    "ciclos_expostos",
    "ciclos_janela_roi",
    "n_post_roi",
    "gmv",
    "mb",
    "expectativa_gmv_ano1",
    "atingimento_bruto_vs_exp",
    "investimento_mkt_rs",
    "att_status",
    "n_projetos",
    "gmv_spillover_alocado",
    "gmv_incremental",
    "mb_spillover_alocado",
    "mb_incremental",
    "roi_parcial_midia",
    "payback_parcial_midia",
    "alerta_pouco_tempo",
    "selo",
]


def _json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    produtos, projetos, similares, vendas = carregar()
    produtos.to_parquet(PROCESSED_DIR / "produtos.parquet", index=False)
    projetos.to_parquet(PROCESSED_DIR / "projetos.parquet", index=False)
    similares.to_parquet(PROCESSED_DIR / "similares.parquet", index=False)
    vendas.to_parquet(PROCESSED_DIR / "vendas.parquet", index=False)

    _json(OUTPUTS_DIR / "eda_audit.json", auditar(produtos, projetos, similares, vendas))

    csv_dir = ROOT / "data" / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    (
        vendas.groupby(["cod_ciclo_bruto", "cod_ciclo"], dropna=False)
        .size()
        .reset_index(name="n_linhas")
        .sort_values(["cod_ciclo", "cod_ciclo_bruto"])
        .to_csv(csv_dir / "ciclos_mapeados.csv", index=False)
    )

    out = estimar(vendas, produtos, projetos)
    att = out["att"]
    att_gmv = att.loc[att["metric"] == "gmv"]
    roi = out["roi"]
    paths = out["paths_gmv"]
    ev = out["event_study_medio"]

    out["starts"].to_csv(TABLES_DIR / "celulas_tratamento.csv", index=False)
    out["donors"].to_csv(TABLES_DIR / "celulas_doadoras.csv", index=False)
    out["panel_gmv"].to_csv(TABLES_DIR / "painel_incumbente_gmv.csv", index=False)
    att.drop(columns=["pesos", "placebo_ratios"], errors="ignore").to_csv(
        TABLES_DIR / "att_celulas.csv", index=False
    )
    peso_cols = [c for c in ["marca_std", "subcategoria", "faixa_preco", "pesos"] if c in att_gmv.columns]
    _json(
        OUTPUTS_DIR / "att_pesos.json",
        att_gmv.loc[att_gmv["status"] == "ok", peso_cols].to_dict(orient="records"),
    )
    paths.to_csv(TABLES_DIR / "event_study_gmv.csv", index=False)
    ev.to_csv(TABLES_DIR / "event_study_gmv_medio.csv", index=False)
    roi.to_csv(TABLES_DIR / "roi_projetos.csv", index=False)
    roi[[c for c in ROI_COLS if c in roi.columns]].to_csv(TABLES_DIR / "roi_projetos_resumo.csv", index=False)
    build_painel_comite(roi, att).to_csv(TABLES_DIR / "painel_comite.csv", index=False)

    sim_flag = pares_usaveis(similares, produtos)
    sim_flag.to_csv(TABLES_DIR / "similares_usaveis.csv", index=False)
    cesta(vendas, produtos, projetos).to_csv(TABLES_DIR / "cesta_substituicao.csv", index=False)

    estim = roi.loc[roi["mb_incremental"].notna()]
    headline = {
        "celula": out["label"],
        "gmv_direto_projetos": float(roi["gmv"].sum()),
        "mb_direto_projetos": float(roi["mb"].sum()),
        "midia_total": float(roi["investimento_mkt_rs"].sum()),
        "gmv_incremental_soma_estimavel": float(roi["gmv_incremental"].sum(skipna=True)),
        "mb_incremental_soma_estimavel": float(roi["mb_incremental"].sum(skipna=True)),
        "midia_projetos_estimaveis": float(estim["investimento_mkt_rs"].sum()),
        "payback_parcial_estimavel": float(estim["payback_parcial_midia"].sum()),
        "n_selo": roi["selo"].value_counts(dropna=False).to_dict(),
        "n_celulas_sc_ok": int((att_gmv["status"] == "ok").sum()),
        "n_celulas_nao_identificadas": int((att_gmv["status"] != "ok").sum()),
        "n_pares_similares_usaveis": int(sim_flag["usable"].sum()),
        "n_pares_similares_total": int(len(sim_flag)),
        "n_ciclo_nulo_apos_mapa": int(vendas["flag_ciclo_nulo"].sum()),
        "n_ciclos_distintos": int(vendas["cod_ciclo"].nunique()),
        "event_study_gap": ev.to_dict(orient="records"),
    }
    _json(OUTPUTS_DIR / "headline.json", headline)
    print(json.dumps(headline, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
