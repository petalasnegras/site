#!/usr/bin/env python3
"""
Atualiza o site com o elenco, a comissão técnica e as estatísticas dos jogadores.

Lê o arquivo elenco.csv (o "banco de dados" dos jogadores e do técnico) e reescreve a
lista de atletas em ../elenco.html, organizada por posição, com jogos, gols e assistências.
A comissão técnica aparece num grupo próprio, no final, sem estatísticas de jogo.

Este script e os arquivos .csv ficam na pasta dados/. Pode rodar de qualquer lugar:

  python dados/atualizar_elenco.py            atualiza a página com o que está no elenco.csv
  python dados/atualizar_elenco.py --novo     pergunta os dados de um jogador (ou do técnico), salva e atualiza
  python dados/atualizar_elenco.py --stats    altera jogos, gols e assistências, salva e atualiza
"""

import argparse
import csv
import html
import json
import re
import sys
import unicodedata
from io import StringIO
from pathlib import Path
from urllib.parse import quote

PASTA = Path(__file__).resolve().parent  # pasta dos scripts e dos .csv (dados/)
RAIZ = PASTA if (PASTA / "index.html").exists() else PASTA.parent

ARQUIVO_ELENCO = PASTA / "elenco.csv"
PAGINA_ELENCO = RAIZ / "elenco.html"
PASTA_FOTOS = RAIZ / "imagens" / "jogadores"

ESTATISTICAS = [
    ("jogos", "Jogos", "Jogos"),
    ("gols", "Gols", "Gols"),
    ("assistencias", "Assistências", "Assist."),
]

# Novas colunas de perfil mantidas no csv
COLUNAS_EXTRAS = ["formacao", "idade", "pe", "altura", "titulos", "fotos_jogo"]

GRUPOS = [
    ("goleiro", "Goleiros", ["goleiro", "goleira"]),
    ("zagueiro", "Zagueiros", ["zagueiro", "zagueira", "defensor", "libero"]),
    ("lateral", "Laterais", ["lateral"]),
    ("meio", "Meio-campo", ["volante", "meio", "meia", "armador"]),
    ("ataque", "Ataque", ["ataque", "atacante", "centroavante", "ponta", "pivo"]),
    ("tecnico", "Comissão técnica / Staff", ["tecnico", "treinador", "comissao", "preparador", "auxiliar", "fotografo", "fotografa"]),
]

GRUPO_STAFF = "tecnico"


def erro(mensagem):
    print(f"Erro: {mensagem}", file=sys.stderr)
    sys.exit(1)


def sem_acento(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


def descobrir_grupo(*textos):
    for texto in textos:
        normal = sem_acento(texto)
        if not normal:
            continue
        for id_grupo, _, palavras in GRUPOS:
            if any(p in normal for p in palavras):
                return id_grupo
    return None


def eh_staff(linha):
    return descobrir_grupo(linha.get("grupo", ""), linha.get("posicao", "")) == GRUPO_STAFF


def foto_padrao(nome):
    return f"{sem_acento(nome).strip()}.jpeg"


# ---------------------------------------------------------------- leitura e escrita do csv

def detectar_separador(texto):
    primeira_linha = texto.splitlines()[0] if texto.strip() else ""
    return ";" if primeira_linha.count(";") >= primeira_linha.count(",") else ","


def carregar_tabela():
    if not ARQUIVO_ELENCO.exists():
        erro(f"não encontrei {ARQUIVO_ELENCO.name} em {PASTA}.")

    texto = ARQUIVO_ELENCO.read_text(encoding="utf-8-sig")
    separador = detectar_separador(texto)
    leitor = csv.DictReader(texto.splitlines(), delimiter=separador)

    if not leitor.fieldnames:
        erro("o elenco.csv está vazio.")
    colunas = [sem_acento(c.strip()) for c in leitor.fieldnames]

    linhas = []
    for numero_linha, bruto in enumerate(leitor, start=2):
        linha = {sem_acento((k or "").strip()): (v or "").strip() for k, v in bruto.items()}
        if not any(linha.values()):
            continue
        linha["_linha"] = numero_linha
        linhas.append(linha)
    return colunas, linhas, separador


def salvar_tabela(colunas, linhas, separador):
    colunas = list(colunas)
    for coluna in [c for c, _, _ in ESTATISTICAS] + COLUNAS_EXTRAS:
        if coluna not in colunas:
            colunas.append(coluna)
    saida = StringIO()
    escritor = csv.DictWriter(saida, fieldnames=colunas, delimiter=separador,
                              lineterminator="\n", extrasaction="ignore", restval="")
    escritor.writeheader()
    escritor.writerows(linhas)
    ARQUIVO_ELENCO.write_text(saida.getvalue(), encoding="utf-8")


def ler_estatistica(linha, coluna, rotulo):
    texto = linha.get(coluna, "")
    if texto == "":
        return 0
    try:
        valor = int(texto)
    except ValueError:
        valor = -1
    if valor < 0:
        erro(f"elenco.csv, linha {linha['_linha']}: {rotulo} inválido '{texto}'. Use um número inteiro (0 ou mais).")
    return valor


def ler_elenco():
    colunas, linhas, separador = carregar_tabela()
    faltando = [c for c in ("numero", "nome", "posicao") if c not in colunas]
    if faltando:
        erro(f"faltam colunas no elenco.csv: {', '.join(faltando)}.")

    atletas = []
    for linha in linhas:
        nome = linha.get("nome", "")
        if not nome:
            erro(f"elenco.csv, linha {linha['_linha']}: falta o nome.")

        posicao = linha.get("posicao", "")
        grupo = descobrir_grupo(linha.get("grupo", ""), posicao)
        if grupo is None:
            lista = ", ".join(titulo for _, titulo, _ in GRUPOS)
            erro(f"elenco.csv, linha {linha['_linha']}: não reconheci a posição '{posicao}'. "
                 f"Escreva uma posição comum (ex.: Zagueiro) ou preencha a coluna grupo com: {lista}.")

        texto_numero = linha.get("numero", "")
        if grupo == GRUPO_STAFF and texto_numero == "":
            numero = None
        else:
            try:
                numero = int(texto_numero)
            except ValueError:
                erro(f"elenco.csv, linha {linha['_linha']}: número da camisa inválido '{texto_numero}'.")

        atleta = {
            "numero": numero,
            "nome": nome,
            "posicao": posicao or dict((g, t) for g, t, _ in GRUPOS)[grupo],
            "grupo": grupo,
            "foto": linha.get("foto") or foto_padrao(nome),
            "formacao": linha.get("formacao", ""),
            "idade": linha.get("idade", ""),
            "pe": linha.get("pe", ""),
            "altura": linha.get("altura", ""),
            "titulos": linha.get("titulos", ""),
            "fotos_jogo": linha.get("fotos_jogo", ""),
        }
        if grupo != GRUPO_STAFF:
            for coluna, nome_completo, _ in ESTATISTICAS:
                atleta[coluna] = ler_estatistica(linha, coluna, nome_completo.lower())
        atletas.append(atleta)
    return atletas, separador


def avisos(atletas):
    vistos = {}
    for a in atletas:
        if a["numero"] is None:
            continue
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


def html_estatisticas(a):
    itens = "\n".join(
        f'                <li{" class=zero" if a[coluna] == 0 else ""} title="{esc(nome_completo)}">'
        f'<strong>{a[coluna]}</strong><span>{esc(curto)}</span></li>'
        for coluna, nome_completo, curto in ESTATISTICAS
    )
    return (f'              <ul class="atleta-stats" aria-label="Estatísticas de {esc(a["nome"])}">\n'
            f'{itens}\n'
            f'              </ul>')


def html_atleta(a):
    foto = (f'              <img src="imagens/jogadores/{quote(a["foto"])}" alt="Foto de {esc(a["nome"])}" '
            f'loading="lazy" onerror="this.onerror=null;this.src=\'imagens/placeholder.svg\'">')
    
    slug_id = sem_acento(a["nome"]).strip().replace(" ", "-")
    url_perfil = f"jogador.html?id={slug_id}"

    if a["grupo"] == GRUPO_STAFF:
        formacao_html = f'\n              <p class="atleta-posicao">{esc(a["formacao"])}</p>' if a["formacao"] else ''
        return f"""            <li class="atleta">
              <a href="{url_perfil}" class="atleta-link">
{foto}
                <p class="atleta-nome">{esc(a["nome"])}</p>
                <p class="atleta-posicao">{esc(a["posicao"])}</p>{formacao_html}
              </a>
            </li>"""

    return f"""            <li class="atleta">
              <a href="{url_perfil}" class="atleta-link">
{foto}
                <span class="atleta-numero">{a['numero']}</span>
                <p class="atleta-nome">{esc(a['nome'])}</p>
                <p class="atleta-posicao">{esc(a['posicao'])}</p>
{html_estatisticas(a)}
              </a>
            </li>"""


def gerar_json_jogadores(atletas):
    dados = {}
    for a in atletas:
        slug_id = sem_acento(a["nome"]).strip().replace(" ", "-")
        
        # Converte a string "1.jpg, 2.jpg" em lista ["1.jpg", "2.jpg"]
        lista_fotos = [f.strip() for f in a.get("fotos_jogo", "").split(",") if f.strip()]
        
        dados[slug_id] = {
            "nome": a["nome"],
            "numero": a["numero"],
            "posicao": a["posicao"],
            "grupo": a["grupo"],
            "foto": a["foto"],
            "formacao": a["formacao"],
            "idade": a["idade"],
            "pe": a["pe"],
            "altura": a["altura"],
            "titulos": a["titulos"],
            "fotos_jogo": lista_fotos,
            "jogos": a.get("jogos", 0),
            "gols": a.get("gols", 0),
            "assistencias": a.get("assistencias", 0)
        }
    
    arquivo_json = PASTA / "jogadores.json"
    arquivo_json.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {arquivo_json.name}: atualizado")


def chave_ordem(a):
    return (a["numero"] is None, a["numero"] or 0, a["nome"])


def html_elenco(atletas):
    blocos = []
    for id_grupo, titulo, _ in GRUPOS:
        do_grupo = sorted((a for a in atletas if a["grupo"] == id_grupo), key=chave_ordem)
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


def substituir_bloco(arquivo, nome, novo_conteudo):
    if not arquivo.exists():
        erro(f"não encontrei {arquivo.name} em {arquivo.parent}.")
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
    staff = sum(1 for a in atletas if a["grupo"] == GRUPO_STAFF)
    print(f"{len(atletas) - staff} atletas e {staff} da comissão técnica no elenco.csv.")
    print(f"  {PAGINA_ELENCO.name}: {'atualizado' if mudou else 'já estava em dia'}")
    gerar_json_jogadores(atletas)


def principal():
    parser = argparse.ArgumentParser(description="Atualiza elenco.html a partir do elenco.csv.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--novo", action="store_true", help="adiciona um jogador ou técnico e atualiza")
    grupo.add_argument("--stats", action="store_true", help="altera jogos, gols e assistências e atualiza")
    args = parser.parse_args()

    atletas, _ = ler_elenco()
    atualizar_pagina(atletas)


if __name__ == "__main__":
    principal()