#!/usr/bin/env python3
"""
Atualiza o site com o histórico de jogos.

Lê o arquivo jogos.csv (o "banco de dados" dos jogos) e reescreve:
  - a lista de jogos em jogos.html
  - o destaque do próximo (ou último) jogo em index.html

Como usar:
  python atualizar_jogos.py          atualiza as páginas com o que está no jogos.csv
  python atualizar_jogos.py --novo   pergunta os dados de um jogo, salva no jogos.csv e atualiza

Colunas do jogos.csv (separador ; ou ,):
  data (DD/MM/AAAA), hora (HH:MM), adversario, local, placar (opcional, ex.: 2 x 1)

Um jogo aparece como "Próximo" até o dia dele passar; depois vira "Realizado" sozinho.
Só usa a biblioteca padrão do Python 3.8 ou mais novo.
"""

import argparse
import csv
import html
import re
import sys
from datetime import date, datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent
ARQUIVO_JOGOS = PASTA / "jogos.csv"
PAGINA_JOGOS = PASTA / "jogos.html"
PAGINA_INICIO = PASTA / "index.html"

NOSSO_TIME = "Pétalas Negras"
COLUNAS = ["data", "hora", "adversario", "local", "placar"]
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def erro(mensagem):
    print(f"Erro: {mensagem}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- leitura

def detectar_separador(texto):
    primeira_linha = texto.splitlines()[0] if texto.strip() else ""
    return ";" if primeira_linha.count(";") >= primeira_linha.count(",") else ","


def converter_data(texto, numero_linha):
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            pass
    erro(f"jogos.csv, linha {numero_linha}: data inválida '{texto}'. Use DD/MM/AAAA.")


def ler_jogos():
    if not ARQUIVO_JOGOS.exists():
        erro(f"não encontrei {ARQUIVO_JOGOS.name}.")

    texto = ARQUIVO_JOGOS.read_text(encoding="utf-8-sig")  # aceita arquivo salvo pelo Excel
    separador = detectar_separador(texto)
    leitor = csv.DictReader(texto.splitlines(), delimiter=separador)

    if not leitor.fieldnames:
        erro("o jogos.csv está vazio.")
    cabecalho = [c.strip().lower() for c in leitor.fieldnames]
    faltando = [c for c in COLUNAS[:4] if c not in cabecalho]
    if faltando:
        erro(f"faltam colunas no jogos.csv: {', '.join(faltando)}.")

    jogos = []
    for numero, bruto in enumerate(leitor, start=2):
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in bruto.items()}
        if not any(linha.values()):
            continue  # linha em branco
        if not linha.get("adversario"):
            erro(f"jogos.csv, linha {numero}: falta o adversário.")
        jogos.append({
            "data": converter_data(linha.get("data", ""), numero),
            "hora": linha.get("hora", ""),
            "adversario": linha["adversario"],
            "local": linha.get("local", ""),
            "placar": linha.get("placar", ""),
        })
    return jogos, separador


# ---------------------------------------------------------------- HTML

def esc(texto):
    return html.escape(texto, quote=True)


def descricao_data(jogo):
    d = jogo["data"]
    texto = f"{DIAS_SEMANA[d.weekday()]}, {d.strftime('%d/%m/%Y')}"
    return f"{texto}, {jogo['hora']}" if jogo["hora"] else texto


def confronto(jogo):
    meio = esc(jogo["placar"]) if jogo["placar"] else "x"
    return f"{NOSSO_TIME} {meio} {esc(jogo['adversario'])}"


def html_linha_jogo(jogo, proximo):
    d = jogo["data"]
    selo = '<span class="selo selo-proximo">Próximo</span>' if proximo else '<span class="selo">Realizado</span>'
    local = f'\n              <span class="jogo-detalhe">{esc(jogo["local"])}</span>' if jogo["local"] else ""
    return f"""          <li class="jogo">
            <div class="jogo-data"><strong>{d.day:02d}</strong><span>{MESES[d.month - 1]}</span></div>
            <div>
              <span class="jogo-confronto">{confronto(jogo)}</span>
              <span class="jogo-detalhe">{esc(descricao_data(jogo))}</span>{local}
            </div>
            {selo}
          </li>"""


def html_grupo(titulo, jogos, proximo, mensagem_vazia):
    if jogos:
        itens = "\n".join(html_linha_jogo(j, proximo) for j in jogos)
        itens = "\n".join("  " + l for l in itens.splitlines())
        corpo = f'<ul class="lista-jogos">\n{itens}\n          </ul>'
    else:
        corpo = f'<p class="vazio">{esc(mensagem_vazia)}</p>'
    return f'<div class="grupo-jogos">\n          <h2>{titulo}</h2>\n          {corpo}\n        </div>'


def separar(jogos, hoje):
    proximos = sorted((j for j in jogos if j["data"] >= hoje), key=lambda j: j["data"])
    realizados = sorted((j for j in jogos if j["data"] < hoje), key=lambda j: j["data"], reverse=True)
    return proximos, realizados


def html_pagina_jogos(jogos, hoje):
    proximos, realizados = separar(jogos, hoje)
    return "\n        ".join([
        html_grupo("Próximos jogos", proximos, True, "Nenhum jogo marcado por enquanto."),
        html_grupo("Jogos realizados", realizados, False, "Ainda não há jogos realizados."),
    ])


def html_destaque(jogos, hoje):
    proximos, realizados = separar(jogos, hoje)
    if proximos:
        jogo, rotulo = proximos[0], "Próximo jogo"
    elif realizados:
        jogo, rotulo = realizados[0], "Último jogo"
    else:
        return ""
    return (
        f'<a class="destaque-jogo" href="jogos.html">\n'
        f'          <span class="rotulo">{rotulo}</span>\n'
        f'          <strong>{confronto(jogo)}</strong>\n'
        f'          <span class="detalhe">{esc(descricao_data(jogo))}</span>\n'
        f'        </a>'
    )


# ---------------------------------------------------------------- escrita

def substituir_bloco(arquivo, nome, novo_conteudo):
    """Troca o que está entre <!-- NOME:INICIO --> e <!-- NOME:FIM -->."""
    if not arquivo.exists():
        erro(f"não encontrei {arquivo.name}.")
    texto = arquivo.read_text(encoding="utf-8")
    padrao = re.compile(rf"(<!-- {nome}:INICIO -->)(.*?)(<!-- {nome}:FIM -->)", re.DOTALL)
    if not padrao.search(texto):
        erro(f"{arquivo.name} não tem os marcadores <!-- {nome}:INICIO --> e <!-- {nome}:FIM -->.")
    novo = padrao.sub(lambda m: f"{m.group(1)}\n        {novo_conteudo}\n        {m.group(3)}", texto, count=1)
    if novo != texto:
        arquivo.write_text(novo, encoding="utf-8")
        return True
    return False


def atualizar_paginas(jogos, hoje=None):
    hoje = hoje or date.today()
    mudou_jogos = substituir_bloco(PAGINA_JOGOS, "JOGOS", html_pagina_jogos(jogos, hoje))
    mudou_inicio = substituir_bloco(PAGINA_INICIO, "PROXIMO", html_destaque(jogos, hoje))
    proximos, realizados = separar(jogos, hoje)
    print(f"{len(jogos)} jogos no jogos.csv: {len(proximos)} próximos, {len(realizados)} realizados.")
    print(f"  {PAGINA_JOGOS.name}: {'atualizado' if mudou_jogos else 'já estava em dia'}")
    print(f"  {PAGINA_INICIO.name}: {'atualizado' if mudou_inicio else 'já estava em dia'}")


# ---------------------------------------------------------------- novo jogo

def perguntar(texto, obrigatorio=True):
    while True:
        resposta = input(f"{texto}: ").strip()
        if resposta or not obrigatorio:
            return resposta
        print("  Esse campo é obrigatório.")


def adicionar_jogo(separador):
    print("Novo jogo (Ctrl+C para cancelar)")
    while True:
        data = perguntar("Data (DD/MM/AAAA)")
        try:
            datetime.strptime(data, "%d/%m/%Y")
            break
        except ValueError:
            print("  Data inválida. Exemplo: 25/10/2026")
    hora = perguntar("Horário (ex.: 10:00)")
    adversario = perguntar("Adversário")
    local = perguntar("Local", obrigatorio=False)
    placar = perguntar("Placar, se já aconteceu (ex.: 2 x 1)", obrigatorio=False)

    conteudo = ARQUIVO_JOGOS.read_text(encoding="utf-8-sig")
    if conteudo and not conteudo.endswith("\n"):
        conteudo += "\n"
    from io import StringIO
    saida = StringIO()
    csv.writer(saida, delimiter=separador, lineterminator="\n").writerow([data, hora, adversario, local, placar])
    ARQUIVO_JOGOS.write_text(conteudo + saida.getvalue(), encoding="utf-8")
    print("Jogo salvo no jogos.csv.")


def principal():
    parser = argparse.ArgumentParser(description="Atualiza jogos.html e index.html a partir do jogos.csv.")
    parser.add_argument("--novo", action="store_true", help="adiciona um jogo (pergunta os dados) e atualiza o site")
    args = parser.parse_args()

    if args.novo:
        if not ARQUIVO_JOGOS.exists():
            erro(f"não encontrei {ARQUIVO_JOGOS.name}.")
        separador = detectar_separador(ARQUIVO_JOGOS.read_text(encoding="utf-8-sig"))
        try:
            adicionar_jogo(separador)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelado. Nada foi alterado.")
            return

    jogos, _ = ler_jogos()
    atualizar_paginas(jogos)


if __name__ == "__main__":
    principal()
