# Incrementalidade financeira de lançamentos

Case **Cientista de Dados Especialista II — Mensuração** (Grupo Boticário).

Repositório: [github.com/igrlino/case-incrementalidade-lancamentos](https://github.com/igrlino/case-incrementalidade-lancamentos)

A venda do produto novo é ganho de verdade para a empresa, ou só troca com o que já estava na prateleira?

## Comece aqui

| Artefato | Conteúdo |
|---|---|
| [Relatório metodológico (PDF)](<docs/Relatório Metodológico_ mensuração da incrementalidade financeira de lançamentos.pdf>) | Negócio, método, resultados e limitações |
| [`notebooks/analise_incrementalidade.ipynb`](notebooks/analise_incrementalidade.ipynb) | Análise executiva reproduzível: metodologia, ROI e decisão |
| [`outputs/tables/painel_comite.csv`](outputs/tables/painel_comite.csv) | Painel de decisão por lançamento |
| [`docs/figures/`](docs/figures/) | Figuras do relatório (event study, espelhos, selos, ROI) |
| [`docs/enunciado_case.docx`](docs/enunciado_case.docx) | Brief do processo |

Célula = `marca` × `subcategoria` × `faixa_preco`. Recorte geográfico da base: SP e PR.

## Entrega do case

| Pergunta do enunciado | Onde está |
|---|---|
| Abordagem metodológica (código + análises) | Repositório, notebook e relatório PDF |
| Formulação do ROI incremental | Relatório PDF (seção 12) e notebook (seção 2) |
| Aplicação prática e gates de lançamento | Relatório PDF (seções 13–15), `painel_comite.csv` e notebook (seção 3) |

## Ambiente e execução

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Kernel do notebook: `.venv`.

Recalcular tabelas e o painel do comitê:

```bash
python scripts/run_pipeline.py
```

Regenerar figuras do relatório metodológico:

```bash
python scripts/generate_methodology_figures.py
```

O pipeline lê a planilha em `data/`, estima controle sintético e ATT, calcula ROI e selos, e grava `outputs/`.

## Mapa do código

| Arquivo | Responsabilidade |
|---|---|
| `src/incrementality/prepare.py` | Leitura, padronização de ciclos, números e auditoria |
| `src/incrementality/config.py` | Parâmetros: célula, pré mínimo, ajuste máximo, janelas e cortes |
| `src/incrementality/model.py` | Painel, doadoras, pesos, sintético, ATT, placebo, alocação e cesta |
| `src/incrementality/roi.py` | Margem incremental, retorno, selos e `build_painel_comite()` |
| `scripts/run_pipeline.py` | Orquestração e gravação das tabelas |
| `scripts/generate_methodology_figures.py` | Figuras do relatório em `docs/figures/` |

## Principais saídas

| Saída | Conteúdo |
|---|---|
| `outputs/tables/painel_comite.csv` | Painel de decisão: ROI + diagnóstico do espelho por projeto |
| `outputs/tables/roi_projetos_resumo.csv` | ROI e selo (colunas essenciais) |
| `outputs/tables/att_celulas.csv` | Diagnósticos e efeitos por célula e métrica |
| `outputs/tables/event_study_gmv.csv` | Trajetórias por célula e tempo de evento |
| `outputs/headline.json` | Indicadores agregados |
| `outputs/eda_audit.json` | Auditoria da preparação |
| `outputs/att_pesos.json` | Pesos dos espelhos de GMV |

## Pseudocódigo do pipeline

```text
carregar e limpar cadastro, projetos, similares e vendas
classificar produtos em projeto, incumbente e outra inovação
definir célula = marca × subcategoria × faixa de preço

para cada métrica em {GMV, margem bruta}:
    agregar vendas dos incumbentes por célula e ciclo
    definir células tratadas, T0 e doadoras sem projeto

    para cada célula tratada:
        verificar incumbente, histórico anterior e período posterior
        ajustar espelho no pré (pesos ≥ 0, soma = 1)
        se erro pré > 30%: marcar ajuste fraco
        senão: ATT = soma(observado − sintético) na janela W; placebos

para cada projeto:
    somar sell-out e margem em W
    alocar ATT da célula pelo GMV do projeto
    calcular ROI parcial e selo

gravar painel_comite, demais tabelas e headline
```

## Glossário

| Termo | Definição |
|---|---|
| ATT | Efeito na base antiga da célula: soma de (observado − sintético) em W |
| Base antiga | Incumbentes da célula (produtos antigos na mesma marca × subcategoria × faixa) |
| Célula | `marca` × `subcategoria` × `faixa_preco` |
| Contrafactual / espelho | Trajetória que a base antiga teria sem o lançamento (controle sintético) |
| Doadora | Célula com incumbente e sem projeto oficial — candidata a espelho |
| GMV incremental | Sell-out do novo em W + ATT alocado em GMV |
| MB incremental | Margem do novo em W + ATT alocado em margem |
| Placebo | Mesmo T0 em células sem lançamento; diagnóstico de evidência |
| Projeto | SKU da tabela oficial de lançamentos (25 no case) |
| Selo | Veredito operacional (mensurabilidade, janela, economia) |
| W | Janela econômica: min(17 ciclos, vida do incumbente após T0, fim da amostra) |

## Dados

| Pasta / arquivo | Conteúdo |
|---|---|
| `data/Dados_Case_Especialista_II.xlsx` | Planilha original (~520 mil linhas) |
| `data/raw/` | Parquet gerado na leitura |
| `data/csv/` | Recortes e amostras para auditoria |
