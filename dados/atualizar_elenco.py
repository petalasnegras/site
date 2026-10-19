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

Colunas do elenco.csv (separador ; ou ,):
  numero        número da camisa (deixe em branco para a comissão técnica)
  nome          nome que aparece no site
  posicao       ex.: Goleiro, Zagueiro, Lateral direito, Volante, Meio-campista, Ponta, Centroavante,
                Técnico (também vale Treinador, Auxiliar técnico, Preparador físico)
  foto          (opcional) nome do arquivo dentro de imagens/jogadores/.
                Se ficar em branco, usa o nome da pessoa: "João Vitor" -> "joao vitor.jpeg"
  jogos         (opcional) jogos disputados; em branco vale 0 (não se aplica à comissão técnica)
  gols          (opcional) gols marcados; em branco vale 0
  assistencias  (opcional) assistências; em branco vale 0
  formacao      (opcional) texto curto que aparece no card da comissão técnica,
                ex.: Formado em Ed. Física pela Unicsul
  grupo         (opcional) só se a posição não for reconhecida: Goleiros, Zagueiros, Laterais,
                Meio-campo, Ataque ou Comissão técnica

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

PASTA = Path(__file__).resolve().parent  # pasta dos scripts e dos .csv (dados/)
# A raiz do site é a pasta de cima. Se alguém deixar o script na própria raiz, também funciona.
RAIZ = PASTA if (PASTA / "index.html").exists() else PASTA.parent

ARQUIVO_ELENCO = PASTA / "elenco.csv"
PAGINA_ELENCO = RAIZ / "elenco.html"
PASTA_FOTOS = RAIZ / "imagens" / "jogadores"

# (coluna no csv, nome completo, rótulo curto no card)
ESTATISTICAS = [
    ("jogos", "Jogos", "Jogos"),
    ("gols", "Gols", "Gols"),
    ("assistencias", "Assistências", "Assist."),
]

# Colunas extras que o script mantém no csv
COLUNAS_EXTRAS = ["formacao"]

# (id, título do grupo, palavras que identificam a posição)
GRUPOS = [
    ("goleiro", "Goleiros", ["goleiro", "goleira"]),
    ("zagueiro", "Zagueiros", ["zagueiro", "zagueira", "defensor", "libero"]),
    ("lateral", "Laterais", ["lateral"]),
    ("meio", "Meio-campo", ["volante", "meio", "meia", "armador"]),
    ("ataque", "Ataque", ["ataque", "atacante", "centroavante", "ponta", "pivo"]),
    ("tecnico", "Comissão técnica", ["tecnico", "treinador", "comissao", "preparador", "auxiliar"]),
]

GRUPO_STAFF = "tecnico"


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


def eh_staff(linha):
    """True se a linha crua do csv é da comissão técnica."""
    return descobrir_grupo(linha.get("grupo", ""), linha.get("posicao", "")) == GRUPO_STAFF


def foto_padrao(nome):
    return f"{sem_acento(nome).strip()}.jpeg"


# ---------------------------------------------------------------- leitura e escrita do csv

def detectar_separador(texto):
    primeira_linha = texto.splitlines()[0] if texto.strip() else ""
    return ";" if primeira_linha.count(";") >= primeira_linha.count(",") else ","


def carregar_tabela():
    """Lê o elenco.csv como está. Devolve (colunas, linhas, separador).

    Os nomes das colunas são normalizados (minúsculas, sem acento). Cada linha é um
    dicionário com os textos do csv e a chave "_linha" (número da linha no arquivo).
    """
    if not ARQUIVO_ELENCO.exists():
        erro(f"não encontrei {ARQUIVO_ELENCO.name} em {PASTA}.")

    texto = ARQUIVO_ELENCO.read_text(encoding="utf-8-sig")  # aceita arquivo salvo pelo Excel
    separador = detectar_separador(texto)
    leitor = csv.DictReader(texto.splitlines(), delimiter=separador)

    if not leitor.fieldnames:
        erro("o elenco.csv está vazio.")
    colunas = [sem_acento(c.strip()) for c in leitor.fieldnames]

    linhas = []
    for numero_linha, bruto in enumerate(leitor, start=2):
        linha = {sem_acento((k or "").strip()): (v or "").strip() for k, v in bruto.items()}
        if not any(linha.values()):
            continue  # linha em branco
        linha["_linha"] = numero_linha
        linhas.append(linha)
    return colunas, linhas, separador


def salvar_tabela(colunas, linhas, separador):
    """Grava o elenco.csv inteiro, garantindo as colunas de estatísticas e de formação."""
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
            numero = None  # comissão técnica não tem camisa
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
    if a["grupo"] == GRUPO_STAFF:
        linhas = [
            '            <li class="atleta">',
            foto,
            f'              <p class="atleta-nome">{esc(a["nome"])}</p>',
            f'              <p class="atleta-posicao">{esc(a["posicao"])}</p>',
        ]
        if a["formacao"]:
            linhas.append(f'              <p class="atleta-posicao">{esc(a["formacao"])}</p>')
        linhas.append('            </li>')
        return "\n".join(linhas)

    return f"""            <li class="atleta">
{foto}
              <span class="atleta-numero">{a['numero']}</span>
              <p class="atleta-nome">{esc(a['nome'])}</p>
              <p class="atleta-posicao">{esc(a['posicao'])}</p>
{html_estatisticas(a)}
            </li>"""


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


# ---------------------------------------------------------------- escrita da página

def substituir_bloco(arquivo, nome, novo_conteudo):
    """Troca o que está entre <!-- NOME:INICIO --> e <!-- NOME:FIM -->."""
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


# ---------------------------------------------------------------- perguntas

def perguntar(texto, obrigatorio=True):
    while True:
        resposta = input(f"{texto}: ").strip()
        if resposta or not obrigatorio:
            return resposta
        print("  Esse campo é obrigatório.")


def adicionar_jogador():
    colunas, linhas, separador = carregar_tabela()

    print("Novo integrante (Ctrl+C para cancelar)")
    nome = perguntar("Nome")
    while True:
        posicao = perguntar("Posição (ex.: Zagueiro, Lateral direito, Ponta; ou Técnico)")
        if descobrir_grupo(posicao):
            break
        print("  Não reconheci essa posição. Tente: Goleiro, Zagueiro, Lateral, Volante, Meio-campista, Ponta, Centroavante ou Técnico.")

    staff = descobrir_grupo(posicao) == GRUPO_STAFF
    numero = ""
    formacao = ""
    if staff:
        formacao = perguntar("Formação (ex.: Formado em Ed. Física pela Unicsul)", obrigatorio=False)
    else:
        while True:
            numero = perguntar("Número da camisa")
            if numero.isdigit():
                break
            print("  Digite só o número. Exemplo: 7")
    foto = perguntar(f"Arquivo da foto em imagens/jogadores (Enter para '{foto_padrao(nome)}')", obrigatorio=False)

    novo = {"numero": numero, "nome": nome, "posicao": posicao, "foto": foto, "formacao": formacao}
    if not staff:
        for coluna, _, _ in ESTATISTICAS:
            novo[coluna] = "0"
    linhas.append(novo)
    salvar_tabela(colunas, linhas, separador)
    if staff:
        print("Salvo no elenco.csv (comissão técnica).")
    else:
        print("Jogador salvo no elenco.csv (com jogos, gols e assistências em 0).")


# ---------------------------------------------------------------- estatísticas

def pedir_valor(rotulo, atual):
    """Pergunta um valor: número define, +N soma, Enter mantém."""
    while True:
        resposta = input(f"  {rotulo} (agora {atual}; número define, +N soma, Enter mantém): ").strip()
        if not resposta:
            return atual
        try:
            novo = atual + int(resposta[1:]) if resposta.startswith("+") else int(resposta)
        except ValueError:
            print("  Digite um número, ou +N para somar. Exemplo: 3 ou +1")
            continue
        if novo < 0:
            print("  O valor não pode ficar negativo.")
            continue
        return novo


def mostrar_quadro(linhas):
    print(f"\n{'Nº':>3}  {'Nome':<16}{'Jogos':>6}{'Gols':>6}{'Assist.':>8}")
    for l in sorted(linhas, key=lambda x: int(x["numero"]) if x.get("numero", "").isdigit() else 999):
        vals = [ler_estatistica(l, c, n.lower()) for c, n, _ in ESTATISTICAS]
        print(f"{l.get('numero', ''):>3}  {l.get('nome', ''):<16}{vals[0]:>6}{vals[1]:>6}{vals[2]:>8}")
    print()


def escolher_jogador(linhas):
    while True:
        resposta = input("Camisa ou nome do jogador (Enter para terminar): ").strip()
        if not resposta:
            return None
        busca = sem_acento(resposta)
        achados = [l for l in linhas
                   if (resposta.isdigit() and l.get("numero", "").isdigit() and int(l["numero"]) == int(resposta))
                   or sem_acento(l.get("nome", "")) == busca]
        if not achados:
            achados = [l for l in linhas if busca in sem_acento(l.get("nome", ""))]
        if len(achados) == 1:
            return achados[0]
        if not achados:
            print("  Não encontrei esse jogador.")
        else:
            print("  Mais de um jogador combina, seja mais específico: "
                  + ", ".join(f"{l['numero']} {l['nome']}" for l in achados))


def alterar_estatisticas():
    colunas, linhas, separador = carregar_tabela()
    jogadores = [l for l in linhas if not eh_staff(l)]  # comissão técnica não tem estatísticas
    mostrar_quadro(jogadores)
    print("Alterar estatísticas (Ctrl+C para cancelar)")
    while True:
        jogador = escolher_jogador(jogadores)
        if jogador is None:
            break
        print(f"{jogador['nome']} (camisa {jogador['numero']})")
        for coluna, nome_completo, _ in ESTATISTICAS:
            atual = ler_estatistica(jogador, coluna, nome_completo.lower())
            jogador[coluna] = str(pedir_valor(nome_completo, atual))
        salvar_tabela(colunas, linhas, separador)  # salva a cada jogador, nada se perde
        print("  Salvo.\n")
    print("Estatísticas gravadas no elenco.csv.")


def principal():
    parser = argparse.ArgumentParser(description="Atualiza elenco.html a partir do elenco.csv.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--novo", action="store_true", help="adiciona um jogador ou técnico (pergunta os dados) e atualiza o site")
    grupo.add_argument("--stats", action="store_true", help="altera jogos, gols e assistências dos jogadores e atualiza o site")
    args = parser.parse_args()

    if args.novo or args.stats:
        try:
            adicionar_jogador() if args.novo else alterar_estatisticas()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelado. O que já foi salvo continua no elenco.csv.")

    atletas, _ = ler_elenco()
    atualizar_pagina(atletas)


if __name__ == "__main__":
    principal()
