#!/usr/bin/env python3
"""
Gerencia os jogos do site (calendário, placar, escalação, substituições e fotos) a partir do jogos.csv.

O jogos.csv é o "banco de dados" dos jogos. Este script lê o csv e reescreve:
  - a lista de jogos em ../jogos.html
  - o destaque do próximo (ou último) jogo em ../index.html
  - o arquivo dados/jogos.json, usado pela página de cada jogo (jogo.html)

Este script e os arquivos .csv ficam na pasta dados/. Pode rodar de qualquer lugar:

  python dados/atualizar_jogos.py                   só atualiza as páginas com o que está no jogos.csv
  python dados/atualizar_jogos.py --listar          mostra todos os jogos (nada é alterado)
  python dados/atualizar_jogos.py --novo            cadastra um jogo
  python dados/atualizar_jogos.py --editar          edita qualquer dado de um jogo já cadastrado
  python dados/atualizar_jogos.py --placar          lança o placar de um jogo rapidamente
  python dados/atualizar_jogos.py --escalacao       define titulares, reservas e substituições de um jogo
  python dados/atualizar_jogos.py --fotos           lê as pastas imagens/jogos/<id>/ e preenche a coluna fotos
  python dados/atualizar_jogos.py --remover         remove um jogo

Colunas do jogos.csv (separador ; ou ,):
  data (DD/MM/AAAA), hora (HH:MM), adversario, local, placar (ex.: 2 x 1),
  escalacao (titulares), reservas, substituicoes, fotos (arquivos da pasta imagens/jogos/<id>/)

TITULARES E RESERVAS
  Escreva os jogadores separados por vírgula, pelo nome ou pelo número da camisa (como estão no
  elenco.csv). Ex.: Henrico, 2, Heitor, Rulim

SUPORTE
  Suporte é quem entrou para completar o time mas não está no elenco. Ele fica dentro dos titulares
  ou das reservas, marcado com (suporte), e pode ter a posição depois da vírgula:
      Fulano (suporte), Ciclano (suporte, Goleiro)
  Se você digitar um nome que não está no elenco, o script pergunta se quer adicioná-lo como suporte.

SUBSTITUIÇÕES
  Quem entrou do banco e quem saiu, na ordem em que aconteceram: Quem entrou > Quem saiu
  Ex.: Rulim > Jonas, Paiva > Heitor      (quem entrou precisa estar nas reservas)

  O minuto do jogo é opcional e vai no fim, com apóstrofo (ou entre parênteses):
      Rulim > Jonas 80', Paiva > Heitor (45+2')
  Sem o apóstrofo, o número é lido como camisa (ex.: Rulim > 2 é o Jonas).

Um jogo aparece como "Próximo" até o dia dele passar; depois vira "Realizado" sozinho.
O endereço da página de cada jogo é jogo.html?id=AAAA-MM-DD-adversario.
Só usa a biblioteca padrão do Python 3.8 ou mais novo.
"""

import argparse
import csv
import html
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from urllib.parse import quote

PASTA = Path(__file__).resolve().parent  # pasta dos scripts e dos .csv (dados/)
# A raiz do site é a pasta de cima. Se alguém deixar o script na própria raiz, também funciona.
RAIZ = PASTA if (PASTA / "index.html").exists() else PASTA.parent

ARQUIVO_JOGOS = PASTA / "jogos.csv"
ARQUIVO_ELENCO = PASTA / "elenco.csv"
ARQUIVO_JSON = PASTA / "jogos.json"
PAGINA_JOGOS = RAIZ / "jogos.html"
PAGINA_INICIO = RAIZ / "index.html"
PASTA_FOTOS_JOGOS = RAIZ / "imagens" / "jogos"
EXTENSOES_IMAGEM = {".jpeg", ".jpg", ".png", ".webp"}

NOSSO_TIME = "Pétalas Negras"
COLUNAS = ["data", "hora", "adversario", "local", "placar", "escalacao", "reservas", "substituicoes", "fotos"]
COLUNAS_OBRIGATORIAS = COLUNAS[:4]
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Mesmas posições do atualizar_elenco.py (palavras sem acento). A ordem da lista é a ordem na escalação.
GRUPOS = [
    ("goleiro", ["goleiro", "goleira"]),
    ("zagueiro", ["zagueiro", "zagueira", "defensor", "libero"]),
    ("lateral", ["lateral"]),
    ("meio", ["volante", "meio", "meia", "armador"]),
    ("ataque", ["ataque", "atacante", "centroavante", "ponta", "pivo"]),
    ("tecnico", ["tecnico", "treinador", "comissao", "preparador", "auxiliar", "fotografo", "fotografa"]),
]
ORDEM_GRUPOS = [g for g, _ in GRUPOS]

PADRAO_SUPORTE = re.compile(r"(.+?)\s*\(\s*suporte\s*(?:[,;:\-]\s*(.*?))?\s*\)", re.IGNORECASE)
PADRAO_SUBSTITUICAO = re.compile(r"(.+?)\s*(?:>|→|\bpor\b)\s*(.+)", re.IGNORECASE)

# Minuto no fim da substituição: "80'", "45+2'" ou entre parênteses "(80')" / "(80)".
# Sem apóstrofo e sem parênteses o número é camisa, não minuto.
_MIN = r"(\d{1,3}(?:\s*\+\s*\d{1,2})?)"
PADRAO_MINUTO = re.compile(
    rf"^(?P<resto>.*?)(?:\s*\(\s*{_MIN}\s*['′’]?\s*\)|\s+{_MIN}\s*['′’])\s*$"
)


def erro(mensagem):
    print(f"Erro: {mensagem}", file=sys.stderr)
    sys.exit(1)


def sem_acento(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


def slug_jogador(nome):
    """Mesmo identificador que o atualizar_elenco.py usa em jogador.html?id=..."""
    return sem_acento(nome).strip().replace(" ", "-")


def id_base(data, adversario):
    """Identificador do jogo: usado na URL (jogo.html?id=...) e na pasta imagens/jogos/<id>/."""
    nome = re.sub(r"[^a-z0-9]+", "-", sem_acento(adversario)).strip("-")
    return f"{data.isoformat()}-{nome}" if nome else data.isoformat()


def ordem_natural(texto):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", texto)]


def descobrir_grupo(texto):
    normal = sem_acento(texto or "")
    if not normal:
        return ""
    for id_grupo, palavras in GRUPOS:
        if any(p in normal for p in palavras):
            return id_grupo
    return ""


def separar_lista(texto):
    """Separa por vírgula (ou |), sem quebrar o que está entre parênteses: 'A (suporte, Goleiro), B'."""
    itens, atual, nivel = [], [], 0
    for c in texto or "":
        if c == "(":
            nivel += 1
        elif c == ")":
            nivel = max(0, nivel - 1)
        if c in ",|" and nivel == 0:
            itens.append("".join(atual))
            atual = []
        else:
            atual.append(c)
    itens.append("".join(atual))
    return [i.strip() for i in itens if i.strip()]


# ---------------------------------------------------------------- elenco (para resolver a escalação)

_elenco_cache = None


def elenco():
    """Lê nome, camisa e posição do elenco.csv. Só leitura: quem cuida desse arquivo é o atualizar_elenco.py."""
    global _elenco_cache
    if _elenco_cache is not None:
        return _elenco_cache
    pessoas = []
    if ARQUIVO_ELENCO.exists():
        texto = ARQUIVO_ELENCO.read_text(encoding="utf-8-sig")
        primeira = texto.splitlines()[0] if texto.strip() else ""
        separador = ";" if primeira.count(";") >= primeira.count(",") else ","
        for bruto in csv.DictReader(texto.splitlines(), delimiter=separador):
            linha = {sem_acento((k or "").strip()): (v or "").strip() for k, v in bruto.items()}
            if linha.get("nome"):
                pessoas.append({"nome": linha["nome"], "numero": linha.get("numero", ""),
                                "posicao": linha.get("posicao", ""), "slug": slug_jogador(linha["nome"])})
    _elenco_cache = pessoas
    return pessoas


def no_elenco_exato(nome):
    alvo = sem_acento(nome).strip()
    return any(sem_acento(p["nome"]) == alvo for p in elenco())


def resolver_jogador(texto):
    """Acha um jogador do elenco pela camisa ou pelo nome. Devolve (pessoa, None) ou (None, motivo)."""
    pessoas = elenco()
    if not pessoas:
        return None, "não encontrei o elenco.csv para conferir os nomes"
    t = sem_acento(texto).strip()
    if t.isdigit():
        achados = [p for p in pessoas if p["numero"] == str(int(t))]
    else:
        achados = [p for p in pessoas if sem_acento(p["nome"]) == t]
        if not achados:
            achados = [p for p in pessoas if t and t in sem_acento(p["nome"])]
    if not achados:
        return None, f"ninguém no elenco com nome ou camisa '{texto}'"
    if len(achados) > 1:
        nomes = ", ".join(p["nome"] for p in achados)
        return None, f"'{texto}' bate com mais de um jogador ({nomes}); escreva o nome completo ou a camisa"
    return achados[0], None


# ---------------------------------------------------------------- escalação (titulares, reservas, suporte, substituições)

def formatar_suporte(nome, posicao=""):
    return f"{nome} (suporte, {posicao})" if posicao else f"{nome} (suporte)"


def interpretar_suporte(texto):
    """'Fulano (suporte, Goleiro)' -> ('Fulano', 'Goleiro'). Devolve None se não for suporte."""
    m = PADRAO_SUPORTE.fullmatch(texto.strip())
    return (m.group(1).strip(), (m.group(2) or "").strip()) if m else None


def separar_minuto(texto):
    """'Rulim > Jonas 80\\'' -> ('Rulim > Jonas', \"80'\"). Sem minuto devolve (texto, '')."""
    m = PADRAO_MINUTO.match(texto.strip())
    if not m:
        return texto.strip(), ""
    numero = m.group(2) or m.group(3)
    return m.group("resto").strip(), formatar_minuto(numero)


def formatar_minuto(numero):
    """'80' -> \"80'\"; '45 + 2' -> \"45+2'\"."""
    return re.sub(r"\s+", "", numero) + "'"


def nova_entrada(nome, numero, posicao, slug, suporte):
    return {"nome": nome, "numero": numero, "posicao": posicao, "grupo": descobrir_grupo(posicao),
            "slug": slug, "suporte": suporte, "entrou_por": None, "saiu_para": None, "minuto": None}


def resolver_entrada(texto):
    """Transforma o texto do csv numa pessoa da escalação. Devolve (entrada, None) ou (None, motivo)."""
    suporte = interpretar_suporte(texto)
    if suporte:
        return nova_entrada(suporte[0], None, suporte[1], None, True), None
    pessoa, motivo = resolver_jogador(texto)
    if pessoa is None:
        return None, motivo
    numero = int(pessoa["numero"]) if pessoa["numero"].isdigit() else None
    return nova_entrada(pessoa["nome"], numero, pessoa["posicao"], pessoa["slug"], False), None


def chave_entrada(e):
    return e["slug"] or "suporte:" + sem_acento(e["nome"]).strip()


def ordenar_entradas(entradas):
    """Por posição (goleiro, zagueiro, lateral, meio, ataque); dentro da posição, por camisa e nome."""
    def chave(e):
        grupo = ORDEM_GRUPOS.index(e["grupo"]) if e["grupo"] in ORDEM_GRUPOS else len(ORDEM_GRUPOS)
        return (grupo, e["numero"] if e["numero"] is not None else 9999, sem_acento(e["nome"]))
    return sorted(entradas, key=chave)


def resolver_lista(textos):
    entradas, problemas, vistos = [], [], set()
    for texto in textos:
        entrada, motivo = resolver_entrada(texto)
        if entrada is None:
            problemas.append(motivo)
        elif chave_entrada(entrada) not in vistos:
            vistos.add(chave_entrada(entrada))
            entradas.append(entrada)
    return ordenar_entradas(entradas), problemas


def achar_na_lista(texto, entradas):
    """Procura uma pessoa dentro de uma lista de entradas, por camisa ou nome."""
    t = sem_acento(texto).strip()
    if t.isdigit():
        achados = [e for e in entradas if e["numero"] is not None and e["numero"] == int(t)]
    else:
        achados = [e for e in entradas if sem_acento(e["nome"]) == t]
        if not achados:
            achados = [e for e in entradas if t and t in sem_acento(e["nome"])]
    if len(achados) == 1:
        return achados[0], None
    if not achados:
        return None, "não encontrei na escalação deste jogo"
    return None, "bate com mais de um nome (" + ", ".join(e["nome"] for e in achados) + ")"


def resolver_substituicoes(textos, titulares, reservas):
    """
    Cada substituição é 'Quem entrou > Quem saiu', na ordem em que aconteceram, com minuto opcional
    no fim ('Rulim > Jonas 80\\''). Quem entrou precisa estar no banco; quem saiu precisa estar em campo
    (titular ou reserva que já entrou). Preenche entrou_por / saiu_para / minuto nas entradas.
    Devolve (pares, problemas); cada par é {"entrou", "saiu", "minuto"}.
    """
    pares, problemas = [], []
    em_campo = list(titulares)
    banco = list(reservas)
    for texto in textos:
        corpo, minuto = separar_minuto(texto)
        m = PADRAO_SUBSTITUICAO.fullmatch(corpo)
        if not m:
            problemas.append(f"substituição '{texto}': use o formato 'Quem entrou > Quem saiu' (minuto opcional: 80')")
            continue
        entrou, motivo = achar_na_lista(m.group(1), banco)
        if entrou is None:
            problemas.append(f"substituição '{texto}': quem entrou ({m.group(1).strip()}) precisa estar nas reservas e ainda no banco; {motivo}")
            continue
        saiu, motivo = achar_na_lista(m.group(2), em_campo)
        if saiu is None:
            problemas.append(f"substituição '{texto}': quem saiu ({m.group(2).strip()}) precisa estar em campo; {motivo}")
            continue
        banco.remove(entrou)
        em_campo.remove(saiu)
        em_campo.append(entrou)
        saiu["saiu_para"] = entrou["nome"]
        entrou["entrou_por"] = saiu["nome"]
        if minuto:
            saiu["minuto"] = minuto
            entrou["minuto"] = minuto
        pares.append({"entrou": entrou["nome"], "saiu": saiu["nome"], "minuto": minuto})
    return pares, problemas


def texto_substituicao(par):
    """Volta o par ao formato do csv: 'Rulim > Jonas 80\\''."""
    base = f"{par['entrou']} > {par['saiu']}"
    return f"{base} {par['minuto']}" if par.get("minuto") else base


def montar_escalacao(jogo):
    """Devolve (titulares, reservas, substituicoes, problemas) já resolvidos e ordenados."""
    titulares, p1 = resolver_lista(jogo["escalacao"])
    reservas, p2 = resolver_lista(jogo["reservas"])
    nos_titulares = {chave_entrada(e) for e in titulares}
    reservas = [e for e in reservas if chave_entrada(e) not in nos_titulares]
    pares, p3 = resolver_substituicoes(jogo["substituicoes"], titulares, reservas)
    return titulares, reservas, pares, p1 + p2 + p3


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


def interpretar_placar(texto):
    """'2 x 1' -> (2, 1). Devolve None se não for um placar no formato esperado."""
    m = re.fullmatch(r"\s*(\d+)\s*[xX×-]\s*(\d+)\s*", texto or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def migrar_suporte_antigo(colunas, linhas):
    """A coluna 'suporte' (versão anterior) vira entradas '(suporte)' dentro das reservas."""
    if "suporte" not in colunas:
        return
    colunas.remove("suporte")
    migrou = False
    for linha in linhas:
        itens = separar_lista(linha.get("suporte", ""))
        linha["suporte"] = ""
        if not itens:
            continue
        novos = []
        for item in itens:
            m = re.fullmatch(r"(.+?)\s*\(([^)]*)\)", item)
            nome, posicao = (m.group(1).strip(), m.group(2).strip()) if m else (item, "")
            novos.append(formatar_suporte(nome, posicao))
        linha["reservas"] = ", ".join(separar_lista(linha.get("reservas", "")) + novos)
        migrou = True
    if migrou:
        print("Aviso: a coluna 'suporte' antiga foi movida para as reservas (marcados como suporte). "
              "Será gravada assim na próxima alteração pelo script.")


def carregar_tabela():
    if not ARQUIVO_JOGOS.exists():
        erro(f"não encontrei {ARQUIVO_JOGOS.name} em {PASTA}.")

    texto = ARQUIVO_JOGOS.read_text(encoding="utf-8-sig")  # aceita arquivo salvo pelo Excel
    separador = detectar_separador(texto)
    leitor = csv.DictReader(texto.splitlines(), delimiter=separador)

    if not leitor.fieldnames:
        erro("o jogos.csv está vazio.")
    colunas = [c.strip().lower() for c in leitor.fieldnames]
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in colunas]
    if faltando:
        erro(f"faltam colunas no jogos.csv: {', '.join(faltando)}.")

    linhas = []
    for numero, bruto in enumerate(leitor, start=2):
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in bruto.items()}
        if not any(linha.values()):
            continue  # linha em branco
        linha["_linha"] = numero
        linhas.append(linha)
    migrar_suporte_antigo(colunas, linhas)
    return colunas, linhas, separador


def salvar_tabela(colunas, linhas, separador):
    colunas = list(colunas)
    for coluna in COLUNAS:
        if coluna not in colunas:
            colunas.append(coluna)
    saida = StringIO()
    escritor = csv.DictWriter(saida, fieldnames=colunas, delimiter=separador,
                              lineterminator="\n", extrasaction="ignore", restval="")
    escritor.writeheader()
    escritor.writerows(linhas)
    ARQUIVO_JOGOS.write_text(saida.getvalue(), encoding="utf-8")


def montar_jogos(linhas):
    jogos = []
    usados = {}
    for linha in linhas:
        if not linha.get("adversario"):
            erro(f"jogos.csv, linha {linha['_linha']}: falta o adversário.")
        data = converter_data(linha.get("data", ""), linha["_linha"])

        base = id_base(data, linha["adversario"])
        usados[base] = usados.get(base, 0) + 1
        id_jogo = base if usados[base] == 1 else f"{base}-{usados[base]}"

        jogos.append({
            "id": id_jogo,
            "data": data,
            "hora": linha.get("hora", ""),
            "adversario": linha["adversario"],
            "local": linha.get("local", ""),
            "placar": linha.get("placar", ""),
            "escalacao": separar_lista(linha.get("escalacao", "")),
            "reservas": separar_lista(linha.get("reservas", "")),
            "substituicoes": separar_lista(linha.get("substituicoes", "")),
            "fotos": [f.strip() for f in linha.get("fotos", "").split(",") if f.strip()],
        })
    return jogos


def ler_jogos():
    _, linhas, separador = carregar_tabela()
    return montar_jogos(linhas), separador


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


def url_jogo(jogo):
    return f"jogo.html?id={quote(jogo['id'])}"


def html_linha_jogo(jogo, proximo):
    d = jogo["data"]
    selo = '<span class="selo selo-proximo">Próximo</span>' if proximo else '<span class="selo">Realizado</span>'
    local = f'\n                <span class="jogo-detalhe">{esc(jogo["local"])}</span>' if jogo["local"] else ""
    return f"""          <li>
            <a class="jogo" href="{url_jogo(jogo)}">
              <div class="jogo-data"><strong>{d.day:02d}</strong><span>{MESES[d.month - 1]}</span></div>
              <div>
                <span class="jogo-confronto">{confronto(jogo)}</span>
                <span class="jogo-detalhe">{esc(descricao_data(jogo))}</span>{local}
              </div>
              {selo}
            </a>
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
        f'<a class="destaque-jogo" href="{url_jogo(jogo)}">\n'
        f'          <span class="rotulo">{rotulo}</span>\n'
        f'          <strong>{confronto(jogo)}</strong>\n'
        f'          <span class="detalhe">{esc(descricao_data(jogo))}</span>\n'
        f'        </a>'
    )


# ---------------------------------------------------------------- JSON (página de cada jogo)

def json_jogos(jogos):
    dados = {}
    for jogo in sorted(jogos, key=lambda j: (j["data"], j["hora"]), reverse=True):
        placar = interpretar_placar(jogo["placar"])
        if placar:
            pro, contra = placar
            resultado = "vitoria" if pro > contra else "derrota" if pro < contra else "empate"
            placar_texto = f"{pro} x {contra}"
        else:
            pro = contra = None
            resultado = ""
            placar_texto = jogo["placar"]
        titulares, reservas, substituicoes, _ = montar_escalacao(jogo)
        dados[jogo["id"]] = {
            "id": jogo["id"],
            "data": jogo["data"].isoformat(),
            "data_br": jogo["data"].strftime("%d/%m/%Y"),
            "dia_semana": DIAS_SEMANA[jogo["data"].weekday()],
            "hora": jogo["hora"],
            "adversario": jogo["adversario"],
            "local": jogo["local"],
            "placar": placar_texto,
            "gols_pro": pro,
            "gols_contra": contra,
            "resultado": resultado,
            "titulares": titulares,
            "reservas": reservas,
            "substituicoes": substituicoes,
            "fotos": jogo["fotos"],
        }
    return json.dumps(dados, ensure_ascii=False, indent=2)


def gerar_json_jogos(jogos):
    novo = json_jogos(jogos)
    antigo = ARQUIVO_JSON.read_text(encoding="utf-8") if ARQUIVO_JSON.exists() else None
    if novo != antigo:
        ARQUIVO_JSON.write_text(novo, encoding="utf-8")
    print(f"  {ARQUIVO_JSON.name}: {'atualizado' if novo != antigo else 'já estava em dia'}")


# ---------------------------------------------------------------- escrita das páginas

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


# ---------------------------------------------------------------- CSS do cartão clicável

PAGINA_CSS = RAIZ / "css" / "estilo.css"
MARCA_CSS = "/* JOGO-LINK:INICIO */"
BLOCO_CSS = """
/* JOGO-LINK:INICIO */
/* Cartão de jogo inteiro clicável (acrescentado por atualizar_jogos.py) */
a.jogo {
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s ease, transform 0.15s ease;
}
a.jogo:hover { border-color: rgba(181, 122, 212, 0.55); transform: translateY(-1px); }
a.jogo:focus-visible { border-radius: 12px; }
/* JOGO-LINK:FIM */
"""


def garantir_css():
    """Acrescenta ao estilo.css o visual do cartão de jogo clicável, se ainda não estiver lá."""
    if not PAGINA_CSS.exists():
        print("Aviso: não encontrei css/estilo.css; o cartão de jogo ficará sem o estilo de link.")
        return
    texto = PAGINA_CSS.read_text(encoding="utf-8")
    if MARCA_CSS in texto:
        return
    PAGINA_CSS.write_text(texto.rstrip("\n") + "\n" + BLOCO_CSS, encoding="utf-8")
    print("  estilo.css: acrescentado o estilo do cartão de jogo clicável")


def avisos(jogos):
    for jogo in jogos:
        rotulo = f"{jogo['data'].strftime('%d/%m/%Y')} x {jogo['adversario']}"
        if jogo["placar"] and not interpretar_placar(jogo["placar"]):
            print(f"Aviso: placar '{jogo['placar']}' ({rotulo}) não está no formato '2 x 1'.")

        for texto in jogo["escalacao"] + jogo["reservas"]:
            suporte = interpretar_suporte(texto)
            if suporte and no_elenco_exato(suporte[0]):
                print(f"Aviso: {rotulo}: {suporte[0]} está no elenco; tire o '(suporte)' dele.")

        titulares, reservas, _, problemas = montar_escalacao(jogo)
        for p in problemas:
            print(f"Aviso: escalação de {rotulo}: {p}.")
        repetidos = [e["nome"] for e in resolver_lista(jogo["reservas"])[0]
                     if chave_entrada(e) in {chave_entrada(t) for t in titulares}]
        if repetidos:
            print(f"Aviso: {rotulo}: {', '.join(repetidos)} está nos titulares e nas reservas (ficará só nos titulares).")
        if len(titulares) > 11:
            print(f"Aviso: {rotulo}: {len(titulares)} jogadores nos titulares.")
        for foto in jogo["fotos"]:
            if not (PASTA_FOTOS_JOGOS / jogo["id"] / foto).exists():
                print(f"Aviso: foto não encontrada em imagens/jogos/{jogo['id']}/{foto} ({rotulo}).")


def atualizar_paginas(jogos, hoje=None):
    hoje = hoje or date.today()
    avisos(jogos)
    mudou_jogos = substituir_bloco(PAGINA_JOGOS, "JOGOS", html_pagina_jogos(jogos, hoje))
    mudou_inicio = substituir_bloco(PAGINA_INICIO, "PROXIMO", html_destaque(jogos, hoje))
    proximos, realizados = separar(jogos, hoje)
    print(f"{len(jogos)} jogos no jogos.csv: {len(proximos)} próximos, {len(realizados)} realizados.")
    print(f"  {PAGINA_JOGOS.name}: {'atualizado' if mudou_jogos else 'já estava em dia'}")
    print(f"  {PAGINA_INICIO.name}: {'atualizado' if mudou_inicio else 'já estava em dia'}")
    gerar_json_jogos(jogos)
    garantir_css()
    if not (RAIZ / "jogo.html").exists():
        print("Aviso: não encontrei jogo.html na raiz do site (é a página de cada jogo).")


# ---------------------------------------------------------------- perguntas interativas

def v_data(texto, atual):
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).strftime("%d/%m/%Y")
        except ValueError:
            pass
    raise ValueError("Data inválida. Exemplo: 25/10/2026")


def v_hora(texto, atual):
    m = re.fullmatch(r"(\d{1,2})\s*(?:[:hH]\s*(\d{2})?)?", texto.strip())
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h <= 23 and mi <= 59:
            return f"{h:02d}:{mi:02d}"
    raise ValueError("Horário inválido. Exemplo: 10:00")


def v_placar(texto, atual):
    placar = interpretar_placar(texto)
    if not placar:
        raise ValueError("Use o formato nossos x deles, ex.: 2 x 1 (nosso gol primeiro).")
    return f"{placar[0]} x {placar[1]}"


def v_lista_jogo(texto, atual):
    """Titulares ou reservas: confere com o elenco e oferece cadastrar como suporte quem não está nele."""
    saida, vistos = [], set()
    for item in separar_lista(texto):
        suporte = interpretar_suporte(item)
        if suporte:
            nome, posicao = suporte
            if no_elenco_exato(nome):
                print(f"    Aviso: {nome} já está no elenco; sem o '(suporte)' ele aparece com camisa e perfil.")
            texto_item = formatar_suporte(nome, posicao)
        else:
            pessoa, motivo = resolver_jogador(item)
            if pessoa is not None:
                texto_item = pessoa["nome"]
            elif "mais de um" in motivo:
                raise ValueError(motivo[0].upper() + motivo[1:] + ".")
            else:
                resposta = input(f"    '{item}' não está no elenco. Adicionar como suporte? (s/N): ").strip().lower()
                if resposta != "s":
                    raise ValueError("Confira o nome/camisa, ou escreva 'Nome (suporte)' para quem não é do elenco.")
                posicao = input("    Posição do suporte (opcional, ex.: Goleiro): ").strip()
                texto_item = formatar_suporte(item, posicao)
        chave = sem_acento(texto_item)
        if chave not in vistos:
            vistos.add(chave)
            saida.append(texto_item)
    return ", ".join(saida)


def v_substituicoes_factory(linha):
    def validar(texto, atual):
        titulares, _ = resolver_lista(separar_lista(linha.get("escalacao", "")))
        reservas, _ = resolver_lista(separar_lista(linha.get("reservas", "")))
        nos_titulares = {chave_entrada(e) for e in titulares}
        reservas = [e for e in reservas if chave_entrada(e) not in nos_titulares]
        pares, problemas = resolver_substituicoes(separar_lista(texto), titulares, reservas)
        if problemas:
            raise ValueError(problemas[0][0].upper() + problemas[0][1:] + ".")
        return ", ".join(texto_substituicao(p) for p in pares)
    return validar


def perguntar(rotulo, atual=None, validar=None, obrigatorio=False):
    """
    atual=None  -> cadastro novo (Enter deixa vazio, se não for obrigatório).
    atual="..." -> edição (Enter mantém; "-" apaga).
    """
    editando = atual is not None
    if editando:
        prompt = f"  {rotulo} [{atual if atual != '' else 'vazio'}] (Enter mantém, - apaga): "
    else:
        prompt = f"  {rotulo}{'' if obrigatorio else ' (opcional)'}: "

    while True:
        resposta = input(prompt).strip()
        if resposta == "":
            if editando:
                return atual
            if obrigatorio:
                print("    Esse campo é obrigatório.")
                continue
            return ""
        if resposta == "-" and editando:
            if obrigatorio:
                print("    Esse campo é obrigatório, não dá para apagar.")
                continue
            return ""
        if validar:
            try:
                return validar(resposta, atual)
            except ValueError as e:
                print(f"    {e}")
                continue
        return resposta


def fotos_da_pasta(id_jogo):
    pasta = PASTA_FOTOS_JOGOS / id_jogo
    if not pasta.is_dir():
        return []
    arquivos = [p.name for p in pasta.iterdir() if p.suffix.lower() in EXTENSOES_IMAGEM]
    return sorted(arquivos, key=ordem_natural)


def id_da_linha(linha):
    try:
        return id_base(converter_data(linha.get("data", ""), linha.get("_linha", 0)), linha.get("adversario", ""))
    except SystemExit:
        return ""


def mostrar_elenco():
    pessoas = [p for p in elenco() if p["numero"]]
    if pessoas:
        print("  Elenco: " + " | ".join(f"{p['numero']} {p['nome']}" for p in pessoas))


def perguntar_escalacao(linha, novo):
    mostrar_elenco()
    print("  (nomes ou camisas separados por vírgula; quem não é do elenco entra como suporte)")
    linha["escalacao"] = perguntar("Titulares", None if novo else linha.get("escalacao", ""), v_lista_jogo)
    linha["reservas"] = perguntar("Reservas", None if novo else linha.get("reservas", ""), v_lista_jogo)
    if linha["reservas"] or linha.get("substituicoes"):
        print("  (substituições: 'Quem entrou > Quem saiu', na ordem em que aconteceram, com minuto opcional.")
        print("   Ex.: Rulim > Jonas 80', Paiva > Heitor 45+2')")
        linha["substituicoes"] = perguntar("Substituições", None if novo else linha.get("substituicoes", ""),
                                           v_substituicoes_factory(linha))
    else:
        linha["substituicoes"] = ""
    nos_titulares = {sem_acento(interpretar_suporte(n)[0] if interpretar_suporte(n) else n)
                     for n in separar_lista(linha["escalacao"])}
    repetidos = [n for n in separar_lista(linha["reservas"])
                 if sem_acento(interpretar_suporte(n)[0] if interpretar_suporte(n) else n) in nos_titulares]
    if repetidos:
        print(f"  Aviso: {', '.join(repetidos)} está nos titulares e nas reservas.")
    if len(separar_lista(linha["escalacao"])) > 11:
        print("  Aviso: mais de 11 jogadores nos titulares.")


def v_fotos_factory(linha):
    def validar(texto, atual):
        if sem_acento(texto) == "auto":
            id_jogo = id_da_linha(linha)
            achadas = fotos_da_pasta(id_jogo)
            if not achadas:
                raise ValueError(f"Não achei fotos em imagens/jogos/{id_jogo}/.")
            print(f"    Fotos encontradas: {', '.join(achadas)}")
            return ", ".join(achadas)
        return ", ".join(p.strip() for p in texto.replace("|", ",").split(",") if p.strip())
    return validar


def preencher(linha, novo):
    """Pergunta os campos de um jogo e grava as respostas em `linha` (ainda na memória)."""
    def atual(campo):
        return None if novo else linha.get(campo, "")

    linha["data"] = perguntar("Data (DD/MM/AAAA)", atual("data"), v_data, obrigatorio=True)
    linha["hora"] = perguntar("Horário (ex.: 10:00)", atual("hora"), v_hora, obrigatorio=novo)
    linha["adversario"] = perguntar("Adversário", atual("adversario"), obrigatorio=True)
    linha["local"] = perguntar("Local", atual("local"))
    linha["placar"] = perguntar("Placar, se já aconteceu (ex.: 2 x 1)", atual("placar"), v_placar)
    perguntar_escalacao(linha, novo)
    id_jogo = id_da_linha(linha)
    linha["fotos"] = perguntar(
        f"Fotos do jogo, na pasta imagens/jogos/{id_jogo}/ (ex.: 1.jpeg, 2.jpeg ou 'auto')",
        atual("fotos"), v_fotos_factory(linha))
    return linha


def ordenar_linhas(linhas):
    def chave(l):
        try:
            return (converter_data(l.get("data", ""), 0), l.get("hora", ""))
        except SystemExit:
            return (date.min, "")
    return sorted(linhas, key=chave, reverse=True)


def mostrar_lista(ordenadas):
    print()
    for i, l in enumerate(ordenadas, start=1):
        placar = l.get("placar") or "-"
        info = []
        if l.get("escalacao"):
            info.append(f"{len(separar_lista(l['escalacao']))} titulares")
        if l.get("substituicoes"):
            info.append(f"{len(separar_lista(l['substituicoes']))} subst.")
        if l.get("fotos"):
            info.append(f"{len([f for f in l['fotos'].split(',') if f.strip()])} fotos")
        extra = f"  [{', '.join(info)}]" if info else ""
        print(f"  {i:>2}) {l.get('data', ''):<11}{l.get('hora', ''):<6} {l.get('adversario', ''):<24} {placar:<7}{extra}")
    print()


def escolher_jogo(linhas, termo):
    ordenadas = ordenar_linhas(linhas)
    termo = termo.strip()
    if not termo:
        return None
    if termo.isdigit():
        n = int(termo)
        if 1 <= n <= len(ordenadas):
            return ordenadas[n - 1]
        print("  Número fora da lista.")
        return None
    t = sem_acento(termo)
    achados = [l for l in ordenadas
               if t in sem_acento(l.get("adversario", "")) or t in l.get("data", "") or t in id_da_linha(l)]
    if not achados:
        print("  Nenhum jogo encontrado.")
        return None
    if len(achados) == 1:
        return achados[0]
    print("  Mais de um jogo encontrado:")
    mostrar_lista(achados)
    escolha = input("  Qual deles? (número da lista acima, Enter cancela): ").strip()
    if escolha.isdigit() and 1 <= int(escolha) <= len(achados):
        return achados[int(escolha) - 1]
    return None


def titulo_jogo(linha):
    return f"{linha.get('data', '')} - {NOSSO_TIME} x {linha.get('adversario', '')}"


# ---------------------------------------------------------------- comandos

def cmd_listar():
    _, linhas, _ = carregar_tabela()
    montar_jogos(linhas)  # valida
    mostrar_lista(ordenar_linhas(linhas))


def cmd_novo():
    colunas, linhas, separador = carregar_tabela()
    print("Novo jogo (Ctrl+C para cancelar)")
    linha = {c: "" for c in colunas}
    linha["_linha"] = len(linhas) + 2
    preencher(linha, novo=True)
    linhas.append(linha)
    salvar_tabela(colunas, linhas, separador)
    print(f"\nJogo salvo no jogos.csv: {titulo_jogo(linha)}")
    id_jogo = id_da_linha(linha)
    if not linha.get("fotos"):
        print(f"Para o carrossel, coloque as fotos em imagens/jogos/{id_jogo}/ e depois rode --fotos.")


def cmd_editar(busca=""):
    colunas, linhas, separador = carregar_tabela()
    print("Editar jogos (Ctrl+C cancela o jogo atual; o que já foi salvo fica)")
    termo = busca
    while True:
        if not termo:
            mostrar_lista(ordenar_linhas(linhas))
            termo = input("Número da lista, adversário ou data (Enter para encerrar): ").strip()
            if not termo:
                break
        linha = escolher_jogo(linhas, termo)
        termo = ""
        if not linha:
            continue
        print(f"\n{titulo_jogo(linha)}")
        preencher(linha, novo=False)
        salvar_tabela(colunas, linhas, separador)
        print("  Jogo salvo.")


def cmd_placar():
    colunas, linhas, separador = carregar_tabela()
    print("Lançar placar (nosso gol primeiro, ex.: 2 x 1). Enter no jogo encerra.")
    while True:
        mostrar_lista(ordenar_linhas(linhas))
        termo = input("Número da lista, adversário ou data: ").strip()
        if not termo:
            break
        linha = escolher_jogo(linhas, termo)
        if not linha:
            continue
        print(f"\n{titulo_jogo(linha)}")
        linha["placar"] = perguntar("Placar", linha.get("placar", ""), v_placar)
        salvar_tabela(colunas, linhas, separador)
        print("  Placar salvo.")


def cmd_escalacao(busca=""):
    colunas, linhas, separador = carregar_tabela()
    termo = busca
    while True:
        if not termo:
            mostrar_lista(ordenar_linhas(linhas))
            termo = input("Número da lista, adversário ou data (Enter para encerrar): ").strip()
            if not termo:
                break
        linha = escolher_jogo(linhas, termo)
        termo = ""
        if not linha:
            continue
        print(f"\n{titulo_jogo(linha)}")
        perguntar_escalacao(linha, novo=False)
        salvar_tabela(colunas, linhas, separador)
        print("  Escalação salva.")


def cmd_remover(busca=""):
    colunas, linhas, separador = carregar_tabela()
    termo = busca
    if not termo:
        mostrar_lista(ordenar_linhas(linhas))
        termo = input("Número da lista, adversário ou data de quem remover (Enter cancela): ").strip()
    linha = escolher_jogo(linhas, termo) if termo else None
    if not linha:
        print("Nada foi alterado.")
        return
    print(f"\n{titulo_jogo(linha)}")
    if input("  Remover este jogo? Digite 's' para confirmar: ").strip().lower() != "s":
        print("Nada foi alterado.")
        return
    linhas.remove(linha)
    salvar_tabela(colunas, linhas, separador)
    print("Jogo removido do jogos.csv. (As fotos em imagens/ não são apagadas.)")


def cmd_fotos():
    colunas, linhas, separador = carregar_tabela()
    if not PASTA_FOTOS_JOGOS.exists():
        print("Pasta imagens/jogos/ não encontrada, nada a fazer.")
        return
    mudou = False
    for linha in linhas:
        achadas = fotos_da_pasta(id_da_linha(linha))
        if not achadas:
            continue
        texto = ", ".join(achadas)
        if linha.get("fotos", "") != texto:
            linha["fotos"] = texto
            mudou = True
            print(f"  {titulo_jogo(linha)}: {len(achadas)} fotos ({texto})")
    if mudou:
        salvar_tabela(colunas, linhas, separador)
    else:
        print("A coluna fotos já estava de acordo com as pastas de imagens/jogos/.")


def principal():
    parser = argparse.ArgumentParser(
        description="Gerencia os jogos: atualiza jogos.html, index.html e jogos.json a partir do jogos.csv.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--novo", action="store_true", help="cadastra um jogo")
    grupo.add_argument("--editar", nargs="?", const="", default=None, metavar="JOGO",
                       help="edita qualquer dado de um jogo (adversário, data ou número da lista opcional)")
    grupo.add_argument("--placar", action="store_true", help="lança o placar de um jogo")
    grupo.add_argument("--escalacao", nargs="?", const="", default=None, metavar="JOGO",
                       help="define titulares, reservas e substituições de um jogo")
    grupo.add_argument("--fotos", action="store_true", help="preenche a coluna fotos lendo as pastas imagens/jogos/<id>/")
    grupo.add_argument("--remover", nargs="?", const="", default=None, metavar="JOGO", help="remove um jogo")
    grupo.add_argument("--listar", action="store_true", help="mostra todos os jogos, sem alterar nada")
    args = parser.parse_args()

    if args.listar:
        cmd_listar()
        return

    try:
        if args.novo:
            cmd_novo()
        elif args.editar is not None:
            cmd_editar(args.editar)
        elif args.placar:
            cmd_placar()
        elif args.escalacao is not None:
            cmd_escalacao(args.escalacao)
        elif args.fotos:
            cmd_fotos()
        elif args.remover is not None:
            cmd_remover(args.remover)
    except (KeyboardInterrupt, EOFError):
        print("\nInterrompido. O que já tinha sido salvo foi mantido.")

    jogos, _ = ler_jogos()
    atualizar_paginas(jogos)


if __name__ == "__main__":
    principal()
