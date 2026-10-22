"""
site_petalas - biblioteca para gerenciar o site do time (elenco, jogos, páginas HTML e JSON).

Junta o que antes eram dois scripts (atualizar_elenco.py e atualizar_jogos.py) em um único módulo
importável. Os CSVs continuam sendo o "banco de dados"; a biblioteca lê, altera e regrava os CSVs e
gera elenco.html, jogos.html, o destaque do index.html e os arquivos jogadores.json / jogos.json.

Diferenças em relação aos scripts:
  - nada de input()/print()/sys.exit(): tudo é chamada de função/método;
  - erros viram exceções (ErroDados e subclasses) e avisos são devolvidos como lista de textos;
  - os caminhos são configuráveis (classe Site).

Exemplo:

    from site_petalas import Site, ErroDados

    site = Site("/caminho/do/site")             # raiz com index.html; CSVs em <raiz>/dados/
    site.adicionar_jogo("31/10/2026", "Time X", hora="10:00", local="Campo 1")
    site.definir_placar("Time X", "2 x 1")
    site.definir_escalacao("Time X", titulares=["Henrico", 12, "Fulano (suporte, Goleiro)"],
                           reservas=["Ivan"], substituicoes=["Ivan > Henrico 60'"])
    site.definir_gols("Time X", ["Rulim 23' (ast. Paiva)", "adv 40'", "Novaes 70'"])
    site.atualizar_estatisticas("Rulim", gols="+1", jogos="+1")
    relatorio = site.atualizar_tudo()           # regrava HTMLs e JSONs
    print(relatorio["avisos"])

Só usa a biblioteca padrão (Python 3.8+).
"""

from __future__ import annotations

import csv
import html
import json
import re
import unicodedata
import zipfile
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import quote

__all__ = [
    "Site", "ErroDados", "ErroNaoEncontrado", "ErroAmbiguo", "ErroArquivo",
    "slug", "sem_acento",
]

COLUNAS_FINANCAS = ["data", "tipo", "nome", "descricao", "valor"]

ARQUIVO_CONFIG_MENSALIDADE = "config_mensalidade.json"
ARQUIVO_MENSALIDADES = "mensalidades.json"

# ====================================================================== exceções


class ErroDados(ValueError):
    """Dado inválido (csv, campo, formato...)."""


class ErroArquivo(ErroDados):
    """Arquivo ou marcador de página ausente."""


class ErroNaoEncontrado(ErroDados):
    """Pessoa ou jogo não encontrado."""


class ErroAmbiguo(ErroDados):
    """A busca bateu com mais de um registro."""


# ====================================================================== constantes

EXTENSOES_IMAGEM = {".jpeg", ".jpg", ".png", ".webp"}
NOSSO_TIME_PADRAO = "Pétalas Negras"

ESTATISTICAS = [
    ("jogos", "Jogos", "Jogos"),
    ("gols", "Gols", "Gols"),
    ("assistencias", "Assistências", "Assist."),
]
COLUNAS_ELENCO = ["numero", "nome", "posicao", "foto", "jogos", "gols", "assistencias",
                  "idade", "pe", "altura", "titulos", "formacao", "fotos_jogo"]
COLUNAS_JOGOS = ["data", "hora", "adversario", "local", "placar", "escalacao", "reservas",
                 "substituicoes", "fotos", "gols"]
COLUNAS_JOGOS_OBRIGATORIAS = COLUNAS_JOGOS[:4]

GRUPOS = [
    ("goleiro", "Goleiros", ["goleiro", "goleira"]),
    ("zagueiro", "Zagueiros", ["zagueiro", "zagueira", "defensor", "libero"]),
    ("lateral", "Laterais", ["lateral"]),
    ("meio", "Meio-campo", ["volante", "meio", "meia", "armador"]),
    ("ataque", "Ataque", ["ataque", "atacante", "centroavante", "ponta", "pivo"]),
    ("tecnico", "Comissão técnica / Staff",
     ["tecnico", "treinador", "comissao", "preparador", "auxiliar", "fotografo", "fotografa"]),
]
ORDEM_GRUPOS = [g for g, _, _ in GRUPOS]
GRUPO_STAFF = "tecnico"
# valor do data-posicao no HTML (botões de filtro do elenco.html)
FILTROS = {"goleiro": "goleiros", "zagueiro": "zagueiros", "lateral": "laterais",
           "meio": "meio-campo", "ataque": "ataque", "tecnico": "comissao"}

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

PADRAO_SUPORTE = re.compile(r"(.+?)\s*\(\s*suporte\s*(?:[,;:\-]\s*(.*?))?\s*\)", re.IGNORECASE)
PADRAO_SUBSTITUICAO = re.compile(r"(.+?)\s*(?:>|→|\bpor\b)\s*(.+)", re.IGNORECASE)
_MIN = r"(\d{1,3}(?:\s*\+\s*\d{1,2})?)"
PADRAO_MINUTO = re.compile(
    rf"^(?P<resto>.*?)(?:\s*\(\s*{_MIN}\s*['′’]?\s*\)|\s+{_MIN}\s*['′’])\s*$")
PADRAO_MINUTO_GOL = re.compile(r"^(?P<resto>.*?)\s+(?P<min>\d{1,3}(?:\s*\+\s*\d{1,2})?)\s*['′’]\s*$")
PADRAO_PREFIXO_ASSIST = re.compile(r"^(?:ast|assist(?:[eê]ncia)?)(?:\.\s*|:\s*|\s+)", re.IGNORECASE)
NOMES_ADVERSARIO = {"adv", "adversario", "contra"}

MARCA_CSS = "/* JOGO-LINK:INICIO */"
BLOCO_CSS = """
/* JOGO-LINK:INICIO */
/* Cartão de jogo inteiro clicável (acrescentado por site_petalas) */
a.jogo {
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s ease, transform 0.15s ease;
}
a.jogo:hover { border-color: rgba(181, 122, 212, 0.55); transform: translateY(-1px); }
a.jogo:focus-visible { border-radius: 12px; }
/* JOGO-LINK:FIM */
"""

Lista = Union[str, Sequence[Any], None]

# ====================================================================== utilitários gerais


def sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


def slug(nome: str) -> str:
    """Identificador do perfil (jogador.html?id=...) e da pasta imagens/perfil/<slug>/."""
    return sem_acento(nome).strip().replace(" ", "-")


def _esc(texto: str) -> str:
    return html.escape(texto, quote=True)


def _ordem_natural(texto: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", texto)]


def _descobrir_grupo(*textos: str) -> Optional[str]:
    for texto in textos:
        normal = sem_acento(texto or "")
        if not normal:
            continue
        for id_grupo, _, palavras in GRUPOS:
            if any(p in normal for p in palavras):
                return id_grupo
    return None


def _separar_lista(texto: str) -> List[str]:
    """Separa por vírgula (ou |) sem quebrar o que está entre parênteses."""
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


def _como_lista(valor: Lista) -> List[str]:
    """Aceita texto 'a, b' ou lista [a, b, 12] e devolve lista de textos."""
    if valor is None:
        return []
    if isinstance(valor, str):
        return _separar_lista(valor)
    return [str(v).strip() for v in valor if str(v).strip()]


def _fotos_da_pasta(pasta: Path) -> List[str]:
    if not pasta.is_dir():
        return []
    return sorted((p.name for p in pasta.iterdir() if p.suffix.lower() in EXTENSOES_IMAGEM),
                  key=_ordem_natural)


# ---------------------------------------------------------------------- csv


def _detectar_separador(texto: str) -> str:
    primeira = texto.splitlines()[0] if texto.strip() else ""
    return ";" if primeira.count(";") >= primeira.count(",") else ","


def _ler_csv(arquivo: Path, obrigatorias: Sequence[str] = ()):
    if not arquivo.exists():
        raise ErroArquivo(f"não encontrei {arquivo.name} em {arquivo.parent}.")
    texto = arquivo.read_text(encoding="utf-8-sig")
    separador = _detectar_separador(texto)
    leitor = csv.DictReader(texto.splitlines(), delimiter=separador)
    if not leitor.fieldnames:
        raise ErroArquivo(f"o {arquivo.name} está vazio.")
    colunas = [sem_acento(c.strip()) for c in leitor.fieldnames]
    faltando = [c for c in obrigatorias if c not in colunas]
    if faltando:
        raise ErroArquivo(f"faltam colunas no {arquivo.name}: {', '.join(faltando)}.")
    linhas = []
    for numero, bruto in enumerate(leitor, start=2):
        linha = {sem_acento((k or "").strip()): (v or "").strip() for k, v in bruto.items()}
        if not any(linha.values()):
            continue
        linha["_linha"] = numero
        linhas.append(linha)
    return colunas, linhas, separador


def _gravar_csv(arquivo: Path, colunas, linhas, separador, padrao) -> None:
    colunas = list(colunas)
    for c in padrao:
        if c not in colunas:
            colunas.append(c)
    saida = StringIO()
    escritor = csv.DictWriter(saida, fieldnames=colunas, delimiter=separador,
                              lineterminator="\n", extrasaction="ignore", restval="")
    escritor.writeheader()
    escritor.writerows(linhas)
    arquivo.write_text(saida.getvalue(), encoding="utf-8")


def _substituir_bloco(arquivo: Path, nome: str, novo_conteudo: str) -> bool:
    """Troca o que está entre <!-- NOME:INICIO --> e <!-- NOME:FIM -->. Devolve True se mudou."""
    if not arquivo.exists():
        raise ErroArquivo(f"não encontrei {arquivo.name} em {arquivo.parent}.")
    texto = arquivo.read_text(encoding="utf-8")
    padrao = re.compile(rf"(<!-- {nome}:INICIO -->)(.*?)(<!-- {nome}:FIM -->)", re.DOTALL)
    if not padrao.search(texto):
        raise ErroArquivo(f"{arquivo.name} não tem os marcadores <!-- {nome}:INICIO --> e <!-- {nome}:FIM -->.")
    novo = padrao.sub(lambda m: f"{m.group(1)}\n        {novo_conteudo}\n        {m.group(3)}", texto, count=1)
    if novo != texto:
        arquivo.write_text(novo, encoding="utf-8")
        return True
    return False


# ====================================================================== normalizadores de campos
# Recebem o texto e devolvem o valor normalizado; levantam ErroDados se inválido.


def normalizar_posicao(texto: str) -> str:
    if _descobrir_grupo(texto) is None:
        raise ErroDados("Posição não reconhecida. Exemplos: Goleiro, Zagueiro, Lateral direito, "
                        "Volante, Meio-campista, Ponta, Centroavante, Técnico, Fotógrafo.")
    return texto.strip()


def normalizar_inteiro(valor: Any) -> str:
    texto = str(valor).strip()
    if not texto.isdigit():
        raise ErroDados(f"'{valor}': use apenas um número inteiro (0 ou mais).")
    return str(int(texto))


def normalizar_estatistica(valor: Any, atual: str = "") -> str:
    """Número define o valor; '+N' soma ao atual."""
    texto = str(valor).strip()
    if texto.startswith("+"):
        if not texto[1:].isdigit():
            raise ErroDados("Depois do + coloque um número inteiro, ex.: +1")
        return str(int(atual or 0) + int(texto[1:]))
    return normalizar_inteiro(texto)


def normalizar_altura(valor: Any) -> str:
    try:
        v = float(str(valor).lower().replace("m", "").replace(",", ".").strip())
    except ValueError:
        raise ErroDados("Altura em metros, ex.: 1.75")
    if not 0.5 <= v <= 2.5:
        raise ErroDados("Altura em metros, ex.: 1.75")
    return f"{v:.2f}"


def normalizar_pe(texto: str) -> str:
    n = sem_acento(texto)
    for inicio, valor in (("dest", "Destro"), ("d", "Destro"), ("canh", "Canhoto"), ("c", "Canhoto"),
                          ("ambi", "Ambidestro"), ("a", "Ambidestro")):
        if n.startswith(inicio):
            return valor
    raise ErroDados("Use Destro, Canhoto ou Ambidestro (ou só D, C, A).")


def normalizar_data(texto: Any) -> str:
    if isinstance(texto, (date, datetime)):
        return texto.strftime("%d/%m/%Y")
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(texto).strip(), formato).strftime("%d/%m/%Y")
        except ValueError:
            pass
    raise ErroDados(f"Data inválida '{texto}'. Exemplo: 25/10/2026")


def normalizar_hora(texto: str) -> str:
    m = re.fullmatch(r"(\d{1,2})\s*(?:[:hH]\s*(\d{2})?)?", str(texto).strip())
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h <= 23 and mi <= 59:
            return f"{h:02d}:{mi:02d}"
    raise ErroDados(f"Horário inválido '{texto}'. Exemplo: 10:00")


def interpretar_placar(texto: Optional[str]) -> Optional[Tuple[int, int]]:
    """'2 x 1' -> (2, 1); None se não for um placar."""
    m = re.fullmatch(r"\s*(\d+)\s*[xX×-]\s*(\d+)\s*", texto or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def normalizar_placar(texto: Any) -> str:
    if isinstance(texto, tuple):
        texto = f"{texto[0]} x {texto[1]}"
    p = interpretar_placar(str(texto))
    if not p:
        raise ErroDados("Use o formato nossos x deles, ex.: 2 x 1 (nosso gol primeiro).")
    return f"{p[0]} x {p[1]}"


# ====================================================================== jogos: parsing (puro)


def _converter_data(texto: str, numero_linha: Any = "?") -> date:
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            pass
    raise ErroDados(f"jogos.csv, linha {numero_linha}: data inválida '{texto}'. Use DD/MM/AAAA.")


def _id_base(data: date, adversario: str) -> str:
    nome = re.sub(r"[^a-z0-9]+", "-", sem_acento(adversario)).strip("-")
    return f"{data.isoformat()}-{nome}" if nome else data.isoformat()


def _formatar_suporte(nome: str, posicao: str = "") -> str:
    return f"{nome} (suporte, {posicao})" if posicao else f"{nome} (suporte)"


def _interpretar_suporte(texto: str):
    m = PADRAO_SUPORTE.fullmatch(texto.strip())
    return (m.group(1).strip(), (m.group(2) or "").strip()) if m else None


def _formatar_minuto(numero: str) -> str:
    return re.sub(r"\s+", "", numero) + "'"


def _separar_minuto(texto: str):
    m = PADRAO_MINUTO.match(texto.strip())
    if not m:
        return texto.strip(), ""
    return m.group("resto").strip(), _formatar_minuto(m.group(2) or m.group(3))


def _nova_entrada(nome, numero, posicao, slug_, suporte):
    return {"nome": nome, "numero": numero, "posicao": posicao, "grupo": _descobrir_grupo(posicao) or "",
            "slug": slug_, "suporte": suporte, "entrou_por": None, "saiu_para": None, "minuto": None}


def _resolver_jogador(texto: str, pessoas: List[dict]):
    """Acha alguém do elenco por camisa ou nome. Devolve (pessoa, None) ou (None, motivo)."""
    if not pessoas:
        return None, "não encontrei o elenco.csv para conferir os nomes"
    t = sem_acento(str(texto)).strip()
    if t.isdigit():
        achados = [p for p in pessoas if p["numero"] == str(int(t))]
    else:
        achados = [p for p in pessoas if sem_acento(p["nome"]) == t]
        if not achados:
            achados = [p for p in pessoas if t and t in sem_acento(p["nome"])]
    if not achados:
        return None, f"ninguém no elenco com nome ou camisa '{texto}'"
    if len(achados) > 1:
        return None, (f"'{texto}' bate com mais de um jogador ({', '.join(p['nome'] for p in achados)}); "
                      "escreva o nome completo ou a camisa")
    return achados[0], None


def _resolver_entrada(texto: str, pessoas):
    suporte = _interpretar_suporte(texto)
    if suporte:
        return _nova_entrada(suporte[0], None, suporte[1], None, True), None
    pessoa, motivo = _resolver_jogador(texto, pessoas)
    if pessoa is None:
        return None, motivo
    numero = int(pessoa["numero"]) if pessoa["numero"].isdigit() else None
    return _nova_entrada(pessoa["nome"], numero, pessoa["posicao"], pessoa["slug"], False), None


def _chave_entrada(e) -> str:
    return e["slug"] or "suporte:" + sem_acento(e["nome"]).strip()


def _ordenar_entradas(entradas):
    def chave(e):
        g = ORDEM_GRUPOS.index(e["grupo"]) if e["grupo"] in ORDEM_GRUPOS else len(ORDEM_GRUPOS)
        return (g, e["numero"] if e["numero"] is not None else 9999, sem_acento(e["nome"]))
    return sorted(entradas, key=chave)


def _resolver_lista(textos, pessoas):
    entradas, problemas, vistos = [], [], set()
    for texto in textos:
        entrada, motivo = _resolver_entrada(texto, pessoas)
        if entrada is None:
            problemas.append(motivo)
        elif _chave_entrada(entrada) not in vistos:
            vistos.add(_chave_entrada(entrada))
            entradas.append(entrada)
    return _ordenar_entradas(entradas), problemas


def _achar_na_lista(texto: str, entradas):
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


def _resolver_substituicoes(textos, titulares, reservas):
    pares, problemas = [], []
    em_campo, banco = list(titulares), list(reservas)
    for texto in textos:
        corpo, minuto = _separar_minuto(texto)
        m = PADRAO_SUBSTITUICAO.fullmatch(corpo)
        if not m:
            problemas.append(f"substituição '{texto}': use o formato 'Quem entrou > Quem saiu' (minuto opcional: 80')")
            continue
        entrou, motivo = _achar_na_lista(m.group(1), banco)
        if entrou is None:
            problemas.append(f"substituição '{texto}': quem entrou ({m.group(1).strip()}) precisa estar "
                             f"nas reservas e ainda no banco; {motivo}")
            continue
        saiu, motivo = _achar_na_lista(m.group(2), em_campo)
        if saiu is None:
            problemas.append(f"substituição '{texto}': quem saiu ({m.group(2).strip()}) precisa estar em campo; {motivo}")
            continue
        banco.remove(entrou)
        em_campo.remove(saiu)
        em_campo.append(entrou)
        saiu["saiu_para"] = entrou["nome"]
        entrou["entrou_por"] = saiu["nome"]
        if minuto:
            saiu["minuto"] = entrou["minuto"] = minuto
        pares.append({"entrou": entrou["nome"], "saiu": saiu["nome"], "minuto": minuto})
    return pares, problemas


def _texto_substituicao(par) -> str:
    base = f"{par['entrou']} > {par['saiu']}"
    return f"{base} {par['minuto']}" if par.get("minuto") else base


def _montar_escalacao(jogo, pessoas):
    titulares, p1 = _resolver_lista(jogo["escalacao"], pessoas)
    reservas, p2 = _resolver_lista(jogo["reservas"], pessoas)
    nos_titulares = {_chave_entrada(e) for e in titulares}
    reservas = [e for e in reservas if _chave_entrada(e) not in nos_titulares]
    pares, p3 = _resolver_substituicoes(jogo["substituicoes"], titulares, reservas)
    return titulares, reservas, pares, p1 + p2 + p3


# ---- gols


def _parenteses_final(texto: str):
    t = texto.strip()
    if not t.endswith(")"):
        return t, ""
    nivel = 0
    for i in range(len(t) - 1, -1, -1):
        if t[i] == ")":
            nivel += 1
        elif t[i] == "(":
            nivel -= 1
            if nivel == 0:
                return t[:i].strip(), t[i + 1:-1].strip()
    return t, ""


def _interpretar_gol(texto: str):
    t = texto.strip()
    resto, dentro = _parenteses_final(t)
    if dentro and sem_acento(dentro).startswith("suporte"):
        resto, dentro = t, ""
    assistencia = PADRAO_PREFIXO_ASSIST.sub("", dentro).strip()
    m = PADRAO_MINUTO_GOL.match(resto)
    if m:
        autor, minuto = m.group("resto").strip(), _formatar_minuto(m.group("min"))
    else:
        autor, minuto = resto.strip(), ""
    return {"autor": autor, "assistencia": assistencia, "minuto": minuto}


def _ordem_minuto(minuto: str):
    m = re.fullmatch(r"(\d+)(?:\+(\d+))?['′’]", minuto or "")
    return int(m.group(1)) + int(m.group(2) or 0) / 100 if m else None


def _pessoa_do_gol(texto: str, pessoas):
    suporte = _interpretar_suporte(texto)
    if suporte:
        return {"nome": suporte[0], "numero": None, "posicao": suporte[1], "slug": None, "suporte": True}, None
    pessoa, motivo = _resolver_jogador(texto, pessoas)
    if pessoa is None:
        return None, motivo
    numero = int(pessoa["numero"]) if pessoa["numero"].isdigit() else None
    return {"nome": pessoa["nome"], "numero": numero, "posicao": pessoa["posicao"],
            "slug": pessoa["slug"], "suporte": False}, None


def _eh_gol_do_adversario(autor: str, adversario: str) -> bool:
    return sem_acento(autor).strip() in (NOMES_ADVERSARIO | {sem_acento(adversario).strip()})


def _resolver_gols(textos, adversario, pessoas):
    gols, problemas = [], []
    for texto in textos:
        d = _interpretar_gol(texto)
        if _eh_gol_do_adversario(d["autor"], adversario):
            gols.append({"time": "adversario", "minuto": d["minuto"], "autor": None, "assistencia": None})
            continue
        autor, motivo = _pessoa_do_gol(d["autor"], pessoas)
        if autor is None:
            problemas.append(f"gol '{texto}': autor: {motivo}")
            continue
        assistencia = None
        if d["assistencia"]:
            assistencia, motivo = _pessoa_do_gol(d["assistencia"], pessoas)
            if assistencia is None:
                problemas.append(f"gol '{texto}': assistência: {motivo}")
                continue
            if _chave_entrada(assistencia) == _chave_entrada(autor):
                problemas.append(f"gol '{texto}': quem fez o gol não pode ser o autor da assistência")
                assistencia = None
        gols.append({"time": "nosso", "minuto": d["minuto"], "autor": autor, "assistencia": assistencia})
    if gols and all(_ordem_minuto(g["minuto"]) is not None for g in gols):
        gols.sort(key=lambda g: _ordem_minuto(g["minuto"]))
    nosso = deles = 0
    for g in gols:
        if g["time"] == "nosso":
            nosso += 1
        else:
            deles += 1
        g["parcial"] = f"{nosso} x {deles}"
    return gols, problemas


def _contar_gols(gols):
    return (sum(1 for g in gols if g["time"] == "nosso"), sum(1 for g in gols if g["time"] == "adversario"))


def _canonico_pessoa(item: str, pessoas) -> str:
    """Confere nome/camisa com o elenco. Quem não é do elenco precisa vir como 'Nome (suporte)'."""
    suporte = _interpretar_suporte(item)
    if suporte:
        return _formatar_suporte(*suporte)
    pessoa, motivo = _resolver_jogador(item, pessoas)
    if pessoa is None:
        raise ErroNaoEncontrado(f"{motivo}. Para quem não é do elenco, escreva 'Nome (suporte)' "
                                "ou 'Nome (suporte, Posição)'.")
    return pessoa["nome"]


def _html_linha_jogo(jogo, proximo, time):
    d = jogo["data"]
    selo = '<span class="selo selo-proximo">Próximo</span>' if proximo else '<span class="selo">Realizado</span>'
    local = f'\n                <span class="jogo-detalhe">{_esc(jogo["local"])}</span>' if jogo["local"] else ""
    return f"""          <li>
            <a class="jogo" href="{_url_jogo(jogo)}">
              <div class="jogo-data"><strong>{d.day:02d}</strong><span>{MESES[d.month - 1]}</span></div>
              <div>
                <span class="jogo-confronto">{_confronto(jogo, time)}</span>
                <span class="jogo-detalhe">{_esc(_descricao_data(jogo))}</span>{local}
              </div>
              {selo}
            </a>
          </li>"""


def _descricao_data(jogo) -> str:
    d = jogo["data"]
    texto = f"{DIAS_SEMANA[d.weekday()]}, {d.strftime('%d/%m/%Y')}"
    return f"{texto}, {jogo['hora']}" if jogo["hora"] else texto


def _confronto(jogo, time) -> str:
    meio = _esc(jogo["placar"]) if jogo["placar"] else "x"
    return f"{time} {meio} {_esc(jogo['adversario'])}"


def _url_jogo(jogo) -> str:
    return f"jogo.html?id={quote(jogo['id'])}"


def _html_grupo(titulo, jogos, proximo, vazio, time):
    if jogos:
        itens = "\n".join(_html_linha_jogo(j, proximo, time) for j in jogos)
        itens = "\n".join("  " + l for l in itens.splitlines())
        corpo = f'<ul class="lista-jogos">\n{itens}\n          </ul>'
    else:
        corpo = f'<p class="vazio">{_esc(vazio)}</p>'
    return f'<div class="grupo-jogos">\n          <h2>{titulo}</h2>\n          {corpo}\n        </div>'


def _separar_por_data(jogos, hoje):
    proximos = sorted((j for j in jogos if j["data"] >= hoje), key=lambda j: j["data"])
    realizados = sorted((j for j in jogos if j["data"] < hoje), key=lambda j: j["data"], reverse=True)
    return proximos, realizados


# ====================================================================== elenco: parsing e HTML (puro)


def _ler_estatistica(linha, coluna, rotulo) -> int:
    texto = linha.get(coluna, "")
    if texto == "":
        return 0
    try:
        valor = int(texto)
    except ValueError:
        valor = -1
    if valor < 0:
        raise ErroDados(f"elenco.csv, linha {linha.get('_linha', '?')}: {rotulo} inválido '{texto}'. "
                        "Use um número inteiro (0 ou mais).")
    return valor


def _foto_padrao(nome: str) -> str:
    return f"{sem_acento(nome).strip()}.jpeg"


def _lista_fotos_jogo(atleta) -> List[str]:
    return [f.strip() for f in atleta.get("fotos_jogo", "").split(",") if f.strip()]


def _chave_ordem(a):
    return (a["numero"] is None, a["numero"] or 0, a["nome"])


def _montar_atletas(linhas) -> List[dict]:
    titulos_grupo = {g: t for g, t, _ in GRUPOS}
    atletas = []
    for linha in linhas:
        n = linha.get("_linha", "?")
        nome = linha.get("nome", "")
        if not nome:
            raise ErroDados(f"elenco.csv, linha {n}: falta o nome.")
        posicao = linha.get("posicao", "")
        grupo = _descobrir_grupo(linha.get("grupo", ""), posicao)
        if grupo is None:
            raise ErroDados(f"elenco.csv, linha {n}: não reconheci a posição '{posicao}'. Escreva uma posição "
                            f"comum (ex.: Zagueiro) ou preencha a coluna grupo com: "
                            f"{', '.join(titulos_grupo.values())}.")
        texto_numero = linha.get("numero", "")
        if grupo == GRUPO_STAFF and texto_numero == "":
            numero = None
        else:
            try:
                numero = int(texto_numero)
            except ValueError:
                raise ErroDados(f"elenco.csv, linha {n}: número da camisa inválido '{texto_numero}'.")
        atleta = {
            "numero": numero, "nome": nome, "posicao": posicao or titulos_grupo[grupo], "grupo": grupo,
            "foto": linha.get("foto") or _foto_padrao(nome),
            "formacao": linha.get("formacao", ""), "idade": linha.get("idade", ""), "pe": linha.get("pe", ""),
            "altura": linha.get("altura", ""), "titulos": linha.get("titulos", ""),
            "fotos_jogo": linha.get("fotos_jogo", ""),
        }
        if grupo != GRUPO_STAFF:
            for coluna, nome_completo, _ in ESTATISTICAS:
                atleta[coluna] = _ler_estatistica(linha, coluna, nome_completo.lower())
        atletas.append(atleta)
    return atletas


def _html_estatisticas(a) -> str:
    itens = "\n".join(
        f'                <li{" class=zero" if a[c] == 0 else ""} title="{_esc(nome)}">'
        f'<strong>{a[c]}</strong><span>{_esc(curto)}</span></li>'
        for c, nome, curto in ESTATISTICAS)
    return (f'              <ul class="atleta-stats" aria-label="Estatísticas de {_esc(a["nome"])}">\n'
            f'{itens}\n              </ul>')


def _html_atleta(a) -> str:
    foto = (f'              <img src="imagens/jogadores/{quote(a["foto"])}" alt="Foto de {_esc(a["nome"])}" '
            f'loading="lazy" onerror="this.onerror=null;this.src=\'imagens/placeholder.svg\'">')
    url = f"jogador.html?id={quote(slug(a['nome']))}"
    if a["grupo"] == GRUPO_STAFF:
        formacao = f'\n              <p class="atleta-posicao">{_esc(a["formacao"])}</p>' if a["formacao"] else ""
        return f"""            <li class="atleta">
              <a href="{url}" class="atleta-link">
{foto}
                <p class="atleta-nome">{_esc(a["nome"])}</p>
                <p class="atleta-posicao">{_esc(a["posicao"])}</p>{formacao}
              </a>
            </li>"""
    return f"""            <li class="atleta">
              <a href="{url}" class="atleta-link">
{foto}
                <span class="atleta-numero">{a['numero']}</span>
                <p class="atleta-nome">{_esc(a['nome'])}</p>
                <p class="atleta-posicao">{_esc(a['posicao'])}</p>
{_html_estatisticas(a)}
              </a>
            </li>"""


def _html_elenco(atletas) -> str:
    blocos = []
    for id_grupo, titulo, _ in GRUPOS:
        do_grupo = sorted((a for a in atletas if a["grupo"] == id_grupo), key=_chave_ordem)
        if not do_grupo:
            continue
        itens = "\n".join(_html_atleta(a) for a in do_grupo)
        blocos.append(f'<div class="grupo-elenco" data-posicao="{FILTROS[id_grupo]}">\n'
                      f'          <h2>{titulo}</h2>\n'
                      f'          <ul class="elenco-grade">\n{itens}\n          </ul>\n'
                      f'        </div>')
    if not blocos:
        return '<p class="vazio">Nenhum atleta cadastrado por enquanto.</p>'
    return "\n        ".join(blocos)


def _json_jogadores(atletas) -> str:
    dados = {}
    for a in sorted(atletas, key=_chave_ordem):
        staff = a["grupo"] == GRUPO_STAFF
        dados[slug(a["nome"])] = {
            "nome": a["nome"], "numero": None if staff else a["numero"], "posicao": a["posicao"],
            "grupo": a["grupo"], "foto": a["foto"], "formacao": a["formacao"], "idade": a["idade"],
            "pe": a["pe"], "altura": a["altura"], "titulos": a["titulos"],
            "fotos_jogo": _lista_fotos_jogo(a), "jogos": a.get("jogos", 0), "gols": a.get("gols", 0),
            "assistencias": a.get("assistencias", 0),
        }
    return json.dumps(dados, ensure_ascii=False, indent=2)


def _escrever_se_mudou(arquivo: Path, conteudo: str) -> bool:
    antigo = arquivo.read_text(encoding="utf-8") if arquivo.exists() else None
    if conteudo != antigo:
        arquivo.write_text(conteudo, encoding="utf-8")
        return True
    return False


# ====================================================================== classe principal


class Site:
    """
    Ponto de entrada da biblioteca.

    raiz        pasta do site (onde ficam index.html, elenco.html, jogos.html, imagens/, css/).
    pasta_dados pasta dos .csv/.json. Padrão: <raiz>/dados se existir; senão a própria raiz.
    nosso_time  nome do time, usado nos confrontos ("Pétalas Negras 2 x 1 Fulano").
    """

    def __init__(self, raiz: Union[str, Path], pasta_dados: Union[str, Path, None] = None,
                 nosso_time: str = NOSSO_TIME_PADRAO):
        self.raiz = Path(raiz).resolve()
        if pasta_dados is not None:
            self.pasta_dados = Path(pasta_dados).resolve()
        else:
            self.pasta_dados = self.raiz / "dados" if (self.raiz / "dados").is_dir() else self.raiz
        self.nosso_time = nosso_time

        self.arquivo_elenco = self.pasta_dados / "elenco.csv"
        self.arquivo_jogos = self.pasta_dados / "jogos.csv"
        self.arquivo_json_jogadores = self.pasta_dados / "jogadores.json"
        self.arquivo_json_jogos = self.pasta_dados / "jogos.json"
        self.pagina_elenco = self.raiz / "elenco.html"
        self.pagina_jogos = self.raiz / "jogos.html"
        self.pagina_inicio = self.raiz / "index.html"
        self.pagina_css = self.raiz / "css" / "estilo.css"
        self.pasta_fotos_jogadores = self.raiz / "imagens" / "jogadores"
        self.pasta_fotos_perfil = self.raiz / "imagens" / "perfil"
        self.pasta_fotos_jogos = self.raiz / "imagens" / "jogos"

    # ------------------------------------------------------------ elenco: leitura

    def _tabela_elenco(self):
        return _ler_csv(self.arquivo_elenco)

    def _salvar_elenco(self, colunas, linhas, separador):
        _gravar_csv(self.arquivo_elenco, colunas, linhas, separador, COLUNAS_ELENCO)

    def listar_elenco(self) -> List[dict]:
        """Atletas e comissão como dicts (mesmos campos do jogadores.json, mais 'slug')."""
        _, linhas, _ = self._tabela_elenco()
        atletas = _montar_atletas(linhas)
        for a in atletas:
            a["slug"] = slug(a["nome"])
            a["fotos_jogo"] = _lista_fotos_jogo(a)
        return sorted(atletas, key=lambda a: (a["grupo"] == GRUPO_STAFF, _chave_ordem(a)))

    def obter_pessoa(self, busca: Union[str, int]) -> dict:
        """Procura por nome (ou parte) ou camisa. Levanta ErroNaoEncontrado / ErroAmbiguo."""
        _, linhas, _ = self._tabela_elenco()
        linha = self._achar_pessoa(linhas, busca)
        atleta = _montar_atletas([linha])[0]
        atleta["slug"] = slug(atleta["nome"])
        atleta["fotos_jogo"] = _lista_fotos_jogo(atleta)
        return atleta

    @staticmethod
    def _achar_pessoa(linhas, busca) -> dict:
        t = sem_acento(str(busca)).strip()
        if not t:
            raise ErroNaoEncontrado("busca vazia.")
        achados = [l for l in linhas if l.get("numero", "") == t or sem_acento(l.get("nome", "")) == t]
        if not achados:
            achados = [l for l in linhas if t in sem_acento(l.get("nome", ""))]
        if not achados:
            raise ErroNaoEncontrado(f"ninguém encontrado com nome/camisa '{busca}'.")
        if len(achados) > 1:
            nomes = ", ".join(f"{l.get('numero') or '--'} {l['nome']}" for l in achados)
            raise ErroAmbiguo(f"'{busca}' bate com mais de uma pessoa: {nomes}.")
        return achados[0]

    # ------------------------------------------------------------ elenco: escrita

    @staticmethod
    def _aplicar_campos_pessoa(linha: dict, campos: Dict[str, Any]) -> None:
        for campo, valor in campos.items():
            if campo not in COLUNAS_ELENCO:
                raise ErroDados(f"campo desconhecido: '{campo}'. Campos: {', '.join(COLUNAS_ELENCO)}.")
            if valor is None:
                continue
            if campo == "fotos_jogo" and not isinstance(valor, str):
                valor = ", ".join(str(v).strip() for v in valor if str(v).strip())
            elif campo == "fotos_jogo":
                valor = ", ".join(_separar_lista(valor))
            if valor == "":
                linha[campo] = ""
                continue
            if campo == "posicao":
                valor = normalizar_posicao(valor)
            elif campo in ("numero", "idade"):
                valor = normalizar_inteiro(valor)
            elif campo in ("jogos", "gols", "assistencias"):
                valor = normalizar_estatistica(valor, linha.get(campo, ""))
            elif campo == "altura":
                valor = normalizar_altura(valor)
            elif campo == "pe":
                valor = normalizar_pe(valor)
            linha[campo] = str(valor).strip()

    def adicionar_pessoa(self, nome: str, posicao: str, numero: Union[int, str, None] = None,
                         **campos: Any) -> dict:
        """
        Cadastra jogador ou integrante da comissão. Campos opcionais: foto, idade, pe, altura, titulos,
        formacao, fotos_jogo, jogos, gols, assistencias. Devolve a pessoa cadastrada.
        """
        colunas, linhas, sep = self._tabela_elenco()
        if not nome or not str(nome).strip():
            raise ErroDados("falta o nome.")
        if any(sem_acento(l["nome"]).strip() == sem_acento(nome).strip() for l in linhas):
            raise ErroDados(f"já existe alguém chamado {nome} (o endereço de perfil ficaria duplicado).")
        linha = {c: "" for c in colunas}
        linha["_linha"] = len(linhas) + 2
        linha["nome"] = str(nome).strip()
        linha["posicao"] = normalizar_posicao(posicao)
        staff = _descobrir_grupo(posicao) == GRUPO_STAFF
        if numero is None or str(numero) == "":
            if not staff:
                raise ErroDados("falta o número da camisa.")
        else:
            linha["numero"] = normalizar_inteiro(numero)
        if not staff:
            for c, _, _ in ESTATISTICAS:
                linha[c] = "0"
        self._aplicar_campos_pessoa(linha, campos)
        linhas.append(linha)
        _montar_atletas([linha])  # valida
        self._salvar_elenco(colunas, linhas, sep)
        return self.obter_pessoa(linha["nome"])

    def editar_pessoa(self, busca: Union[str, int], **campos: Any) -> dict:
        """
        Altera campos de alguém. Valor "" apaga; None ignora. jogos/gols/assistencias aceitam "+N".
        Ex.: site.editar_pessoa("Rulim", altura="1.66", pe="d")
        """
        colunas, linhas, sep = self._tabela_elenco()
        linha = self._achar_pessoa(linhas, busca)
        if "nome" in campos and campos["nome"]:
            novo = sem_acento(campos["nome"]).strip()
            if any(l is not linha and sem_acento(l["nome"]).strip() == novo for l in linhas):
                raise ErroDados(f"já existe alguém chamado {campos['nome']}.")
        self._aplicar_campos_pessoa(linha, campos)
        _montar_atletas([linha])  # valida
        self._salvar_elenco(colunas, linhas, sep)
        return self.obter_pessoa(linha["nome"])

    def atualizar_estatisticas(self, busca: Union[str, int], jogos: Any = None, gols: Any = None,
                               assistencias: Any = None) -> dict:
        """Define (número) ou soma ("+N") jogos, gols e assistências de um jogador."""
        pessoa = self.obter_pessoa(busca)
        if pessoa["grupo"] == GRUPO_STAFF:
            raise ErroDados(f"{pessoa['nome']} é da comissão técnica e não tem estatísticas.")
        return self.editar_pessoa(busca, jogos=jogos, gols=gols, assistencias=assistencias)

    def remover_pessoa(self, busca: Union[str, int]) -> dict:
        """Remove do elenco.csv (as fotos em imagens/ não são apagadas). Devolve quem foi removido."""
        colunas, linhas, sep = self._tabela_elenco()
        linha = self._achar_pessoa(linhas, busca)
        removido = _montar_atletas([linha])[0]
        linhas.remove(linha)
        self._salvar_elenco(colunas, linhas, sep)
        return removido

    def sincronizar_fotos_perfil(self) -> Dict[str, List[str]]:
        """Preenche fotos_jogo lendo imagens/perfil/<slug>/. Devolve {nome: [fotos]} dos que mudaram."""
        colunas, linhas, sep = self._tabela_elenco()
        mudou: Dict[str, List[str]] = {}
        for linha in linhas:
            achadas = _fotos_da_pasta(self.pasta_fotos_perfil / slug(linha["nome"]))
            if achadas and linha.get("fotos_jogo", "") != ", ".join(achadas):
                linha["fotos_jogo"] = ", ".join(achadas)
                mudou[linha["nome"]] = achadas
        if mudou:
            self._salvar_elenco(colunas, linhas, sep)
        return mudou

    # ------------------------------------------------------------ elenco: páginas

    def avisos_elenco(self) -> List[str]:
        atletas = _montar_atletas(self._tabela_elenco()[1])
        avisos, vistos = [], {}
        for a in atletas:
            if a["numero"] is None or a["grupo"] == GRUPO_STAFF:
                continue
            if a["numero"] in vistos:
                avisos.append(f"a camisa {a['numero']} está com {vistos[a['numero']]} e {a['nome']}.")
            vistos[a["numero"]] = a["nome"]
        faltando = [a for a in atletas if not (self.pasta_fotos_jogadores / a["foto"]).exists()]
        if faltando and len(faltando) == len(atletas):
            avisos.append("não encontrei nenhuma foto em imagens/jogadores/ (aparece uma silhueta no lugar).")
        else:
            avisos += [f"foto não encontrada em imagens/jogadores/{a['foto']} ({a['nome']})." for a in faltando]
        if self.pasta_fotos_perfil.exists():
            for a in atletas:
                for foto in _lista_fotos_jogo(a):
                    if not (self.pasta_fotos_perfil / slug(a["nome"]) / foto).exists():
                        avisos.append(f"foto em jogo não encontrada em imagens/perfil/{slug(a['nome'])}/{foto} ({a['nome']}).")
        return avisos

    def atualizar_elenco(self) -> dict:
        """Regrava elenco.html e jogadores.json. Devolve um relatório."""
        atletas = _montar_atletas(self._tabela_elenco()[1])
        avisos = self.avisos_elenco()
        mudou_html = _substituir_bloco(self.pagina_elenco, "ELENCO", _html_elenco(atletas))
        mudou_json = _escrever_se_mudou(self.arquivo_json_jogadores, _json_jogadores(atletas))
        staff = sum(1 for a in atletas if a["grupo"] == GRUPO_STAFF)
        return {"atletas": len(atletas) - staff, "comissao": staff, "elenco_html_mudou": mudou_html,
                "jogadores_json_mudou": mudou_json, "avisos": avisos}

    # ------------------------------------------------------------ jogos: leitura

    def _tabela_jogos(self):
        return _ler_csv(self.arquivo_jogos, COLUNAS_JOGOS_OBRIGATORIAS)

    def _salvar_jogos(self, colunas, linhas, sep):
        _gravar_csv(self.arquivo_jogos, colunas, linhas, sep, COLUNAS_JOGOS)

    def _pessoas(self) -> List[dict]:
        """Nome, camisa, posição e slug do elenco.csv (só leitura)."""
        if not self.arquivo_elenco.exists():
            return []
        _, linhas, _ = self._tabela_elenco()
        return [{"nome": l["nome"], "numero": l.get("numero", ""), "posicao": l.get("posicao", ""),
                 "slug": slug(l["nome"])} for l in linhas if l.get("nome")]

    @staticmethod
    def _montar_jogos(linhas) -> List[dict]:
        jogos, usados = [], {}
        for linha in linhas:
            if not linha.get("adversario"):
                raise ErroDados(f"jogos.csv, linha {linha['_linha']}: falta o adversário.")
            data = _converter_data(linha.get("data", ""), linha["_linha"])
            base = _id_base(data, linha["adversario"])
            usados[base] = usados.get(base, 0) + 1
            id_jogo = base if usados[base] == 1 else f"{base}-{usados[base]}"
            jogos.append({
                "id": id_jogo, "data": data, "hora": linha.get("hora", ""), "adversario": linha["adversario"],
                "local": linha.get("local", ""), "placar": linha.get("placar", ""),
                "escalacao": _separar_lista(linha.get("escalacao", "")),
                "reservas": _separar_lista(linha.get("reservas", "")),
                "substituicoes": _separar_lista(linha.get("substituicoes", "")),
                "gols": _separar_lista(linha.get("gols", "")),
                "fotos": [f.strip() for f in linha.get("fotos", "").split(",") if f.strip()],
            })
        return jogos

    def _jogo_para_dict(self, jogo: dict, pessoas: List[dict]) -> dict:
        """Formato do jogos.json (titulares/reservas/gols já resolvidos)."""
        placar = interpretar_placar(jogo["placar"])
        if placar:
            pro, contra = placar
            resultado = "vitoria" if pro > contra else "derrota" if pro < contra else "empate"
            placar_texto = f"{pro} x {contra}"
        else:
            pro = contra = None
            resultado, placar_texto = "", jogo["placar"]
        titulares, reservas, substituicoes, _ = _montar_escalacao(jogo, pessoas)
        gols, _ = _resolver_gols(jogo["gols"], jogo["adversario"], pessoas)
        conferem = (_contar_gols(gols) == placar) if (placar and gols) else None
        return {
            "id": jogo["id"], "data": jogo["data"].isoformat(), "data_br": jogo["data"].strftime("%d/%m/%Y"),
            "dia_semana": DIAS_SEMANA[jogo["data"].weekday()], "hora": jogo["hora"],
            "adversario": jogo["adversario"], "local": jogo["local"], "placar": placar_texto,
            "gols_pro": pro, "gols_contra": contra, "resultado": resultado,
            "titulares": titulares, "reservas": reservas, "substituicoes": substituicoes,
            "gols": gols, "gols_conferem": conferem, "fotos": jogo["fotos"],
        }

    def listar_jogos(self) -> List[dict]:
        """Todos os jogos já resolvidos (mais recentes primeiro), no formato do jogos.json."""
        jogos = self._montar_jogos(self._tabela_jogos()[1])
        pessoas = self._pessoas()
        jogos.sort(key=lambda j: (j["data"], j["hora"]), reverse=True)
        return [self._jogo_para_dict(j, pessoas) for j in jogos]

    def obter_jogo(self, busca: Union[str, int]) -> dict:
        """Busca por id, adversário (ou parte), data (DD/MM/AAAA ou AAAA-MM-DD) ou posição (int, 1 = mais recente)."""
        _, linhas, _ = self._tabela_jogos()
        linha = self._achar_jogo(linhas, busca)
        jogo = next(j for j in self._montar_jogos(linhas) if j["id"] == self._id_da_linha(linha))
        return self._jogo_para_dict(jogo, self._pessoas())

    @staticmethod
    def _id_da_linha(linha) -> str:
        try:
            return _id_base(_converter_data(linha.get("data", ""), linha.get("_linha", "?")), linha.get("adversario", ""))
        except ErroDados:
            return ""

    def _ordenar_linhas(self, linhas):
        def chave(l):
            try:
                return (_converter_data(l.get("data", "")), l.get("hora", ""))
            except ErroDados:
                return (date.min, "")
        return sorted(linhas, key=chave, reverse=True)

    def _achar_jogo(self, linhas, busca) -> dict:
        ordenadas = self._ordenar_linhas(linhas)
        if isinstance(busca, int):
            if 1 <= busca <= len(ordenadas):
                return ordenadas[busca - 1]
            raise ErroNaoEncontrado(f"posição {busca} fora da lista ({len(ordenadas)} jogos).")
        termo = str(busca).strip()
        if not termo:
            raise ErroNaoEncontrado("busca vazia.")
        exatos = [l for l in ordenadas if self._id_da_linha(l) == termo]
        if exatos:
            return exatos[0]
        t = sem_acento(termo)
        achados = [l for l in ordenadas if t in sem_acento(l.get("adversario", ""))
                   or termo in l.get("data", "") or t in self._id_da_linha(l)]
        if not achados:
            raise ErroNaoEncontrado(f"nenhum jogo encontrado para '{busca}'.")
        if len(achados) > 1:
            raise ErroAmbiguo(f"'{busca}' bate com mais de um jogo: "
                              + ", ".join(self._id_da_linha(l) for l in achados) + ". Use o id completo.")
        return achados[0]

    # ------------------------------------------------------------ jogos: escrita

    def _aplicar_campos_jogo(self, linha: dict, campos: Dict[str, Any]) -> None:
        for campo in campos:
            if campo not in COLUNAS_JOGOS:
                raise ErroDados(f"campo desconhecido: '{campo}'. Campos: {', '.join(COLUNAS_JOGOS)}.")
        pessoas = self._pessoas()

        # campos simples
        if campos.get("data") is not None:
            linha["data"] = normalizar_data(campos["data"])
        if campos.get("hora") not in (None, ""):
            linha["hora"] = normalizar_hora(campos["hora"])
        elif campos.get("hora") == "":
            linha["hora"] = ""
        for c in ("adversario", "local"):
            if campos.get(c) is not None:
                linha[c] = str(campos[c]).strip()
        if campos.get("placar") is not None:
            linha["placar"] = "" if campos["placar"] == "" else normalizar_placar(campos["placar"])
        if campos.get("fotos") is not None:
            linha["fotos"] = ", ".join(_como_lista(campos["fotos"]))

        # titulares e reservas: nomes conferidos com o elenco; quem não é do elenco precisa de "(suporte)"
        for campo in ("escalacao", "reservas"):
            if campos.get(campo) is not None:
                itens, vistos = [], set()
                for item in _como_lista(campos[campo]):
                    texto = _canonico_pessoa(item, pessoas)
                    if sem_acento(texto) not in vistos:
                        vistos.add(sem_acento(texto))
                        itens.append(texto)
                linha[campo] = ", ".join(itens)

        if campos.get("substituicoes") is not None:
            titulares, _ = _resolver_lista(_separar_lista(linha.get("escalacao", "")), pessoas)
            reservas, _ = _resolver_lista(_separar_lista(linha.get("reservas", "")), pessoas)
            nos_titulares = {_chave_entrada(e) for e in titulares}
            reservas = [e for e in reservas if _chave_entrada(e) not in nos_titulares]
            pares, problemas = _resolver_substituicoes(_como_lista(campos["substituicoes"]), titulares, reservas)
            if problemas:
                raise ErroDados(problemas[0][0].upper() + problemas[0][1:] + ".")
            linha["substituicoes"] = ", ".join(_texto_substituicao(p) for p in pares)

        if campos.get("gols") is not None:
            saida = []
            for item in _como_lista(campos["gols"]):
                d = _interpretar_gol(item)
                if not d["autor"]:
                    raise ErroDados("falta quem fez o gol (ou 'adv' para gol do adversário).")
                if _eh_gol_do_adversario(d["autor"], linha.get("adversario", "")):
                    autor, assistencia = "adv", ""
                else:
                    autor = _canonico_pessoa(d["autor"], pessoas)
                    assistencia = _canonico_pessoa(d["assistencia"], pessoas) if d["assistencia"] else ""
                texto = f"{autor} {d['minuto']}" if d["minuto"] else autor
                if assistencia:
                    texto += f" (ast. {assistencia})"
                saida.append(texto)
            _, problemas = _resolver_gols(saida, linha.get("adversario", ""), pessoas)
            if problemas:
                raise ErroDados(problemas[0][0].upper() + problemas[0][1:] + ".")
            linha["gols"] = ", ".join(saida)

    def adicionar_jogo(self, data: Any, adversario: str, hora: str = "", local: str = "", placar: str = "",
                       escalacao: Lista = None, reservas: Lista = None, substituicoes: Lista = None,
                       gols: Lista = None, fotos: Lista = None) -> dict:
        """
        Cadastra um jogo. Listas aceitam texto separado por vírgula ou lista Python; jogadores por nome
        ou camisa; quem não é do elenco: "Fulano (suporte)" / "Fulano (suporte, Goleiro)".
        """
        colunas, linhas, sep = self._tabela_jogos()
        if not adversario or not str(adversario).strip():
            raise ErroDados("falta o adversário.")
        linha = {c: "" for c in colunas}
        linha["_linha"] = len(linhas) + 2
        self._aplicar_campos_jogo(linha, {
            "data": data, "adversario": adversario, "hora": hora, "local": local, "placar": placar,
            "escalacao": escalacao, "reservas": reservas, "substituicoes": substituicoes,
            "gols": gols, "fotos": fotos})
        linhas.append(linha)
        self._montar_jogos(linhas)  # valida
        self._salvar_jogos(colunas, linhas, sep)
        return self.obter_jogo(self._id_da_linha(linha))

    def editar_jogo(self, busca: Union[str, int], **campos: Any) -> dict:
        """Altera qualquer campo do jogo (data, hora, adversario, local, placar, escalacao, reservas,
        substituicoes, gols, fotos). Valor "" apaga; None ignora."""
        colunas, linhas, sep = self._tabela_jogos()
        linha = self._achar_jogo(linhas, busca)
        self._aplicar_campos_jogo(linha, campos)
        self._montar_jogos(linhas)  # valida
        self._salvar_jogos(colunas, linhas, sep)
        return self.obter_jogo(self._id_da_linha(linha))

    def definir_placar(self, busca: Union[str, int], placar: Any) -> dict:
        return self.editar_jogo(busca, placar=placar)

    def definir_escalacao(self, busca: Union[str, int], titulares: Lista = None, reservas: Lista = None,
                          substituicoes: Lista = None) -> dict:
        return self.editar_jogo(busca, escalacao=titulares, reservas=reservas, substituicoes=substituicoes)

    def definir_gols(self, busca: Union[str, int], gols: Lista) -> dict:
        return self.editar_jogo(busca, gols=gols)

    def remover_jogo(self, busca: Union[str, int]) -> str:
        """Remove o jogo do jogos.csv (fotos em imagens/ não são apagadas). Devolve o id removido."""
        colunas, linhas, sep = self._tabela_jogos()
        linha = self._achar_jogo(linhas, busca)
        id_jogo = self._id_da_linha(linha)
        linhas.remove(linha)
        self._salvar_jogos(colunas, linhas, sep)
        return id_jogo

    def sincronizar_fotos_jogos(self) -> Dict[str, List[str]]:
        """Preenche a coluna fotos lendo imagens/jogos/<id>/. Devolve {id: [fotos]} dos que mudaram."""
        colunas, linhas, sep = self._tabela_jogos()
        mudou: Dict[str, List[str]] = {}
        for linha in linhas:
            id_jogo = self._id_da_linha(linha)
            achadas = _fotos_da_pasta(self.pasta_fotos_jogos / id_jogo) if id_jogo else []
            if achadas and linha.get("fotos", "") != ", ".join(achadas):
                linha["fotos"] = ", ".join(achadas)
                mudou[id_jogo] = achadas
        if mudou:
            self._salvar_jogos(colunas, linhas, sep)
        return mudou

    # ------------------------------------------------------------ jogos: páginas

    def avisos_jogos(self) -> List[str]:
        jogos = self._montar_jogos(self._tabela_jogos()[1])
        pessoas = self._pessoas()
        nomes_elenco = {sem_acento(p["nome"]) for p in pessoas}
        avisos = []
        for jogo in jogos:
            r = f"{jogo['data'].strftime('%d/%m/%Y')} x {jogo['adversario']}"
            if jogo["placar"] and not interpretar_placar(jogo["placar"]):
                avisos.append(f"placar '{jogo['placar']}' ({r}) não está no formato '2 x 1'.")
            for texto in jogo["escalacao"] + jogo["reservas"]:
                sup = _interpretar_suporte(texto)
                if sup and sem_acento(sup[0]) in nomes_elenco:
                    avisos.append(f"{r}: {sup[0]} está no elenco; tire o '(suporte)' dele.")
            titulares, reservas, _, problemas = _montar_escalacao(jogo, pessoas)
            avisos += [f"escalação de {r}: {p}." for p in problemas]
            chaves_tit = {_chave_entrada(t) for t in titulares}
            repetidos = [e["nome"] for e in _resolver_lista(jogo["reservas"], pessoas)[0]
                         if _chave_entrada(e) in chaves_tit]
            if repetidos:
                avisos.append(f"{r}: {', '.join(repetidos)} está nos titulares e nas reservas (ficará só nos titulares).")
            if len(titulares) > 11:
                avisos.append(f"{r}: {len(titulares)} jogadores nos titulares.")
            for foto in jogo["fotos"]:
                if not (self.pasta_fotos_jogos / jogo["id"] / foto).exists():
                    avisos.append(f"foto não encontrada em imagens/jogos/{jogo['id']}/{foto} ({r}).")
            gols, problemas_gols = _resolver_gols(jogo["gols"], jogo["adversario"], pessoas)
            avisos += [f"gols de {r}: {p}." for p in problemas_gols]
            placar = interpretar_placar(jogo["placar"])
            if gols and not placar:
                avisos.append(f"{r}: há gols lançados, mas o placar está vazio.")
            elif gols and _contar_gols(gols) != placar:
                n, d = _contar_gols(gols)
                avisos.append(f"{r}: os gols lançados ({n} x {d}) não batem com o placar ({placar[0]} x {placar[1]}).")
            em_jogo = {_chave_entrada(e) for e in titulares + reservas}
            if em_jogo:
                for g in gols:
                    for pessoa in (g["autor"], g["assistencia"]):
                        if pessoa and _chave_entrada(pessoa) not in em_jogo:
                            avisos.append(f"{r}: {pessoa['nome']} fez gol/assistência mas não está nos titulares nem nas reservas.")
        return avisos

    def _garantir_css(self) -> bool:
        if not self.pagina_css.exists():
            return False
        texto = self.pagina_css.read_text(encoding="utf-8")
        if MARCA_CSS in texto:
            return False
        self.pagina_css.write_text(texto.rstrip("\n") + "\n" + BLOCO_CSS, encoding="utf-8")
        return True

    def atualizar_jogos(self, hoje: Optional[date] = None) -> dict:
        """Regrava jogos.html, o destaque do index.html e jogos.json. Devolve um relatório."""
        hoje = hoje or date.today()
        jogos = self._montar_jogos(self._tabela_jogos()[1])
        pessoas = self._pessoas()
        avisos = self.avisos_jogos()
        proximos, realizados = _separar_por_data(jogos, hoje)
        t = self.nosso_time

        pagina = "\n        ".join([
            _html_grupo("Próximos jogos", proximos, True, "Nenhum jogo marcado por enquanto.", t),
            _html_grupo("Jogos realizados", realizados, False, "Ainda não há jogos realizados.", t)])
        if proximos:
            destaque_jogo, rotulo = proximos[0], "Próximo jogo"
        elif realizados:
            destaque_jogo, rotulo = realizados[0], "Último jogo"
        else:
            destaque_jogo = None
        destaque = "" if destaque_jogo is None else (
            f'<a class="destaque-jogo" href="{_url_jogo(destaque_jogo)}">\n'
            f'          <span class="rotulo">{rotulo}</span>\n'
            f'          <strong>{_confronto(destaque_jogo, t)}</strong>\n'
            f'          <span class="detalhe">{_esc(_descricao_data(destaque_jogo))}</span>\n'
            f'        </a>')

        mudou_jogos = _substituir_bloco(self.pagina_jogos, "JOGOS", pagina)
        mudou_inicio = _substituir_bloco(self.pagina_inicio, "PROXIMO", destaque)
        dados = {j["id"]: self._jogo_para_dict(j, pessoas)
                 for j in sorted(jogos, key=lambda j: (j["data"], j["hora"]), reverse=True)}
        mudou_json = _escrever_se_mudou(self.arquivo_json_jogos, json.dumps(dados, ensure_ascii=False, indent=2))
        css = self._garantir_css()
        if not (self.raiz / "jogo.html").exists():
            avisos.append("não encontrei jogo.html na raiz do site (é a página de cada jogo).")
        return {"jogos": len(jogos), "proximos": len(proximos), "realizados": len(realizados),
                "jogos_html_mudou": mudou_jogos, "index_html_mudou": mudou_inicio,
                "jogos_json_mudou": mudou_json, "css_acrescentado": css, "avisos": avisos}

    # ------------------------------------------------------------ tudo junto

    def atualizar_tudo(self, hoje: Optional[date] = None) -> dict:
        """Atualiza elenco e jogos. Devolve {'elenco': ..., 'jogos': ..., 'avisos': [...]}."""
        elenco = self.atualizar_elenco()
        jogos = self.atualizar_jogos(hoje)
        return {"elenco": elenco, "jogos": jogos, "avisos": elenco["avisos"] + jogos["avisos"]}

    # ------------------------------------------------------------ finanças
    def _tabela_financas(self):
        arquivo = self.pasta_dados / "financas.csv"
        if not arquivo.exists():
            _gravar_csv(arquivo, COLUNAS_FINANCAS, [], ",", COLUNAS_FINANCAS)
        return _ler_csv(arquivo)

    def listar_financas(self) -> List[dict]:
        try:
            _, linhas, _ = self._tabela_financas()
            return linhas
        except Exception:
            return []

    def adicionar_transacao(self, tipo: str, nome: str, descricao: str, valor: float, data: str = "") -> dict:
        colunas, linhas, sep = self._tabela_financas()
        data_transacao = data if data else date.today().strftime("%d/%m/%Y")
        nova = {
            "data": data_transacao,
            "tipo": tipo,
            "nome": nome,
            "descricao": descricao,
            "valor": f"{valor:.2f}"
        }
        linhas.append(nova)
        _gravar_csv(self.pasta_dados / "financas.csv", colunas, linhas, sep, COLUNAS_FINANCAS)
        return nova

    # ------------------------------------------------------------ mensalidades
    def _caminho_mensalidades(self) -> Path:
        return self.pasta_dados / ARQUIVO_MENSALIDADES

    def _caminho_config_mensalidade(self) -> Path:
        return self.pasta_dados / ARQUIVO_CONFIG_MENSALIDADE

    def obter_valor_mensalidade(self) -> float:
        """Retorna o valor padrão atual da mensalidade (padrão R$ 50.00)."""
        caminho = self._caminho_config_mensalidade()
        if caminho.exists():
            try:
                dados = json.loads(caminho.read_text(encoding="utf-8"))
                return float(dados.get("valor", 50.0))
            except Exception:
                pass
        return 50.0

    def definir_valor_mensalidade(self, valor: float) -> None:
        """Salva o novo valor padrão da mensalidade."""
        caminho = self._caminho_config_mensalidade()
        caminho.write_text(json.dumps({"valor": float(valor)}, ensure_ascii=False, indent=2), encoding="utf-8")

    def carregar_status_mensalidades(self) -> dict:
        """Carrega o dicionário de status {slug_atleta: 'pago' ou 'pendente'}."""
        caminho = self._caminho_mensalidades()
        if caminho.exists():
            try:
                return json.loads(caminho.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def salvar_status_mensalidades(self, status: dict) -> None:
        caminho = self._caminho_mensalidades()
        caminho.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    def atualizar_status_mensalidade(self, slug_atleta: str, pago: bool, nome_atleta: str) -> None:
        """Atualiza o status do atleta e registra na aba de finanças se mudou para pago."""
        status = self.carregar_status_mensalidades()
        estado_anterior = status.get(slug_atleta, "pendente")
        novo_estado = "pago" if pago else "pendente"
        status[slug_atleta] = novo_estado
        self.salvar_status_mensalidades(status)

        # Se mudou de pendente para pago, lança automaticamente nas finanças
        if estado_anterior != "pago" and novo_estado == "pago":
            valor = self.obter_valor_mensalidade()
            self.adicionar_transacao(
                tipo="recebita",
                nome=nome_atleta,
                descricao="Mensalidade",
                valor=valor
            )

    def gerar_backup(self, pasta_destino: Union[str, Path, None] = None) -> Path:
        """
        Cria um arquivo .zip com toda a pasta de dados (incluindo subpastas) e as imagens do site.
        Retorna o caminho do arquivo zip gerado.
        """
        data_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_zip = f"backup_petalas_{data_str}.zip"
        
        destino_dir = Path(pasta_destino) if pasta_destino else self.raiz
        caminho_zip = destino_dir / nome_zip

        with zipfile.ZipFile(caminho_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 1. Salvar pasta de dados e todas as suas subpastas recursivamente
            if self.pasta_dados.exists():
                for arq in self.pasta_dados.rglob("*"):
                    if arq.is_file():
                        # Mantém a estrutura de caminhos relativos à pasta de dados
                        rel_path = arq.relative_to(self.pasta_dados.parent)
                        zipf.write(arq, arcname=rel_path)

            # 2. Salvar imagens (jogadores, perfil, jogos)
            pastas_imagens = [
                self.pasta_fotos_jogadores,
                self.pasta_fotos_perfil,
                self.pasta_fotos_jogos
            ]
            for pasta in pastas_imagens:
                if pasta.exists():
                    for arq in pasta.rglob("*"):
                        if arq.is_file():
                            rel_path = arq.relative_to(self.raiz)
                            zipf.write(arq, arcname=rel_path)

        return caminho_zip

    # ------------------------------------------------------------ treinos e presença
    def _caminho_treinos(self) -> Path:
        return self.pasta_dados / "treinos.json"

    def carregar_treinos(self) -> dict:
        caminho = self._caminho_treinos()
        if caminho.exists():
            try:
                return json.loads(caminho.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def salvar_treinos(self, treinos: dict) -> None:
        caminho = self._caminho_treinos()
        caminho.write_text(json.dumps(treinos, ensure_ascii=False, indent=2), encoding="utf-8")

    def adicionar_ou_editar_treino(self, id_treino: str, data: str, hora: str, descricao: str, presencas: dict) -> str:
        treinos = self.carregar_treinos()
        if not id_treino:
            # Gera um ID baseado na data e descrição curta
            base = re.sub(r"[^a-z0-9]+", "-", sem_acento(data + "-" + descricao[:15])).strip("-")
            id_treino = base if base not in treinos else f"{base}-{len(treinos)+1}"
        
        treinos[id_treino] = {
            "id": id_treino,
            "data": data,
            "hora": hora,
            "descricao": descricao,
            "presencas": presencas  # Ex: {"slug-atleta": {"status": "presente"|"ausente"|"justificado", "motivo": "..."}}
        }
        self.salvar_treinos(treinos)
        return id_treino

    def remover_treino(self, id_treino: str) -> None:
        treinos = self.carregar_treinos()
        if id_treino in treinos:
            pop_item = treinos.pop(id_treino)
            self.salvar_treinos(treinos)

    def calcular_porcentagem_presenca(self) -> dict:
        """
        Calcula a % de presença de cada atleta.
        Fórmula: Presaças / (Total de Treinos - Faltas Justificadas)
        """
        treinos = self.carregar_treinos()
        atletas = [a for a in self.listar_elenco() if a["grupo"] != GRUPO_STAFF]
        
        estatisticas = {}
        for a in atletas:
            slug = a["slug"]
            total_esperado = 0
            presentes = 0
            justificadas = 0
            
            for t_id, treino in treinos.items():
                p_info = treino.get("presencas", {}).get(slug, {"status": "ausente", "motivo": ""})
                status = p_info.get("status", "ausente")
                
                if status == "presente":
                    presentes += 1
                    total_esperado += 1
                elif status == "justificado":
                    justificadas += 1
                    # Faltas justificadas não entram no total cobrado do atleta
                else:
                    # Ausente sem justificativa conta no total esperado
                    total_esperado += 1
            
            porcentagem = (presentes / total_esperado * 100) if total_esperado > 0 else 100.0
            estatisticas[slug] = {
                "nome": a["nome"],
                "presentes": presentes,
                "total_esperado": total_esperado,
                "justificadas": justificadas,
                "porcentagem": porcentagem
            }
        return estatisticas


# ====================================================================== CLI mínima (opcional)


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys
    p = argparse.ArgumentParser(description="Atualiza as páginas do site a partir dos CSVs.")
    p.add_argument("comando", nargs="?", default="atualizar", choices=["atualizar", "listar-elenco", "listar-jogos"])
    p.add_argument("--raiz", default=".", help="pasta do site (padrão: pasta atual)")
    args = p.parse_args(argv)
    site = Site(args.raiz)
    try:
        if args.comando == "listar-elenco":
            for a in site.listar_elenco():
                print(f"{a['numero'] if a['numero'] is not None else '--':>3}  {a['nome']:<14} {a['posicao']}")
        elif args.comando == "listar-jogos":
            for j in site.listar_jogos():
                print(f"{j['data_br']} {j['hora']:<6} {j['adversario']:<24} {j['placar'] or '-'}")
        else:
            rel = site.atualizar_tudo()
            print(f"{rel['elenco']['atletas']} atletas, {rel['elenco']['comissao']} na comissão, "
                  f"{rel['jogos']['jogos']} jogos.")
            for a in rel["avisos"]:
                print("Aviso:", a)
    except ErroDados as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())