#!/usr/bin/env python3
"""
Gerencia todo o elenco do site (jogadores e comissão técnica) a partir do elenco.csv.

O elenco.csv é o "banco de dados". Este script lê o csv e reescreve:
  - a lista de atletas em ../elenco.html (com os filtros por posição)
  - o arquivo dados/jogadores.json, usado pelas páginas de perfil (jogador.html)

Este script e os arquivos .csv ficam na pasta dados/. Pode rodar de qualquer lugar:

  python dados/atualizar_elenco.py                  só atualiza as páginas com o que está no elenco.csv
  python dados/atualizar_elenco.py --listar         mostra o quadro de todo mundo (nada é alterado)
  python dados/atualizar_elenco.py --novo           cadastra um jogador ou integrante da comissão
  python dados/atualizar_elenco.py --editar         edita qualquer dado de quem já está no elenco
  python dados/atualizar_elenco.py --editar Rulim   idem, já indo direto para a pessoa (nome ou camisa)
  python dados/atualizar_elenco.py --stats          altera jogos, gols e assistências rapidamente
  python dados/atualizar_elenco.py --remover        remove alguém do elenco
  python dados/atualizar_elenco.py --fotos          lê as pastas imagens/perfil/<id>/ e preenche fotos_jogo sozinho

Nas perguntas de edição: Enter mantém o valor atual, "-" apaga o valor.
Só usa a biblioteca padrão do Python 3.8 ou mais novo.
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
ARQUIVO_JSON = PASTA / "jogadores.json"
PAGINA_ELENCO = RAIZ / "elenco.html"
PASTA_FOTOS = RAIZ / "imagens" / "jogadores"
PASTA_PERFIL = RAIZ / "imagens" / "perfil"
EXTENSOES_IMAGEM = {".jpeg", ".jpg", ".png", ".webp"}

ESTATISTICAS = [
    ("jogos", "Jogos", "Jogos"),
    ("gols", "Gols", "Gols"),
    ("assistencias", "Assistências", "Assist."),
]

# Ordem padrão das colunas do csv (colunas que faltarem são acrescentadas ao salvar)
COLUNAS_PADRAO = ["numero", "nome", "posicao", "foto", "jogos", "gols", "assistencias",
                  "idade", "pe", "altura", "titulos", "formacao", "fotos_jogo"]

GRUPOS = [
    ("goleiro", "Goleiros", ["goleiro", "goleira"]),
    ("zagueiro", "Zagueiros", ["zagueiro", "zagueira", "defensor", "libero"]),
    ("lateral", "Laterais", ["lateral"]),
    ("meio", "Meio-campo", ["volante", "meio", "meia", "armador"]),
    ("ataque", "Ataque", ["ataque", "atacante", "centroavante", "ponta", "pivo"]),
    ("tecnico", "Comissão técnica / Staff", ["tecnico", "treinador", "comissao", "preparador", "auxiliar", "fotografo", "fotografa"]),
]

# Valor do data-posicao no HTML (é o que os botões de filtro do elenco.html usam)
FILTROS = {
    "goleiro": "goleiros",
    "zagueiro": "zagueiros",
    "lateral": "laterais",
    "meio": "meio-campo",
    "ataque": "ataque",
    "tecnico": "comissao",
}

GRUPO_STAFF = "tecnico"
EXEMPLOS_POSICAO = ("Goleiro, Zagueiro, Lateral direito, Lateral esquerdo, Volante, Meio-campista, "
                    "Ponta, Centroavante, Técnico, Auxiliar técnico, Preparador físico, Fotógrafo")


def erro(mensagem):
    print(f"Erro: {mensagem}", file=sys.stderr)
    sys.exit(1)


def sem_acento(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


def slug(nome):
    """Identificador usado na URL do perfil (jogador.html?id=...) e na pasta imagens/perfil/."""
    return sem_acento(nome).strip().replace(" ", "-")


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


def ordem_natural(texto):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", texto)]


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
    for coluna in COLUNAS_PADRAO:
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


def montar_atletas(linhas):
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
    return atletas


def ler_elenco():
    _, linhas, separador = carregar_tabela()
    return montar_atletas(linhas), separador


def lista_fotos_jogo(atleta):
    return [f.strip() for f in atleta.get("fotos_jogo", "").split(",") if f.strip()]


def avisos(atletas):
    vistos = {}
    for a in atletas:
        if a["numero"] is None or a["grupo"] == GRUPO_STAFF:
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

    if PASTA_PERFIL.exists():
        for a in atletas:
            for foto in lista_fotos_jogo(a):
                if not (PASTA_PERFIL / slug(a["nome"]) / foto).exists():
                    print(f"Aviso: foto em jogo não encontrada em imagens/perfil/{slug(a['nome'])}/{foto} ({a['nome']}).")


# ---------------------------------------------------------------- HTML e JSON

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

    url_perfil = f"jogador.html?id={quote(slug(a['nome']))}"

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


def json_jogadores(atletas):
    dados = {}
    for a in sorted(atletas, key=chave_ordem):
        staff = a["grupo"] == GRUPO_STAFF
        dados[slug(a["nome"])] = {
            "nome": a["nome"],
            # comissão técnica não tem camisa: o perfil não mostra "#100" etc.
            "numero": None if staff else a["numero"],
            "posicao": a["posicao"],
            "grupo": a["grupo"],
            "foto": a["foto"],
            "formacao": a["formacao"],
            "idade": a["idade"],
            "pe": a["pe"],
            "altura": a["altura"],
            "titulos": a["titulos"],
            "fotos_jogo": lista_fotos_jogo(a),
            "jogos": a.get("jogos", 0),
            "gols": a.get("gols", 0),
            "assistencias": a.get("assistencias", 0),
        }
    return json.dumps(dados, ensure_ascii=False, indent=2)


def gerar_json_jogadores(atletas):
    novo = json_jogadores(atletas)
    antigo = ARQUIVO_JSON.read_text(encoding="utf-8") if ARQUIVO_JSON.exists() else None
    if novo != antigo:
        ARQUIVO_JSON.write_text(novo, encoding="utf-8")
    print(f"  {ARQUIVO_JSON.name}: {'atualizado' if novo != antigo else 'já estava em dia'}")


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
            f'<div class="grupo-elenco" data-posicao="{FILTROS[id_grupo]}">\n'
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


# ---------------------------------------------------------------- perguntas interativas

def v_posicao(texto, atual):
    if descobrir_grupo(texto) is None:
        raise ValueError(f"Posição não reconhecida. Exemplos: {EXEMPLOS_POSICAO}.")
    return texto


def v_inteiro(texto, atual):
    if not texto.isdigit():
        raise ValueError("Use apenas um número inteiro (0 ou mais).")
    return str(int(texto))


def v_estatistica(texto, atual):
    if texto.startswith("+"):
        if not texto[1:].isdigit():
            raise ValueError("Depois do + coloque um número inteiro, ex.: +1")
        return str(int(atual or 0) + int(texto[1:]))
    return v_inteiro(texto, atual)


def v_altura(texto, atual):
    try:
        valor = float(texto.lower().replace("m", "").replace(",", ".").strip())
    except ValueError:
        raise ValueError("Altura em metros, ex.: 1.75")
    if not 0.5 <= valor <= 2.5:
        raise ValueError("Altura em metros, ex.: 1.75")
    return f"{valor:.2f}"


def v_pe(texto, atual):
    normal = sem_acento(texto)
    for inicio, valor in (("dest", "Destro"), ("d", "Destro"), ("canh", "Canhoto"), ("c", "Canhoto"),
                          ("ambi", "Ambidestro"), ("a", "Ambidestro")):
        if normal.startswith(inicio):
            return valor
    raise ValueError("Use Destro, Canhoto ou Ambidestro (ou só D, C, A).")


def v_fotos_jogo(texto, atual, slug_pessoa=""):
    if sem_acento(texto) == "auto":
        achadas = fotos_da_pasta(slug_pessoa)
        if not achadas:
            raise ValueError(f"Não achei fotos em imagens/perfil/{slug_pessoa}/.")
        print(f"    Fotos encontradas: {', '.join(achadas)}")
        return ", ".join(achadas)
    partes = [p.strip() for p in texto.replace("|", ",").split(",") if p.strip()]
    return ", ".join(partes)


def perguntar(rotulo, atual=None, validar=None, obrigatorio=False, permitir_limpar=True):
    """
    atual=None  -> cadastro novo (Enter deixa vazio, se não for obrigatório).
    atual="..." -> edição (Enter mantém; "-" apaga, se permitido).
    """
    editando = atual is not None
    if editando:
        mostrado = atual if atual != "" else "vazio"
        dica = " (Enter mantém, - apaga)" if permitir_limpar else " (Enter mantém)"
        prompt = f"  {rotulo} [{mostrado}]{dica}: "
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
        if resposta == "-" and editando and permitir_limpar:
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


def fotos_da_pasta(slug_pessoa):
    pasta = PASTA_PERFIL / slug_pessoa
    if not pasta.is_dir():
        return []
    arquivos = [p.name for p in pasta.iterdir() if p.suffix.lower() in EXTENSOES_IMAGEM]
    return sorted(arquivos, key=ordem_natural)


def preencher(linha, novo):
    """Pergunta os campos de uma pessoa e grava as respostas em `linha` (ainda na memória)."""
    def atual(campo):
        return None if novo else linha.get(campo, "")

    linha["nome"] = perguntar("Nome", atual("nome"), obrigatorio=True)
    linha["posicao"] = perguntar("Posição", atual("posicao"), v_posicao, obrigatorio=True)
    staff = eh_staff(linha)

    if staff:
        linha["numero"] = perguntar("Número (comissão técnica não precisa)", atual("numero"), v_inteiro)
    else:
        linha["numero"] = perguntar("Número da camisa", atual("numero"), v_inteiro, obrigatorio=True)

    linha["foto"] = perguntar(f"Arquivo da foto em imagens/jogadores/ (vazio = {foto_padrao(linha['nome'])})", atual("foto"))

    if staff:
        linha["formacao"] = perguntar("Formação / texto do card (ex.: Formado em Ed. Física)", atual("formacao"))
    else:
        linha["idade"] = perguntar("Idade", atual("idade"), v_inteiro)
        linha["pe"] = perguntar("Pé dominante (Destro/Canhoto/Ambidestro)", atual("pe"), v_pe)
        linha["altura"] = perguntar("Altura em metros (ex.: 1.75)", atual("altura"), v_altura)
        linha["titulos"] = perguntar("Títulos (separe com |)", atual("titulos"))
        if not novo:
            for coluna, nome_completo, _ in ESTATISTICAS:
                linha[coluna] = perguntar(f"{nome_completo} (número define, +N soma)", linha.get(coluna) or "0",
                                          v_estatistica, permitir_limpar=False)

    pessoa_slug = slug(linha["nome"])
    linha["fotos_jogo"] = perguntar(
        f"Fotos em jogo, na pasta imagens/perfil/{pessoa_slug}/ (ex.: 1.jpeg, 2.jpeg ou 'auto')",
        atual("fotos_jogo"), lambda t, a: v_fotos_jogo(t, a, pessoa_slug))
    return linha


def procurar(linhas, termo):
    t = sem_acento(termo).strip()
    if not t:
        return []
    exatos = [l for l in linhas if l.get("numero", "") == t or sem_acento(l.get("nome", "")) == t]
    if exatos:
        return exatos
    return [l for l in linhas if t in sem_acento(l.get("nome", ""))]


def escolher(linhas, termo):
    achados = procurar(linhas, termo)
    if not achados:
        print("  Ninguém encontrado com esse nome/camisa.")
        return None
    if len(achados) == 1:
        return achados[0]
    print("  Mais de uma pessoa encontrada:")
    for i, l in enumerate(achados, start=1):
        print(f"    {i}) {l.get('numero') or '--':>3}  {l['nome']} ({l.get('posicao', '')})")
    escolha = input("  Qual delas? (número da lista, Enter cancela): ").strip()
    if escolha.isdigit() and 1 <= int(escolha) <= len(achados):
        return achados[int(escolha) - 1]
    return None


def mostrar_pessoa(linha):
    print(f"\n{linha['nome']} - {linha.get('posicao', '')}"
          + (f" - camisa {linha['numero']}" if linha.get("numero") else ""))


def quadro(linhas):
    atletas = sorted(montar_atletas(linhas), key=lambda a: (GRUPO_STAFF == a["grupo"], chave_ordem(a)))
    print(f"\n{'Nº':>4}  {'Nome':<14}{'Posição':<18}{'Jog':>4}{'Gol':>4}{'Ast':>4}  Idade  Pé          Alt.   Fotos")
    print("-" * 88)
    for a in atletas:
        numero = "--" if a["numero"] is None else a["numero"]
        if a["grupo"] == GRUPO_STAFF:
            print(f"{numero:>4}  {a['nome']:<14}{a['posicao']:<18}{'':>12}  {a['formacao']}")
        else:
            print(f"{numero:>4}  {a['nome']:<14}{a['posicao']:<18}{a['jogos']:>4}{a['gols']:>4}{a['assistencias']:>4}"
                  f"  {a['idade'] or '-':<6}{a['pe'] or '-':<12}{a['altura'] or '-':<7}{len(lista_fotos_jogo(a))}")
    print()


# ---------------------------------------------------------------- comandos

def cmd_listar():
    _, linhas, _ = carregar_tabela()
    quadro(linhas)


def cmd_novo():
    colunas, linhas, separador = carregar_tabela()
    print("Novo integrante do elenco (Ctrl+C para cancelar)")
    linha = {c: "" for c in colunas}
    linha["_linha"] = len(linhas) + 2
    for coluna, _, _ in ESTATISTICAS:
        linha[coluna] = "0"
    preencher(linha, novo=True)

    if any(l["nome"].strip().lower() == linha["nome"].strip().lower() for l in linhas):
        print(f"Aviso: já existe alguém chamado {linha['nome']}. Os dois ficariam com o mesmo endereço de perfil.")
    linhas.append(linha)
    salvar_tabela(colunas, linhas, separador)
    foto = linha["foto"] or foto_padrao(linha["nome"])
    print(f"\n{linha['nome']} salvo no elenco.csv.")
    print(f"Lembrete: coloque a foto em imagens/jogadores/{foto}")
    if not linha.get("fotos_jogo"):
        print(f"Para o carrossel do perfil, use imagens/perfil/{slug(linha['nome'])}/ e depois rode --fotos.")


def cmd_editar(busca=""):
    colunas, linhas, separador = carregar_tabela()
    print("Editar elenco (Ctrl+C cancela a pessoa atual; o que já foi salvo fica)")
    termo = busca
    while True:
        if not termo:
            termo = input("\nCamisa ou nome de quem editar (Enter para encerrar): ").strip()
            if not termo:
                break
        linha = escolher(linhas, termo)
        termo = ""
        if not linha:
            continue
        mostrar_pessoa(linha)
        preencher(linha, novo=False)
        salvar_tabela(colunas, linhas, separador)
        print(f"  {linha['nome']} salvo.")


def cmd_stats():
    colunas, linhas, separador = carregar_tabela()
    jogadores = [l for l in linhas if not eh_staff(l)]
    quadro(linhas)
    print("Para cada estatística: número define, +N soma, Enter mantém. Enter no nome encerra.")
    while True:
        termo = input("\nCamisa ou nome do jogador: ").strip()
        if not termo:
            break
        linha = escolher(jogadores, termo)
        if not linha:
            continue
        mostrar_pessoa(linha)
        for coluna, nome_completo, _ in ESTATISTICAS:
            linha[coluna] = perguntar(nome_completo, linha.get(coluna) or "0", v_estatistica, permitir_limpar=False)
        salvar_tabela(colunas, linhas, separador)
        print(f"  {linha['nome']} salvo.")


def cmd_remover(busca=""):
    colunas, linhas, separador = carregar_tabela()
    termo = busca or input("Camisa ou nome de quem remover (Enter cancela): ").strip()
    if not termo:
        print("Nada foi alterado.")
        return
    linha = escolher(linhas, termo)
    if not linha:
        return
    mostrar_pessoa(linha)
    if input("  Remover do elenco? Digite 's' para confirmar: ").strip().lower() != "s":
        print("Nada foi alterado.")
        return
    linhas.remove(linha)
    salvar_tabela(colunas, linhas, separador)
    print(f"{linha['nome']} removido do elenco.csv. (As fotos em imagens/ não são apagadas.)")


def cmd_fotos():
    colunas, linhas, separador = carregar_tabela()
    if not PASTA_PERFIL.exists():
        print("Pasta imagens/perfil/ não encontrada, nada a fazer.")
        return
    mudou = False
    for linha in linhas:
        achadas = fotos_da_pasta(slug(linha["nome"]))
        if not achadas:
            continue
        texto = ", ".join(achadas)
        if linha.get("fotos_jogo", "") != texto:
            linha["fotos_jogo"] = texto
            mudou = True
            print(f"  {linha['nome']}: {len(achadas)} fotos em jogo ({texto})")
    if mudou:
        salvar_tabela(colunas, linhas, separador)
    else:
        print("fotos_jogo já estava de acordo com as pastas de imagens/perfil/.")


def principal():
    parser = argparse.ArgumentParser(description="Gerencia o elenco: atualiza elenco.html e jogadores.json a partir do elenco.csv.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--novo", action="store_true", help="cadastra um jogador ou integrante da comissão")
    grupo.add_argument("--editar", nargs="?", const="", default=None, metavar="NOME",
                       help="edita qualquer dado de alguém do elenco (nome ou camisa opcional)")
    grupo.add_argument("--stats", action="store_true", help="altera jogos, gols e assistências")
    grupo.add_argument("--remover", nargs="?", const="", default=None, metavar="NOME",
                       help="remove alguém do elenco (nome ou camisa opcional)")
    grupo.add_argument("--fotos", action="store_true", help="preenche fotos_jogo lendo as pastas imagens/perfil/<id>/")
    grupo.add_argument("--listar", action="store_true", help="mostra o quadro do elenco, sem alterar nada")
    args = parser.parse_args()

    if args.listar:
        cmd_listar()
        return

    try:
        if args.novo:
            cmd_novo()
        elif args.editar is not None:
            cmd_editar(args.editar)
        elif args.stats:
            cmd_stats()
        elif args.remover is not None:
            cmd_remover(args.remover)
        elif args.fotos:
            cmd_fotos()
    except (KeyboardInterrupt, EOFError):
        print("\nInterrompido. O que já tinha sido salvo foi mantido.")

    atualizar_pagina(ler_elenco()[0])


if __name__ == "__main__":
    principal()
