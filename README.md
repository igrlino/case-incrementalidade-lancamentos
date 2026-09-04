# Incrementalidade financeira de lançamentos

Case **Cientista de Dados Especialista II — Mensuração** (Grupo Boticário).  
Pasta autocontida: notebooks + dados + código + resultados.

## Comece aqui

1. `notebooks/01_eda.ipynb` — auditoria da base (desconto, ciclo, cadastro)
2. `notebooks/02_resultados.ipynb` — ATT, event study, ROI, gates
3. `docs/` — texto para a apresentação de 25 min

Enunciado: `docs/enunciado_case.docx`. Planilha: `data/Dados_Case_Especialista_II.xlsx`.

## Como abrir (quem recebeu o zip)

```bash
cd case
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

No Cursor/VS Code: selecione o kernel `.venv` e rode os notebooks **nesta pasta** (`notebooks/`).

Opcional — regenerar tabelas:

```bash
.venv/bin/python scripts/run_pipeline.py
```

## Árvore

```
case/
  README.md
  requirements.txt
  notebooks/           ← abrir estes
    01_eda.ipynb
    02_resultados.ipynb
  docs/                ← narrativa da apresentação
    01_eda.md
    02_metodologia.md
    03_roi_e_gates.md
    enunciado_case.docx
  data/
    Dados_Case_Especialista_II.xlsx
    csv/               ← tabelas pequenas para inspecionar no editor
    raw/               ← parquet gerado da planilha
  outputs/tables/      ← ROI, ATT, event study
  src/incrementality/  ← limpeza, causal, ROI
  scripts/run_pipeline.py
```

## Onde está cada número

| Pergunta | Abrir |
|---|---|
| Desconto nulo é zero? | `notebooks/01_eda.ipynb` |
| Ciclo `2024/01` → `202401` | `data/csv/ciclos_mapeados.csv` |
| ROI e gate por projeto | `outputs/tables/roi_projetos_resumo.csv` ou notebook 02 |
| ATT por nicho | `outputs/tables/att_nicho.csv` |
| Event study | `outputs/tables/event_study_gmv_medio.csv` |

Os `.md` não são a fonte dos números; são o texto. A fonte é o notebook (EDA) e os CSV em `outputs/tables/` (modelo).
