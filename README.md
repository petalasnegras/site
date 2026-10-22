# Pétalas Negras FC: site oficial

Site do **Pétalas Negras FC**, time de várzea de Guarulhos (SP), fundado em 2022.
Mostra jogos (com escalação, gols e fotos), elenco com perfis, calendário, ranking, história, manto oficial (venda pelo WhatsApp) e contato.

**Em uma frase:** os dados ficam em planilhas (`.csv`) em `dados/`; um app em Python (`devapp`) edita essas planilhas e regera as páginas HTML e os arquivos `.json`.

---

## 1. Como funciona

| Item | Descrição |
|---|---|
| Tipo | Site **estático** (HTML + CSS + JavaScript). Sem servidor, banco ou login. |
| Visual | Tema escuro, roxo do clube `#732d91`, fonte Archivo (Google Fonts). |
| Dados | `elenco.csv`, `jogos.csv`, `financas.csv` e arquivos `.json` em `dados/`. |
| Gerenciador | `devapp/devapp.py` (interface Tkinter) usa a biblioteca `devapp/site_petalas.py`. |
| Dependências | Nenhuma além do Python 3.8+ (Tkinter já vem com o Python na maioria dos sistemas). |

```
CSV (dados/)  ──►  site_petalas.py  ──►  HTML (trechos entre marcadores) + JSON
                        ▲
                   devapp.py (interface gráfica)
```

Páginas **"automáticas"** (o app reescreve só o trecho entre marcadores `<!-- X:INICIO --> ... <!-- X:FIM -->`):

| Página | Marcadores |
|---|---|
| `jogos.html` | `JOGOS` |
| `index.html` (destaque do jogo) | `PROXIMO` |
| `elenco.html` | `ELENCO` |
| `ranking.html` | `RANKING_ARTILHARIA`, `RANKING_ASSISTENCIAS`, `RANKING_JOGOS` (sufixos `_INICIO`/`_FIM`) |
| `calendario.html` | `TITULO_MES`, `CALENDARIO` (sufixos `_INICIO`/`_FIM`) |

⚠️ Nunca apague nem edite esses comentários, e não edite à mão o que está entre eles: será sobrescrito.

Páginas **dinâmicas no navegador:** `jogo.html?id=...` lê `dados/jogos.json` e `dados/jogadores.json`; `jogador.html?id=...` lê `dados/jogadores.json`.
Por usar `fetch()`, **essas duas precisam ser abertas por um servidor** (não funcionam com duplo clique em `file://`). O botão "Ver no Navegador" do app já sobe um servidor local em `http://localhost:8000`.

Páginas **fixas** (edite o HTML direto): `historia.html`, `loja.html`, `contato.html`, `404.html` e o restante de `index.html`.

---

## 2. Estrutura de pastas

```
site/
├── index.html, jogos.html, jogo.html, elenco.html, jogador.html,
│   calendario.html, ranking.html, historia.html, loja.html, contato.html, 404.html
├── css/estilo.css              Visual de todo o site
├── js/menu.js                  Menu do celular
├── dados/
│   ├── elenco.csv              Jogadores e comissão técnica
│   ├── jogos.csv               Jogos, escalação, gols, fotos
│   ├── jogadores.json, jogos.json   Gerados pelo app (lidos pelo site)
│   ├── calendarios/eventos_<mes>_<ano>.json   Um arquivo por mês
│   ├── treinos.json            Treinos e chamada (uso interno)
│   ├── financas.csv, mensalidades.json, config_mensalidade.json   Financeiro (uso interno)
├── devapp/
│   ├── devapp.py               Aplicativo de gestão (interface)
│   └── site_petalas.py         Biblioteca: lê/grava CSVs e gera HTML/JSON
└── imagens/                    (não versionada; precisa ficar ao lado dos HTMLs)
    ├── logo.jpeg, placeholder.svg
    ├── carrossel/              time.jpeg, aquecimento.jpeg, entrada.jpeg
    ├── jogadores/<nome>.jpeg   Foto do card (retrato 4:5)
    ├── perfil/<slug>/N.jpeg    Fotos "em ação" do jogador
    ├── jogos/<id-do-jogo>/N.jpeg   Fotos de cada jogo
    └── uniforme/               linha.jpeg, goleiro.jpeg
```

---

## 3. Uso no dia a dia

1. Rode `python devapp/devapp.py` e escolha a pasta do site (fica salva em `~/.petalas_gui.json`).
2. Use as abas:
   - **Elenco:** adicionar/editar/remover pessoas; botões `+1 jogo`, `+1 gol`, `+1 assistência`.
   - **Jogos:** adicionar jogo; definir placar, escalação e gols.
   - **Treinos & Presença:** criar treino e fazer a chamada (presente, ausente, justificado).
   - **Calendário:** abrir/criar o JSON do mês e cadastrar jogos e treinos.
   - **Ranking:** gera `ranking.html` a partir das estatísticas do elenco.
   - **Finanças / Mensalidades:** caixa e controle de pagamentos (marcar "pago" lança a entrada no caixa).
3. Com "Atualizar o site automaticamente" ligado, cada alteração já regrava os HTMLs e JSONs. Senão, clique em **Atualizar site agora**.
4. Confira no navegador ("Ver no Navegador") e publique os arquivos alterados.

Sem o app, dá para editar os `.csv` e rodar `python devapp/site_petalas.py --raiz .` (regera elenco, jogos e JSONs; **não** gera ranking nem calendário).

### Formatos importantes

- **jogos.csv** (separador `;`): `data;hora;adversario;local;placar;escalacao;reservas;fotos;substituicoes;gols`
  - Data `DD/MM/AAAA`; placar `2 x 1` (nosso primeiro).
  - Jogadores por nome ou camisa; quem não é do elenco: `Fulano (suporte)` ou `Fulano (suporte, Goleiro)`.
  - Substituição: `Quem entrou > Quem saiu 60'`. Gol: `Rulim 23' (ast. João Vitor)`; gol do adversário: `adv 40'`.
  - O id do jogo é `AAAA-MM-DD-adversario` e define a pasta de fotos `imagens/jogos/<id>/`.
- **elenco.csv**: `numero;nome;posicao;foto;jogos;gols;assistencias;idade;pe;altura;titulos;formacao;fotos_jogo`
  - Comissão técnica/staff: deixe `numero` e estatísticas vazios (posições: Técnico, Preparador, Auxiliar, Fotógrafo...).
  - Foto padrão: `<nome em minúsculas sem acento>.jpeg`. O id do perfil é o nome em minúsculas, sem acento, com `-` no lugar de espaço.
  - `titulos` separados por `|`.
- **Calendário** (`dados/calendarios/*.json`): `mes_ano`, `offset_dias_anteriores` (dias do mês anterior que aparecem na 1ª semana), `total_dias_mes` e `eventos` por dia (`tipo`: `jogo` ou `treino`).

### Tarefas manuais (sem app)

- **Telefone/WhatsApp:** `5511977890581` está escrito à mão em `contato.html`, `loja.html` e no rodapé de todas as páginas. Use buscar-e-substituir.
- **Preço e camisas:** edite os blocos `<li class="produto">` de `loja.html`.
- **Textos:** `historia.html`, `contato.html`, `index.html` (dentro de `<p>`).
- **Cores:** variáveis em `:root` no topo de `css/estilo.css`.
- **Novo item no menu:** o cabeçalho é repetido em todos os HTMLs; altere em todos.
- **Nova temporada:** atualizar ano no rodapé (`&copy; 2026`) e na loja; revisar estatísticas do elenco.

---

## 4. Problemas comuns

| Sintoma | Causa provável / solução |
|---|---|
| `jogo.html` ou `jogador.html` mostram "não encontrado" | Aberto sem servidor, ou `jogos.json`/`jogadores.json` desatualizados. Use o servidor local e clique em "Atualizar site agora". |
| Erro "não tem os marcadores" | Comentário `INICIO`/`FIM` apagado. Recoloque exatamente igual. |
| "não reconheci a posição" | Use uma posição conhecida (Goleiro, Zagueiro, Lateral, Volante, Meio-campista, Ponta, Centroavante, Técnico...). |
| Foto virou silhueta | Nome do arquivo não bate com o esperado (veja avisos no log do app). Use `.jpeg`, não `.jpg`. |
| Acentos quebrados no CSV | Salve como **CSV UTF-8**. |
| Jogo antigo ainda aparece como "Próximo" | Rode "Atualizar site agora" (o status só muda quando as páginas são regeradas). |

---

## 5. Melhorias necessárias

### Segurança e privacidade (prioridade alta)
- **Dados internos ficam públicos ao publicar a pasta `dados/`:** `financas.csv`, `mensalidades.json`, `treinos.json` e `config_mensalidade.json` ficariam acessíveis por URL. Mover os dados privados para fora da pasta publicada (ou publicar só `jogos.json`, `jogadores.json` e `calendarios/`).
- **Atletas menores de idade (17 anos):** idade, altura e fotos estão públicas. Confirmar autorização dos responsáveis (LGPD) e considerar remover a idade do site.

### Bugs no `devapp.py` e `site_petalas.py`
- O botão **"Gerar Zip"** nunca aparece: o código procura `gerar_backup_zip`, mas o método se chama `fazer_backup`.
- Cards do dashboard: `recarregar_listas` testa `atualizar_cards_dashboard` (sem `_`), então o dashboard não atualiza sozinho após alterações; `lbl_artilheiro`, `lbl_assistencias` e `lbl_indicadores` nunca são criados (o código está morto).
- `marcar_todos_pendente` existe, mas não há botão para ela.
- Linha com erro de digitação: `ttk.Button(barra_batoroes := barra_botoes, ...)`. Funciona, mas deve virar `barra_botoes`.
- Janela abre sempre em tela cheia (`fullscreen`), sem como sair facilmente. Remover ou tornar opcional.
- Tipo financeiro grafado **`recebita`** (deveria ser `receita`) no código e nos dados; migrar com cuidado.
- `financas.csv` tem cabeçalho diferente do código (`origem_destino` não é usado). Padronizar as colunas.
- Em `calcular_porcentagem_presenca` a variável `slug` sobrescreve a função `slug()` (só dentro do método, mas confunde); comentário "Presaças"; `pop_item` não usado; imports não usados (`Iterable`).
- A mensalidade tem um único status por atleta, sem mês de referência, e voltar para "pendente" não estorna o lançamento no caixa. Controlar por mês.
- Chamada de treino: quem não está na lista conta como ausente por padrão (o comentário diz o contrário).

### Dados e regras de negócio
- **Jogos, gols e assistências do elenco são lançados à mão** e já divergem dos dados de `jogos.csv` (escalação/gols). Calcular as estatísticas a partir dos jogos.
- Três dos quatro jogos "realizados" estão **sem placar**.
- O **calendário é separado** de `jogos.csv` e de `treinos.json` (digitar o mesmo evento duas ou três vezes). Gerar o calendário a partir dos jogos e treinos.
- Calendário permite só **um evento por dia**, e o deslocamento do início do mês é informado à mão (calcular pela data).
- Status "Próximo/Realizado" é estático em `jogos.html` e `index.html`, mas calculado no navegador em `jogo.html`. Unificar, por exemplo com um agendamento diário que regera o site.
- Treinos e presença não aparecem no site; decidir se devem aparecer.

### Código do site
- **Cabeçalho, menu e rodapé repetidos em 11 HTMLs** (e a ordem do menu já diverge em `ranking.html`). Gerar as páginas a partir de um modelo (template) ou usar um gerador estático.
- CSS duplicado: carrossel e perfil estão em `jogo.html` e `jogador.html` (inline) e `fatos-grid`/`bloco-titulos` também em `estilo.css`. Centralizar em `estilo.css`.
- JavaScript do carrossel duplicado em duas páginas; extrair para `js/carrossel.js`.
- Telefone de WhatsApp espalhado em todos os arquivos; centralizar em um só lugar (variável do gerador).
- `jogo.html` pré-carrega **todas** as fotos do jogo (até 19-20) para ver quais existem. Informar só as existentes no JSON e usar miniaturas/`loading="lazy"`.
- Imagens sem otimização (ideal abaixo de ~300 KB). Gerar versões redimensionadas (`webp`).
- Falta `<meta>` Open Graph (prévia ao compartilhar no WhatsApp), `sitemap.xml` e `robots.txt`.

### Projeto em geral
- **Ausência de testes automatizados** para o parsing de jogos, gols e escalação (parte mais frágil da biblioteca).
- Sem `requirements`/instruções de instalação, sem CI e sem publicação automática (ex.: GitHub Actions + GitHub Pages).
- Sem backup agendado (o botão de zip está quebrado) e sem pasta separada para dados privados.
- `devapp.py` concentra interface, ranking e calendário em um único arquivo longo; separar em módulos.
- Imagens não são versionadas: documentar onde ficam o backup e a fonte das fotos.
- `.gitignore` só ignora `__pycache__/`; incluir arquivos de dados privados, backups `.zip` e `.petalas_gui.json`.
