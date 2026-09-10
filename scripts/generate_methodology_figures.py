"""Gera as figuras do relatório metodológico a partir dos outputs do pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = ROOT / "docs" / "figures"

COLORS = {
    "blue": "#2F5D8A",
    "green": "#2E7D5B",
    "orange": "#C45C26",
    "red": "#A33A3A",
    "gray": "#5F6B7A",
    "light": "#D9E2EC",
}


def brl(value: float, _position: float | None = None) -> str:
    sign = "−" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{sign}R$ {absolute / 1_000_000:.1f} mi"
    if absolute >= 1_000:
        return f"{sign}R$ {absolute / 1_000:.0f} mil"
    return f"{sign}R$ {absolute:.0f}"


def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIGURES / name, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def configure() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "regular",
        }
    )


def event_study() -> None:
    event = pd.read_csv(TABLES / "event_study_gmv_medio.csv")
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 6.6), sharex=True)

    axes[0].plot(
        event["event_time"],
        event["observado"],
        marker="o",
        color=COLORS["blue"],
        label="Base antiga observada",
    )
    axes[0].plot(
        event["event_time"],
        event["sintetico"],
        marker="o",
        color=COLORS["gray"],
        linestyle="--",
        label="Contrafactual sintético",
    )
    axes[0].axvline(0, color=COLORS["orange"], linewidth=1.2)
    axes[0].set_ylabel("Valor bruto de mercadoria médio por célula (R$)")
    axes[0].set_title("Trajetória média das 10 células com estimativa calculável")
    axes[0].yaxis.set_major_formatter(FuncFormatter(brl))
    axes[0].legend(frameon=False)

    axes[1].bar(
        event["event_time"],
        event["gap"],
        color=np.where(event["gap"] >= 0, COLORS["green"], COLORS["red"]),
        width=0.75,
    )
    axes[1].axhline(0, color=COLORS["gray"], linewidth=0.8)
    axes[1].axvline(0, color=COLORS["orange"], linewidth=1.2)
    axes[1].set_xlabel("Ciclos em relação ao primeiro lançamento (0 = lançamento)")
    axes[1].set_ylabel("Observado menos sintético (R$)")
    axes[1].set_title("Diferença média ciclo a ciclo")
    axes[1].yaxis.set_major_formatter(FuncFormatter(brl))
    save(fig, "01_estudo_de_evento_medio.png")


def mirror_weights() -> None:
    records = json.loads((OUTPUTS / "att_pesos.json").read_text(encoding="utf-8"))
    record = next(
        row
        for row in records
        if row["marca_std"] == "Eudora"
        and row["subcategoria"] == "Perfume Masculino"
        and row["faixa_preco"] == "P1"
    )
    weights = pd.Series(record["pesos"]).sort_values()
    labels = [label.replace("|", " · ") for label in weights.index]

    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.barh(labels, weights.values, color=COLORS["blue"], height=0.62)
    ax.set_xlabel("Peso na combinação convexa")
    ax.set_title("Composição do espelho: Eudora · Perfume Masculino · P1")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    for index, value in enumerate(weights.values):
        ax.text(value + 0.006, index, f"{value:.0%}", va="center", color=COLORS["gray"])
    ax.set_xlim(0, max(weights.max() * 1.23, 0.35))
    save(fig, "02_pesos_espelho_exemplo.png")


def fit_and_placebo() -> None:
    att = pd.read_csv(TABLES / "att_celulas.csv")
    att = att[(att["metric"] == "gmv") & (att["status"] == "ok")].copy()
    att["label"] = (
        att["marca_std"].str.replace("O Boticário", "Boticário", regex=False)
        + " · "
        + att["subcategoria"]
        + " · "
        + att["faixa_preco"]
    )
    att = att.sort_values("placebo_pvalue_rmspe_ratio", ascending=True)

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 6.0), sharey=True)
    axes[0].barh(att["label"], att["fit_rel_pre"], color=COLORS["blue"], height=0.58)
    axes[0].axvline(0.30, color=COLORS["red"], linestyle="--", label="Teto operacional: 30%")
    axes[0].set_xlabel("Erro prévio relativo à média")
    axes[0].set_title("Qualidade do ajuste antes do lançamento")
    axes[0].xaxis.set_major_formatter(PercentFormatter(1.0))
    axes[0].legend(frameon=False, fontsize=8)

    axes[1].barh(
        att["label"],
        att["placebo_pvalue_rmspe_ratio"],
        color=COLORS["gray"],
        height=0.58,
    )
    axes[1].axvline(0.10, color=COLORS["orange"], linestyle="--", label="Referência descritiva: 10%")
    axes[1].set_xlabel("Fração dos placebos tão extremos quanto o tratado")
    axes[1].set_title("Diagnóstico de placebo no espaço")
    axes[1].xaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].legend(frameon=False, fontsize=8)
    save(fig, "03_ajuste_previo_e_placebos.png")


def coverage_and_seals() -> None:
    roi = pd.read_csv(TABLES / "roi_projetos_resumo.csv")
    counts = roi["selo"].value_counts().sort_values()
    colors = [
        COLORS["blue"] if label == "Ano 1 incompleto" else COLORS["gray"]
        for label in counts.index
    ]

    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.barh(counts.index, counts.values, color=colors, height=0.58)
    ax.set_xlabel("Número de projetos")
    ax.set_title("Cobertura da mensuração e resultado do selo operacional")
    ax.set_xlim(0, counts.max() + 2)
    for index, value in enumerate(counts.values):
        ax.text(value + 0.15, index, str(int(value)), va="center", color=COLORS["gray"])
    save(fig, "04_distribuicao_selos.png")


def roi_decision() -> None:
    roi = pd.read_csv(TABLES / "roi_projetos_resumo.csv")
    estimable = roi[roi["mb_incremental"].notna()].copy()
    complete = estimable["n_post_roi"].eq(17)
    colors = np.where(complete, COLORS["orange"], COLORS["blue"])
    maximum = float(
        max(estimable["investimento_mkt_rs"].max(), estimable["mb_incremental"].max())
    )

    fig, ax = plt.subplots(figsize=(8.2, 6.2))
    ax.scatter(
        estimable["investimento_mkt_rs"],
        estimable["mb_incremental"],
        c=colors,
        s=64,
        zorder=3,
    )
    ax.plot([0, maximum], [0, maximum], color=COLORS["gray"], linestyle="--")
    for _, row in estimable.iterrows():
        ax.annotate(
            row["cod_sku_lancamento"],
            (row["investimento_mkt_rs"], row["mb_incremental"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_xlabel("Investimento observado em mídia (R$)")
    ax.set_ylabel("Margem bruta incremental estimada (R$)")
    ax.set_title("Decisão econômica: margem incremental versus mídia")
    ax.xaxis.set_major_formatter(FuncFormatter(brl))
    ax.yaxis.set_major_formatter(FuncFormatter(brl))
    ax.text(
        maximum * 0.58,
        maximum * 0.77,
        "Acima da diagonal:\npaga a mídia",
        color=COLORS["green"],
        ha="center",
    )
    ax.scatter([], [], color=COLORS["orange"], label="Janela completa: 17 ciclos")
    ax.scatter([], [], color=COLORS["blue"], label="Ano 1 incompleto")
    ax.legend(frameon=False)
    save(fig, "05_margem_incremental_versus_midia.png")


def worked_example() -> None:
    roi = pd.read_csv(TABLES / "roi_projetos_resumo.csv")
    row = roi.loc[roi["cod_sku_lancamento"] == "SKU_120"].iloc[0]
    labels = [
        "Margem do\nlançamento",
        "Efeito na\nbase antiga",
        "Margem\nincremental",
        "Mídia",
        "Payback",
    ]
    values = [
        row["mb"],
        row["mb_spillover_alocado"],
        row["mb_incremental"],
        row["investimento_mkt_rs"],
        row["payback_parcial_midia"],
    ]
    colors = [
        COLORS["blue"],
        COLORS["green"] if values[1] >= 0 else COLORS["red"],
        COLORS["green"],
        COLORS["orange"],
        COLORS["green"] if values[4] >= 0 else COLORS["red"],
    ]

    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(labels, values, color=colors, width=0.62)
    ax.axhline(0, color=COLORS["gray"], linewidth=0.8)
    ax.set_ylabel("Valor em reais")
    ax.set_title("Exemplo completo: SKU_120, janela de 17 ciclos")
    ax.yaxis.set_major_formatter(FuncFormatter(brl))
    for index, value in enumerate(values):
        vertical = "bottom" if value >= 0 else "top"
        offset = 6_000 if value >= 0 else -6_000
        ax.text(index, value + offset, brl(value), ha="center", va=vertical, fontsize=8)
    save(fig, "06_exemplo_roi_sku_120.png")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    configure()
    event_study()
    mirror_weights()
    fit_and_placebo()
    coverage_and_seals()
    roi_decision()
    worked_example()
    print(f"Figuras geradas em {FIGURES}")


if __name__ == "__main__":
    main()
