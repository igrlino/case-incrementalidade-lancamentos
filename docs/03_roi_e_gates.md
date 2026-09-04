# 03 — ROI incremental e Gates de lançamento

## Equação proposta para o negócio

Variáveis **observadas no case**:

- `MB_direto` — margem bruta do SKU de lançamento (vendas)
- `ΔMB_incumbentes` — ATT sintético da base regular do nicho (estimado)
- `I_midia` — `investimento_mkt_rs`

Variáveis **necessárias para um parâmetro oficial e ausentes na base** — entram como parâmetros, default zero = “não informado”, nunca imputadas:

- `C_pd` — P&D, tooling, registro, prototipagem
- `C_estoque` — write-off / transição de estoque da base canibalizada e do próprio phase-out
- `C_sustentacao` — mídia de continuidade além do investimento de lançamento
- `C_oportunidade` — capacidade fabril/logística deslocada
- `T` — impostos e taxas não capturados na margem bruta teórica do cadastro

```
MB_inc = MB_direto + ΔMB_incumbentes

ROI_parcial = (MB_inc − I_midia) / I_midia
ROI_full    = (MB_inc − I_midia − C_pd − C_estoque − C_sustentacao − C_oportunidade)
              / (I_midia + C_pd + C_estoque + C_sustentacao + C_oportunidade)
```

`ROI_parcial` é o que esta base permite calcular. `ROI_full` é o contrato do indicador oficial: o time de portfólio preenche os C_* no gate, ciência de dados não inventa.

GMV incremental é métrica de **saúde comercial**, não de retorno. Um lançamento pode ter GMV_inc > 0 e MB_inc < 0 (destrói mix). Por isso o gate olha margem primeiro.

## Como o número volta para o comitê

Não usar “bateu a expectativa de GMV” como go/kill. A expectativa é uma âncora de planejamento, não um contrafactual.

| Gate | Regra | Uso no comitê |
|---|---|---|
| `VALUE_CREATOR` | Janela ≥ 6 ciclos, MB_inc identificado, MB_inc > 0 e ROI_parcial > 0 | Candidato a escala / replay da plataforma |
| `ABAIXO_HURDLE` | MB_inc > 0 mas não paga a mídia observada | Segue com redesign de investimento ou preço, não com “sucesso de sell-out” |
| `MIX_DESTROYER` | GMV_inc > 0 e MB_inc ≤ 0 | Recusa ou reposicionamento; mix piorou |
| `CANNIBAL` | GMV_inc ≤ 0 | Não escala; revisar similaridade real vs brief |
| `INCONCLUSIVO_IDENTIFICACAO` | Sem pré, sem incumbente, ou ajuste pré fraco | Não mata o projeto por ausência de prova; também não celebra GMV bruto |
| `INCONCLUSIVO_JANELA` | < 6 ciclos de exposição | Esperar; não anualizar run-rate como se fosse ano 1 |

Alerta adicional: janela < 12 ciclos (`alerta_janela_curta`). `VALUE_CREATOR` com 9 ciclos é provisório.

## Leitura dos resultados nesta base

Entre os 18 projetos com ATT estimável (ciclo unificado; 0 nulos; 43 ciclos; phase-in e preço do cadastro parseados):

- GMV incremental ~ R$ 7,12 mi.
- MB incremental ~ R$ 4,26 mi contra R$ 13,10 mi de mídia desses 18 → payback parcial ~ **− R$ 8,84 mi**.
- 2 `VALUE_CREATOR`, 16 `ABAIXO_HURDLE`, 0 canibal na especificação indexada.
- 7 projetos ficam inconclusivos, inclusive o de maior GMV (`SKU_085`) e o segundo (`SKU_119`).

Placebos: nem todo ATT grande é distinguível de ruído. Eudora Perfume Masculino tem ATT de incumbentes positivo e p-valor 0,75 — não vender como “expansão comprovada”. Condicionador Eudora e Sabonete Boticário têm p = 0 contra os 8 doadores; ainda assim o ROI de quase todos permanece negativo porque a mídia é grande frente à margem incremental.

## Retroalimentação dos Gates (processo, não só métrica)

1. **Gate de conceito (pré-P&D):** nicho já tem projeto sobreposto? Se sim, o comitê aprova um *stream* de inovação, não um SKU isolado. Ciência de dados avisa que o SKU não terá efeito isolável.
2. **Gate de investimento:** exigir `ROI_full` com C_pd e C_estoque preenchidos pelo funcional. Sem isso, só publicamos `ROI_parcial` com selo “incompleto”.
3. **Gate de go-to-market:** reserva de 4+ ciclos de pré da base regular **antes** do T0 — senão o lançamento nasce cego (caso Shampoo Eudora).
4. **Gate de scale (pós 12–17 ciclos):** classificação da tabela acima. `ABAIXO_HURDLE` não é kill automático: é “o produto gera margem incremental, o spend não se paga”. A alavanca é mídia/preço, não só descontinuar o SKU.
5. **Sunset:** 5 projetos já têm phase-out no cadastro. O indicador oficial deve parar no phase-out e incluir `C_estoque` do encerramento.

## O que não entra na conta (de propósito)

- Run-rate × 17 ciclos como substituto de ano 1.
- P&D “típico do setor” inventado.
- Extra-polação Brasil a partir de SP/PR.
- Uso da malha de similares sem filtro.
