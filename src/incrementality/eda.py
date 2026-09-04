"""Auditoria da base. Só descreve o que está nas tabelas."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .config import DICT_CICLO_MAX, DICT_CICLO_MIN


def _identity_checks(vendas: pd.DataFrame, produtos: pd.DataFrame) -> dict[str, Any]:
    merged = vendas.merge(
        produtos[["cod_sku", "preco_regular", "margem_bruta_pct"]],
        on="cod_sku",
        how="left",
    )
    priced = merged["preco_regular"].notna()
    delta_tabela = (merged["vlr_venda_tabela"] - merged["preco_regular"] * merged["qt_venda"]).abs()
    delta_praticado = (
        merged["vlr_venda_praticado"] - (merged["vlr_venda_tabela"] - merged["vlr_venda_desconto"])
    ).abs()
    delta_mb = (merged["margem_bruta"] - merged["vlr_venda_praticado"] * merged["margem_bruta_pct"]).abs()
    return {
        "tabela_vs_preco_qty_erros_0_05": int(((delta_tabela > 0.05) & priced).sum()),
        "praticado_vs_tabela_menos_desc_erros_0_05": int((delta_praticado > 0.05).sum()),
        "margem_vs_praticado_pct_erros_0_02": int((delta_mb > 0.02).sum()),
        "desconto_preenchido_como_zero": True,
    }


def run_eda(
    produtos: pd.DataFrame,
    projetos: pd.DataFrame,
    similares: pd.DataFrame,
    vendas: pd.DataFrame,
) -> dict[str, Any]:
    launch_skus = set(projetos["cod_sku_lancamento"])
    v_ts = vendas.loc[~vendas["flag_ciclo_nulo"]].copy()

    marca_raw = produtos["marca"].value_counts().to_dict()
    canal_raw = vendas["canal_venda"].value_counts().to_dict()

    n_sim_launch = int(projetos["cod_sku_lancamento"].isin(similares["cod_sku_principal"]).sum())
    dead_similar = similares.merge(
        produtos[["cod_sku", "cod_ciclo_phase_out"]],
        left_on="cod_sku_similar",
        right_on="cod_sku",
        how="left",
    )
    dead_before_panel = int((dead_similar["cod_ciclo_phase_out"] < 202401).sum())

    sim_launch = similares[similares["cod_sku_principal"].isin(launch_skus)]
    same_sub = 0
    n_pairs = 0
    prod_ix = produtos.set_index("cod_sku")
    for _, row in sim_launch.iterrows():
        if row["cod_sku_principal"] not in prod_ix.index or row["cod_sku_similar"] not in prod_ix.index:
            continue
        n_pairs += 1
        if (
            prod_ix.loc[row["cod_sku_principal"], "subcategoria"]
            == prod_ix.loc[row["cod_sku_similar"], "subcategoria"]
        ):
            same_sub += 1

    gmv_total = float(vendas["vlr_venda_praticado"].sum())
    gmv_launch = float(vendas.loc[vendas["cod_sku"].isin(launch_skus), "vlr_venda_praticado"].sum())
    gmv_ciclo_nulo = float(vendas.loc[vendas["flag_ciclo_nulo"], "vlr_venda_praticado"].sum())

    ticket = vendas.groupby("id_venda").agg(
        n=("cod_sku", "size"),
        n_ciclo=("cod_ciclo", "nunique"),
        n_uf=("uf", "nunique"),
        n_canal=("canal_std", "nunique"),
    )

    cells = (
        produtos.groupby(["marca_std", "subcategoria"], as_index=False)
        .agg(
            n_sku=("cod_sku", "size"),
            n_project=("is_project", "sum"),
            n_incumbent=("is_incumbent", "sum"),
            n_other_innovation=("is_other_innovation", "sum"),
        )
    )
    never_treated = cells.loc[cells["n_project"] == 0, ["marca_std", "subcategoria", "n_incumbent"]]

    audit: dict[str, Any] = {
        "shapes": {
            "produtos": list(produtos.shape),
            "projetos": list(projetos.shape),
            "similares": list(similares.shape),
            "vendas": list(vendas.shape),
        },
        "chaves": {
            "sku_unicos": int(produtos["cod_sku"].nunique()),
            "projetos_unicos": int(projetos["id_projeto"].nunique()),
            "sku_projeto_unicos": int(projetos["cod_sku_lancamento"].nunique()),
            "id_venda_nao_e_pk": True,
            "pk_vendas": "id_venda + cod_sku",
            "tickets": int(vendas["id_venda"].nunique()),
            "linhas_por_ticket_media": float(ticket["n"].mean()),
            "tickets_inconsistentes_ciclo_uf_canal": int(
                ((ticket["n_ciclo"] > 1) | (ticket["n_uf"] > 1) | (ticket["n_canal"] > 1)).sum()
            ),
        },
        "sujeira_cadastral": {
            "marca_bruta": marca_raw,
            "canal_bruto": canal_raw,
            "preco_regular_ausente": produtos.loc[
                produtos["preco_regular"].isna(), "cod_sku"
            ].tolist(),
            "campo_dicionario_ausente_no_cadastro": ["score_similaridade"],
            "sku_sem_venda": produtos.loc[~produtos["cod_sku"].isin(vendas["cod_sku"]), "cod_sku"].tolist(),
        },
        "ciclo": {
            "nulos": int(vendas["flag_ciclo_nulo"].sum()),
            "tickets_inteiros_nulos": int(
                vendas.loc[vendas["flag_ciclo_nulo"], "id_venda"].nunique()
            ),
            "gmv_ciclo_nulo": gmv_ciclo_nulo,
            "ciclos_distintos_observados": int(v_ts["cod_ciclo"].nunique()),
            "ciclo_min": int(v_ts["cod_ciclo"].min()),
            "ciclo_max": int(v_ts["cod_ciclo"].max()),
            "dicionario_min": DICT_CICLO_MIN,
            "dicionario_max": DICT_CICLO_MAX,
            "linhas_seq_13_a_17": int(vendas["flag_ciclo_seq_13_a_17"].fillna(False).sum()),
            "linhas_alem_dicionario": int(vendas["flag_ciclo_alem_dicionario"].fillna(False).sum()),
            "cadastro_phase_in_usa_seq_gt_12": False,
        },
        "identidades_financeiras": _identity_checks(vendas, produtos),
        "devolucoes": {
            "linhas_qty_negativa": int((vendas["qt_venda"] < 0).sum()),
            "gmv_devolucoes": float(vendas.loc[vendas["qt_venda"] < 0, "vlr_venda_praticado"].sum()),
        },
        "portfolio": {
            "projetos": int(produtos["is_project"].sum()),
            "incumbentes": int(produtos["is_incumbent"].sum()),
            "outras_inovacoes_fora_da_tabela_projeto": int(produtos["is_other_innovation"].sum()),
        },
        "similares": {
            "pares": int(len(similares)),
            "score_nulo": int(similares["score_similaridade_par"].isna().sum()),
            "projetos_com_lista_como_principal": n_sim_launch,
            "projetos_sem_lista": int(len(projetos) - n_sim_launch),
            "pares_com_similar_descontinuado_antes_do_painel": dead_before_panel,
            "pares_de_projeto_mesma_subcategoria": same_sub,
            "pares_de_projeto_avaliados": n_pairs,
            "grafo_simetrico": False,
        },
        "gmv": {
            "total": gmv_total,
            "projetos": gmv_launch,
            "share_projetos": gmv_launch / gmv_total if gmv_total else None,
        },
        "celulas_nunca_tratadas": never_treated.to_dict(orient="records"),
        "celulas_com_projeto": cells.loc[cells["n_project"] > 0].to_dict(orient="records"),
    }
    return audit
