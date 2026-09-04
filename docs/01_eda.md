# 01 — EDA e auditoria da base

Fonte exclusiva: `processo/Dados_Case_Especialista_II.xlsx`. Nenhum valor de negócio foi imputado.

## Universo

| Tabela | Linhas | Papel |
|---|---|---|
| `tb_produtos_atributos` | 150 SKUs | Cadastro, preço, margem, phase-in/out |
| `tb_projetos_lancamento` | 25 projetos | SKU inovador, mídia, GMV esperado ano 1 |
| `tb_skus_similares` | 285 pares | Score de similaridade (0,60–0,98) |
| `tb_vendas` | 519.976 linhas / 152.478 tickets | GMV, desconto, margem, UF, canal |

Painel: ciclos `202401`–`202609` (43 ciclos, depois de unificar a barra). Dicionário declarava `202401`–`202606`. Geografia: SP e PR. Canais: VD e Loja.

## Desconto nulo — a conta, sem atalho

`vlr_venda_desconto` está vazio em **334.570 linhas (64,3%)**. Não existe `0` explícito na coluna: o arquivo usa célula vazia para “sem desconto”.

Teste **antes** de preencher nulo (é isso que justifica tratar como zero):

| Recorte | N | Conta | Máximo do erro absoluto |
|---|---|---|---|
| Desconto nulo | 334.570 | `praticado − tabela` | **0,0 em todas as linhas** |
| Desconto preenchido (> 0) | 185.406 | `praticado − (tabela − desconto)` | 9,1×10⁻¹³ (ponto flutuante) |
| Desconto `< 0` | 0 | — | — |

Conclusão: nulo **é** zero nesta base. Preencher com 0 não inventa desconto; só torna a coluna numérica. A identidade do dicionário (`praticado = tabela − desconto`) vale nos dois recortes.

Isso **não** é o mesmo erro do ciclo: ciclo com barra (`2024/01`) era texto que o `to_numeric` derrubava; desconto nulo é célula realmente vazia cuja conta fecha.

## Equívocos de limpeza (mesmo tipo: texto que o pandas não lê)

Tudo abaixo estava **no xlsx**. A primeira passagem com `pd.to_numeric(..., errors="coerce")` apagou.

| Campo | O que o arquivo tem | O que a 1ª limpeza fez | Correção |
|---|---|---|---|
| `tb_vendas.cod_ciclo` | `202401` **e** `2024/01` (2.651 linhas) | Barra → NaN (falso “ciclo nulo”) | Tirar `/`. 0 nulos. 43 ciclos. |
| `tb_produtos.cod_ciclo_phase_in` | 3 SKUs com barra: `SKU_023` `2022/04`, `SKU_088` `2024/08`, `SKU_128` `2024/07` | Phase-in nulo → ficaram fora de incumbente **e** de “outra inovação” | Mesmo parser do ciclo |
| `tb_produtos.preco_regular` | 3 SKUs com vírgula decimal: `SKU_010` `31,34`, `SKU_074` `244,15`, `SKU_150` `295,6` | Classificados como “preço ausente” | Trocar `,` por `.` só quando não há ponto |

Os três SKUs de phase-in com barra são Eudora Óleo Corporal (célula **doadora**, sem projeto). `SKU_023` é incumbente (2022); `SKU_088` e `SKU_128` são inovação não rotulada (2024). Sem o parser, o sintético perdia um incumbente doador. Depois da correção: **66 incumbentes, 59 outras inovações, 25 projetos** (150).

Lista conferível: `data/csv/ciclos_tb_vendas.csv` (texto bruto), `data/csv/ciclos_mapeados.csv` (bruto → normalizado), `data/csv/ciclos_normalizados.csv` (43 ciclos).

Não há outro campo numérico das vendas com `/` ou `,`. `phase_out` não tem barra.

## Outras correções (cadastro, não parser)

1. **Marca** — `eudora` / `o boticário` em 3 SKUs. Sem padronizar, o nicho (marca × subcategoria) parte ao meio.
2. **Canal** — `vd`/`loja` vs `VD`/`LOJA`. Uppercase.
3. **`id_venda` não é PK** — cesta (média 3,4 itens). Chave da linha: `id_venda + cod_sku`. Tickets consistentes em ciclo, UF e canal.

## O que a base tem e o dicionário simplifica

### Calendário de ciclo

Não é YYYYMM gregoriano. Existem `202413`–`202417` e `2024/13`–`2024/17` (texto, coluna C; visível ~linha 130018). O cadastro de produto, com o parser, usa 01–12 (os três com barra viram 202204/202407/202408). O dicionário para em 202606; a série vai a 202609.

**Decisão:** unificar a barra e ordenar 01–17 por ano. Não é um modelo de calendário sofisticado.

### Campo fantasma

O dicionário lista `score_similaridade` em `tb_produtos_atributos`. A tabela não tem a coluna. Não foi reconstruída.

### Score de par nulo

50 pares em `tb_skus_similares` sem `score_similaridade_par`. Não imputamos. Só entram na robustez se score ≥ 0,70, mesma subcategoria e similar incumbente (15/285).

### SKU morto na malha

`SKU_036` (Eudora Óleo Corporal) tem `phase_out = 202312`, zero vendas no painel, e aparece como similar de `SKU_120` com score 0,97.

## Qualidade financeira (depois dos parsers)

- `tabela = preco_regular × qt_venda`: 0 erros > R$ 0,05 (os 3 preços com vírgula agora entram na conta).
- `praticado = tabela − desconto` (nulo = 0): ver tabela do desconto.
- `margem_bruta ≈ praticado × margem_bruta_pct`: erro máximo R$ 0,005 (arredondamento). **Não** é `tabela × %` — nas 185.406 linhas com desconto a margem segue o praticado, não a tabela.
- Devoluções: 4.185 linhas com `qt_venda` negativo (dicionário prevê). Mantidas.
- Nenhuma venda antes do phase-in nem depois do phase-out (com phase-in já parseado).

## Achados que mudam a metodologia

1. A malha de similares não é mapa de canibalização (13/25 projetos sem pares; 15/285 pares usáveis).
2. SUTVA no SKU quebrada: 20/25 projetos compartilham nicho.
3. 59 SKUs nascem no painel fora da tabela de projetos (inovação não rotulada).
4. 66 incumbentes (phase-in &lt; 202401, não projeto) são o objeto do contrafactual.
5. Eudora Colônia Infantil: zero incumbentes — deslocamento não identificável.
6. `SKU_085` (maior GMV, único acima da expectativa bruta) nasce em 202401: sem pré-período.
7. Ano do `id_projeto` ≠ data de lançamento (`PROJ_2025_12` entra em 202404).
8. GMV observado vs `expectativa_gmv_ano1` é descritivo, não causal.

## Composição do portfólio (após parsers)

| Papel | N | Regra |
|---|---|---|
| Projeto | 25 | `tb_projetos_lancamento` |
| Incumbente | 66 | phase-in &lt; 202401 e não é projeto |
| Outra inovação | 59 | phase-in ≥ 202401 e não é projeto |
| Sem venda | 1 | `SKU_036`, phase-out pré-painel |

Doadoras (nenhum projeto na célula): Óleo Corporal (ambas as marcas) e, no Boticário, Colônia Infantil, Condicionador, Hidratante, Perfume Masculino, Shampoo, Sérum.
