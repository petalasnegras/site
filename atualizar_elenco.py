#!/usr/bin/env python3
"""
Atualiza o site com o elenco.

Lê o arquivo elenco.csv (o "banco de dados" dos jogadores) e reescreve a lista
de atletas em elenco.html, organizada por posição.

Como usar:
  python atualizar_elenco.py          atualiza a página com o que está no elenco.csv
  python atualizar_elenco.py --novo   pergunta os dados de um jogador, salva no elenco.csv e atualiza

Colunas do elenco.csv (separador ; ou ,):
  numero   número da camisa
  nome     nome que aparece no site
  posicao  ex.: Goleiro, Zagueiro, Lateral direito, Volante, Meio-campista, Ponta, Centroavante
  foto     (opcional) nome do arquivo dentro de imagens/jogadores/.
           Se ficar em branco, usa o nome do jogador: "João Vitor" -> "joao vitor.jpeg"
  grupo    (opcional) só se a posição não for reconhecida: Goleiros, Zagueiros, Laterais,
           Meio-campo ou Ataque

Só usa a biblioteca padrão do Python 3.8 ou mais novo.
"""

import argparse
import csv
import html
import re
import sys
import unicodedata
from io import StringIO
from pathlib import Path
from urllib.parse import quote

PASTA = Path(__file__).resolve().parent
ARQUIVO_ELENCO = PASTA / "elenco.csv"
PAGINA_ELENCO = PASTA / "elenco.html"
PASTA_FOTOS = PASTA / "imagens" / "jogadores"

# (id, título do grupo, palavras que identificam a posição)
GRUPOS = [
    ("goleiro", "Goleiros", ["goleiro", "goleira"]),
    ("zagueiro", "Zagueiros", ["zagueiro", "zagueira", "defensor", "libero"]),
    ("lateral", "Laterais", ["lateral"]),
    ("meio", "Meio-campo", ["volante", "meio", "meia", "armador"]),
    ("ataque", "Ataque", ["ataque", "atacante", "centroavante", "ponta", "pivo"]),
]


def erro(mensagem):
    print(f"Erro: {mensagem}", file=sys.stderr)
    sys.exit(1)


def sem_acento(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


def descobrir_grupo(*textos):
    """Devolve o id do grupo (goleiro, zagueiro...) a partir da posição ou do grupo informado."""
    for texto in textos:
        normal = sem_acento(texto)
        if not normal:
            continue
        for id_grupo, _, palavras in GRUPOS:
            if any(p in normal for p in palavras):
                return id_grupo
    return None


def foto_padrao(nome):
    return f"{sem_acento(nome).strip()}.jpeg"


# ---------------------------------------------------------------- leitura

def detectar_separador(texto):
    primeira_linha = texto.splitlines()[0] if texto.strip() else ""
    return ";" if primeira_linha.count(";") >= primeira_linha.count(",") else ","


def ler_elenco():
    if not ARQUIVO_ELENCO.exists():
        erro(f"não encontrei {ARQUIVO_ELENCO.name}.")

    texto = ARQUIVO_ELENCO.read_text(encoding="utf-8-sig")  # aceita arquivo salvo pelo Excel
    separador = detectar_separador(texto)
    leitor = csv.DictReader(texto.splitlines(), delimiter=separador)

    if not leitor.fieldnames:
        erro("o elenco.csv está vazio.")
    cabecalho = [c.strip().lower() for c in leitor.fieldnames]
    faltando = [c for c in ("numero", "nome", "posicao") if c not in cabecalho]
    if faltando:
        erro(f"faltam colunas no elenco.csv: {', '.join(faltando)}.")

    atletas = []
    for numero_linha, bruto in enumerate(leitor, start=2):
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in bruto.items()}
        if not any(linha.values()):
            continue  # linha em branco

        nome = linha.get("nome", "")
        if not nome:
            erro(f"elenco.csv, linha {numero_linha}: falta o nome.")
        try:
            numero = int(linha.get("numero", ""))
        except ValueError:
            erro(f"elenco.csv, linha {numero_linha}: número da camisa inválido '{linha.get('numero', '')}'.")

        posicao = linha.get("posicao", "")
        grupo = descobrir_grupo(linha.get("grupo", ""), posicao)
        if grupo is None:
            lista = ", ".join(titulo for _, titulo, _ in GRUPOS)
            erro(f"elenco.csv, linha {numero_linha}: não reconheci a posição '{posicao}'. "
                 f"Escreva uma posição comum (ex.: Zagueiro) ou preencha a coluna grupo com: {lista}.")

        atletas.append({
            "numero": numero,
            "nome": nome,
            "posicao": posicao or dict((g, t) for g, t, _ in GRUPOS)[grupo],
            "grupo": grupo,
            "foto": linha.get("foto") or foto_padrao(nome),
        })
    return atletas, separador


def avisos(atletas):
    vistos = {}
    for a in atletas:
        if a["numero"] in vistos:
            print(f"Aviso: a camisa {a['numero']} está com {vistos[a['numero']]} e {a['nome']}.")
        vistos[a["numero"]] = a["nome"]

    faltando = [a for a in atletas if not (PASTA_FOTOS / a["foto"]).exists()]
    if faltando and len(faltando) == len(atletas):
        print("Aviso: não encontrei nenhuma foto em imagens/jogadores/ (aparece uma silhueta no lugar).")
    else:
        for a in faltando:
            print(f"Aviso: foto não encontrada em imagens/jogadores/{a['foto']} ({a['nome']}).")


# ---------------------------------------------------------------- HTML

def esc(texto):
    return html.escape(texto, quote=True)


def html_atleta(a):
    return f"""            <li class="atleta">
              <img src="imagens/jogadores/{quote(a['foto'])}" alt="Foto de {esc(a['nome'])}" loading="lazy" onerror="this.onerror=null;this.src='imagens/placeholder.svg'">
              <span class="atleta-numero">{a['numero']}</span>
              <p class="atleta-nome">{esc(a['nome'])}</p>
              <p class="atleta-posicao">{esc(a['posicao'])}</p>
            </li>"""


def html_elenco(atletas):
    blocos = []
    for id_grupo, titulo, _ in GRUPOS:
        do_grupo = sorted((a for a in atletas if a["grupo"] == id_grupo), key=lambda a: a["numero"])
        if not do_grupo:
            continue
        itens = "\n".join(html_atleta(a) for a in do_grupo)
        blocos.append(
            f'<div class="grupo-elenco">\n'
            f'          <h2>{titulo}</h2>\n'
            f'          <ul class="elenco-grade">\n{itens}\n          </ul>\n'
            f'        </div>'
        )
    if not blocos:
        return '<p class="vazio">Nenhum atleta cadastrado por enquanto.</p>'
    return "\n        ".join(blocos)


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


def atualizar_pagina(atletas):
    avisos(atletas)
    mudou = substituir_bloco(PAGINA_ELENCO, "ELENCO", html_elenco(atletas))
    print(f"{len(atletas)} atletas no elenco.csv.")
    print(f"  {PAGINA_ELENCO.name}: {'atualizado' if mudou else 'já estava em dia'}")


# ---------------------------------------------------------------- novo jogador

def perguntar(texto, obrigatorio=True):
    while True:
        resposta = input(f"{texto}: ").strip()
        if resposta or not obrigatorio:
            return resposta
        print("  Esse campo é obrigatório.")


def adicionar_jogador(separador):
    print("Novo jogador (Ctrl+C para cancelar)")
    while True:
        numero = perguntar("Número da camisa")
        if numero.isdigit():
            break
        print("  Digite só o número. Exemplo: 7")
    nome = perguntar("Nome")
    while True:
        posicao = perguntar("Posição (ex.: Zagueiro, Lateral direito, Ponta)")
        if descobrir_grupo(posicao):
            break
        print("  Não reconheci essa posição. Tente: Goleiro, Zagueiro, Lateral, Volante, Meio-campista, Ponta ou Centroavante.")
    foto = perguntar(f"Arquivo da foto em imagens/jogadores (Enter para '{foto_padrao(nome)}')", obrigatorio=False)

    conteudo = ARQUIVO_ELENCO.read_text(encoding="utf-8-sig")
    if conteudo and not conteudo.endswith("\n"):
        conteudo += "\n"
    saida = StringIO()
    csv.writer(saida, delimiter=separador, lineterminator="\n").writerow([numero, nome, posicao, foto])
    ARQUIVO_ELENCO.write_text(conteudo + saida.getvalue(), encoding="utf-8")
    print("Jogador salvo no elenco.csv.")


def principal():
    parser = argparse.ArgumentParser(description="Atualiza elenco.html a partir do elenco.csv.")
    parser.add_argument("--novo", action="store_true", help="adiciona um jogador (pergunta os dados) e atualiza o site")
    args = parser.parse_args()

    if args.novo:
        if not ARQUIVO_ELENCO.exists():
            erro(f"não encontrei {ARQUIVO_ELENCO.name}.")
        separador = detectar_separador(ARQUIVO_ELENCO.read_text(encoding="utf-8-sig"))
        try:
            adicionar_jogador(separador)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelado. Nada foi alterado.")
            return

    atletas, _ = ler_elenco()
    atualizar_pagina(atletas)


if __name__ == "__main__":
    principal()
