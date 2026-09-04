# 02 — Metodologia: Pilha Causal de Incrementalidade

Pergunta do case: isolar o ganho incremental real (GMV e margem bruta) dos lançamentos, não o faturamento do SKU novo.

## 1. Identidade (contábil, inegociável)

```
GMV_inc(L) = GMV_direto(L) + ΔGMV_incumbentes(nicho(L))
MB_inc(L)  = MB_direto(L)  + ΔMB_incumbentes(nicho(L))
```

- `GMV_direto` e `MB_direto` são **observados**. Não se modela o SKU novo: ele não tem pré-período.
- O que precisa de contrafactual é a **base regular do nicho** (66 incumbentes). Canibalização é incumbente abaixo do sintético; halo/expansão é incumbente acima.

Isso é o oposto do atalho comum “queda dos similares depois do lançamento”.

## 2. Por que os atalhos comuns falham nesta base

| Atalho | Por que cai |
|---|---|
| GMV do lançamento vs `expectativa_gmv_ano1` | Ignora deslocamento; janelas de exposição desiguais; expectativa não é contrafactual |
| Antes/depois dos SKUs similares | 13 projetos sem lista; pares cruzam categoria; inclui SKU phase-out; sem controle de tendência |
| DiD SKU a SKU | 20/25 projetos dividem nicho (SUTVA quebrada); TWFE com tratamento escalonado é viesado (Goodman-Bacon) |
| “Resto da categoria” como controle | 59 inovações não rotuladas + outros projetos no mesmo nicho |

## 3. Unidade de identificação

**Célula de concorrência** = `marca_std × subcategoria`.

Tratamento da célula = primeiro ciclo com projeto ativo. O efeito identificado é o da **entrada de inovação naquele nicho** sobre a base regular — não o efeito isolado de um SKU quando há vários projetos no mesmo nicho.

Quando há um único projeto no nicho, célula = SKU. Quando há vários, a alocação do Δ entre projetos é **contábil** (peso = GMV direto do projeto no pós), declarada como tal. Não fingimos causalidade no SKU.

## 4. Controle sintético na trajetória (Abadie, indexado)

Doadores: células **nunca tratadas** (nenhum projeto na tabela) e com incumbente.

Ajuste **não** é feito em R$ absoluto. Nichos têm escalas diferentes; pesos no nível fazem o sintético herdar o tamanho do doador e fabricam canibalização. Diagnóstico da primeira especificação: sintético 7–16× o nível pré de nichos pequenos.

Especificação adotada:

1. Indexa cada série pela média do pré-período da própria série.
2. Estima pesos `w ≥ 0`, `Σw = 1`, minimizando o erro quadrático no índice pré (SLSQP).
3. Reconstrói o contrafactual em R$ = índice sintético × média pré do tratado.
4. `ATT_soma` = Σ (observado − sintético) nos ciclos pós.

Travas de validade (não estimamos se falhar):

- ≥ 4 ciclos de pré no painel.
- ≥ 1 incumbente no nicho.
- RMSPE pré / |média pré| ≤ 0,35.

Inferência: placebos no espaço (Abadie) — cada doador recebe o mesmo T0; p-valor = fração de placebos com razão RMSPE pós/pré ≥ a do tratado. Sem p-valor de OLS fingindo randomização.

## 5. Event study

Séries alinhadas em tempo de evento `t − T0`, janela −8 a +12, só células que passaram nas travas. O pré deve oscilar em torno de zero se o índice colou. É o gráfico executivo da identificação.

## 6. Triangulação via cesta (mecanismo, não causal)

Ticket com o lançamento: fração sozinho vs fração com incumbente do mesmo nicho. Sem aleatorização, isso descreve substituição na mesma viagem vs complemento. Não entra no ROI.

## 7. O que a malha de similares ainda faz

Só robustez, depois de filtros: mesma subcategoria, similar incumbente (não morto, não projeto, não inovação tardia), score ≥ 0,70. Score nulo **não é imputado**.

## 8. Limitações que o comitê precisa ouvir

- Sem pré-período: Eudora Shampoo (inclui o maior GMV do case) e Boticário Perfume Feminino. Não há ATT. Reportamos GMV/MB diretos e marcamos `INCONCLUSIVO_IDENTIFICACAO`.
- Eudora Colônia Infantil: zero incumbentes. Deslocamento da base regular não identificável.
- Painel só SP/PR. Não é Brasil.
- 17 ciclos/ano é o que a série de vendas mostra, não o dicionário. Unificar `2024/01` → `202401` é a única recodificação. `phase_in` do cadastro teve o mesmo parser (3 SKUs de Óleo Corporal Eudora).
- Outras inovações (59) foram retiradas do desfecho para não misturar projetos oficiais com lançamentos não rotulados. Se o negócio quiser “toda inovação”, é outro recorte — e precisa da lista completa, que esta tabela de projetos não é.
