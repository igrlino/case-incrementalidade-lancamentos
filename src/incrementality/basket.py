"""Triangulação via cesta. Não é identificador causal — é mecanismo."""

from __future__ import annotations

import pandas as pd


def basket_substitution(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    projetos: pd.DataFrame,
) -> pd.DataFrame:
    """De cada ticket com lançamento, vê se entra incumbente do mesmo nicho.

    Interpretação: co-ocorrência baixa sugere substituição na mesma viagem;
    alta sugere complemento ou ticket expandido. Sem aleatorização, não
    identificamos efeito causal — só descrevemos o mecanismo de cesta.
    """
    launch = projetos.merge(
        produtos[["cod_sku", "marca_std", "subcategoria"]],
        left_on="cod_sku_lancamento",
        right_on="cod_sku",
        how="left",
    )
    incumbents = produtos.loc[
        produtos["is_incumbent"], ["cod_sku", "marca_std", "subcategoria"]
    ]
    v = vendas.loc[~vendas["flag_ciclo_nulo"], ["id_venda", "cod_sku"]].copy()
    v = v.merge(
        produtos[["cod_sku", "marca_std", "subcategoria", "is_incumbent", "is_project"]],
        on="cod_sku",
        how="left",
    )
    rows = []
    # Pré-indexa SKUs de incumbentes por nicho
    inc_by_cell = {
        (m, s): set(g["cod_sku"])
        for (m, s), g in incumbents.groupby(["marca_std", "subcategoria"])
    }
    ticket_skus = v.groupby("id_venda")["cod_sku"].apply(set)
    for _, proj in launch.iterrows():
        sku = proj["cod_sku_lancamento"]
        cell = (proj["marca_std"], proj["subcategoria"])
        inc_set = inc_by_cell.get(cell, set())
        tickets_with = [tid for tid, skus in ticket_skus.items() if sku in skus]
        if not tickets_with:
            rows.append(
                {
                    "id_projeto": proj["id_projeto"],
                    "cod_sku_lancamento": sku,
                    "tickets_com_lancamento": 0,
                    "tickets_sozinho": 0,
                    "tickets_com_incumbente_nicho": 0,
                    "share_sozinho": None,
                    "share_com_incumbente_nicho": None,
                }
            )
            continue
        alone = 0
        with_inc = 0
        for tid in tickets_with:
            skus = ticket_skus[tid]
            others = skus - {sku}
            if not others:
                alone += 1
            if others & inc_set:
                with_inc += 1
        n = len(tickets_with)
        rows.append(
            {
                "id_projeto": proj["id_projeto"],
                "cod_sku_lancamento": sku,
                "tickets_com_lancamento": n,
                "tickets_sozinho": alone,
                "tickets_com_incumbente_nicho": with_inc,
                "share_sozinho": alone / n,
                "share_com_incumbente_nicho": with_inc / n,
            }
        )
    return pd.DataFrame(rows)
