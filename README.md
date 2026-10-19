# Pétalas Negras FC: site

Site estático: é só abrir o `index.html` no navegador (ou publicar a pasta em qualquer hospedagem). Não precisa de servidor.

## Estrutura de pastas

```
index.html, jogos.html, elenco.html, historia.html, loja.html, contato.html, 404.html
css/estilo.css
js/menu.js
imagens/            logo.jpeg, carrossel/, jogadores/, uniforme/
dados/              o "banco de dados" e os scripts que atualizam o site
  jogos.csv
  elenco.csv
  atualizar_jogos.py
  atualizar_elenco.py
```

Os scripts ficam em `dados/` junto com os `.csv`, mas reescrevem as páginas da pasta de cima. Rode a partir da pasta do site (ou de dentro de `dados/`, tanto faz).

## Atualizar os jogos

Os jogos ficam em `dados/jogos.csv`, que pode ser editado no bloco de notas ou no Excel:

```
data;hora;adversario;local;placar
17/10/2026;10:00;Adversário a confirmar;Rua tal, 123;
```

Depois rode (precisa do Python 3):

```bash
python dados/atualizar_jogos.py
```

O script reescreve a lista em `jogos.html` e o destaque de "Próximo jogo" em `index.html`. Um jogo é "Próximo" até o dia passar e depois vira "Realizado" sozinho (rode o script de novo para o site refletir isso). O placar é opcional, por exemplo `2 x 1`.

Para adicionar um jogo sem abrir o arquivo:

```bash
python dados/atualizar_jogos.py --novo
```

Ele pergunta data, horário, adversário, local e placar, salva no `jogos.csv` e atualiza as páginas.

> Não apague as linhas `<!-- JOGOS:INICIO -->`, `<!-- JOGOS:FIM -->`, `<!-- PROXIMO:INICIO -->` e `<!-- PROXIMO:FIM -->` dos HTMLs: é entre elas que o script escreve.

## Atualizar o elenco

Funciona igual aos jogos, com o arquivo `dados/elenco.csv`:

```
numero;nome;posicao;foto;jogos;gols;assistencias;formacao
7;Fulano;Zagueiro;;0;0;0;
```

Depois rode:

```bash
python dados/atualizar_elenco.py
```

ou use `python dados/atualizar_elenco.py --novo` para o script perguntar nome, posição, número (ou formação, no caso do técnico) e foto, salvar no `elenco.csv` e atualizar a página.

- A posição define o grupo na página (Goleiros, Zagueiros, Laterais, Meio-campo, Ataque, Comissão técnica). Se for uma posição diferente das comuns, preencha a coluna extra `grupo` com um desses nomes.
- A coluna `foto` é opcional: em branco, o script procura `imagens/jogadores/<nome em minúsculas, sem acento>.jpeg` (ex.: "João Vitor" vira `joao vitor.jpeg`). O script avisa quando uma foto não é encontrada.
- Dentro de cada grupo, os atletas ficam em ordem de número.
- Não apague as linhas `<!-- ELENCO:INICIO -->` e `<!-- ELENCO:FIM -->` do `elenco.html`.

## Comissão técnica

O técnico e outros membros da comissão ficam no mesmo `elenco.csv`, num grupo próprio ("Comissão técnica") no final da página de elenco:

```
numero;nome;posicao;foto;jogos;gols;assistencias;formacao
;Rodrigo;Técnico;;;;;Formado em Ed. Física pela Unicsul
```

- Use a posição `Técnico` (também vale `Treinador`, `Auxiliar técnico` ou `Preparador físico`).
- Deixe `numero`, `jogos`, `gols` e `assistencias` em branco: a comissão não tem camisa nem estatísticas.
- A coluna `formacao` é um texto curto que aparece no card (ex.: "Formado em Ed. Física pela Unicsul").
- A foto segue a mesma regra: em branco, procura `imagens/jogadores/rodrigo.jpeg`.
- O `--stats` ignora a comissão técnica.

## Estatísticas dos jogadores

Cada atleta tem **jogos**, **gols** e **assistências**, que aparecem no card dele em `elenco.html`. Os números ficam nas colunas `jogos`, `gols` e `assistencias` do `elenco.csv` (em branco vale 0).

Para alterar pelo script, sem abrir o arquivo:

```bash
python dados/atualizar_elenco.py --stats
```

Ele mostra o quadro atual e pergunta a camisa ou o nome do jogador (basta um pedaço do nome). Para cada estatística você pode:

- digitar um número para **definir** o valor (ex.: `5`);
- digitar `+N` para **somar** ao que já tem (ex.: `+1` depois de um gol);
- apertar Enter para **manter**.

Cada jogador é salvo assim que você termina, e a página é atualizada no final (Enter no lugar do nome encerra). Também dá para editar as colunas direto no Excel e rodar `python dados/atualizar_elenco.py`.

## Imagens

Coloque a sua pasta `imagens` dentro da pasta do site (ao lado dos HTMLs), com os nomes de arquivo de sempre (`logo.jpeg`, `carrossel/entrada.jpeg`, `carrossel/time.jpeg`, `carrossel/aquecimento.jpeg` (as três se alternam no fundo da página inicial), `jogadores/*.jpeg` (inclui `rodrigo.jpeg`, do técnico), `uniforme/linha.jpeg` e `goleiro.jpeg`). Foto que faltar aparece como silhueta.

## Arquivos

- `index.html`, `jogos.html`, `elenco.html`, `historia.html`, `loja.html`, `contato.html`, `404.html`: uma página por seção
- `css/estilo.css`: todo o visual (cores nas variáveis do topo)
- `js/menu.js`: só abre e fecha o menu no celular
- `dados/jogos.csv` e `dados/atualizar_jogos.py`: histórico de jogos e o script que atualiza o site
- `dados/elenco.csv` e `dados/atualizar_elenco.py`: o mesmo para os jogadores, a comissão técnica e as estatísticas

Camisas, história e contato são editados direto nos HTMLs. Se o número de WhatsApp mudar, troque em `contato.html`, `loja.html` e no rodapé de cada página (procure por `5511977890581`).
