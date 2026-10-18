# Pétalas Negras FC: site

Site estático: é só abrir o `index.html` no navegador (ou publicar a pasta em qualquer hospedagem). Não precisa de servidor.

## Atualizar os jogos

Os jogos ficam no arquivo `jogos.csv`, que pode ser editado no bloco de notas ou no Excel:

```
data;hora;adversario;local;placar
17/10/2026;10:00;Adversário a confirmar;Rua tal, 123;
```

Depois rode (precisa do Python 3):

```bash
python atualizar_jogos.py
```

O script reescreve a lista em `jogos.html` e o destaque de "Próximo jogo" em `index.html`. Um jogo é "Próximo" até o dia passar e depois vira "Realizado" sozinho (rode o script de novo para o site refletir isso). O placar é opcional, por exemplo `2 x 1`.

Para adicionar um jogo sem abrir o arquivo:

```bash
python atualizar_jogos.py --novo
```

Ele pergunta data, horário, adversário, local e placar, salva no `jogos.csv` e atualiza as páginas.

> Não apague as linhas `<!-- JOGOS:INICIO -->`, `<!-- JOGOS:FIM -->`, `<!-- PROXIMO:INICIO -->` e `<!-- PROXIMO:FIM -->` dos HTMLs: é entre elas que o script escreve.

## Atualizar o elenco

Funciona igual aos jogos, com o arquivo `elenco.csv`:

```
numero;nome;posicao;foto
7;Fulano;Zagueiro;
```

Depois rode:

```bash
python atualizar_elenco.py
```

ou use `python atualizar_elenco.py --novo` para o script perguntar número, nome, posição e foto, salvar no `elenco.csv` e atualizar a página.

- A posição define o grupo na página (Goleiros, Zagueiros, Laterais, Meio-campo, Ataque). Se for uma posição diferente das comuns, preencha a coluna extra `grupo` com um desses cinco nomes.
- A coluna `foto` é opcional: em branco, o script procura `imagens/jogadores/<nome em minúsculas, sem acento>.jpeg` (ex.: "João Vitor" vira `joao vitor.jpeg`). O script avisa quando uma foto não é encontrada.
- Dentro de cada grupo, os atletas ficam em ordem de número.
- Não apague as linhas `<!-- ELENCO:INICIO -->` e `<!-- ELENCO:FIM -->` do `elenco.html`.

## Imagens

Coloque a sua pasta `imagens` dentro desta pasta, com os mesmos nomes de arquivo de antes (`logo.jpeg`, `carrossel/entrada.jpeg`, `carrossel/time.jpeg`, `carrossel/aquecimento.jpeg` (as três se alternam no fundo da página inicial), `jogadores/*.jpeg`, `uniforme/linha.jpeg` e `goleiro.jpeg`). Foto que faltar aparece como silhueta.

## Arquivos

- `index.html`, `jogos.html`, `elenco.html`, `historia.html`, `loja.html`, `contato.html`, `404.html`: uma página por seção
- `css/estilo.css`: todo o visual (cores nas variáveis do topo)
- `js/menu.js`: só abre e fecha o menu no celular
- `jogos.csv` e `atualizar_jogos.py`: histórico de jogos e o script que atualiza o site
- `elenco.csv` e `atualizar_elenco.py`: o mesmo para os jogadores

Camisas, história e contato são editados direto nos HTMLs. Se o número de WhatsApp mudar, troque em `contato.html`, `loja.html` e no rodapé de cada página (procure por `5511977890581`).
