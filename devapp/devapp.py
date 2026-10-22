#!/usr/bin/env python3
"""
devapp - gerenciador único do site Pétalas Negras (elenco, jogos, calendário, ranking e servidor local).

Coloque este arquivo na mesma pasta do site_petalas.py e execute:

    python devapp.py

Na primeira vez, escolha a pasta do site (a que tem index.html e a pasta dados/ com os CSVs).
A pasta escolhida (e o último JSON do calendário) ficam salvos em ~/.petalas_gui.json.

Substitui: app_petalas.py, ranking.py, calendario.py e test.py.
Só usa a biblioteca padrão (Python 3.8+).
"""

from __future__ import annotations

import functools
import html
import http.server
import json
import re
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import site_petalas as sp
except ImportError:  # pragma: no cover
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("site_petalas não encontrado",
                         "Coloque o devapp.py na mesma pasta do site_petalas.py.")
    raise SystemExit(1)

CONFIG = Path.home() / ".petalas_gui.json"
PORTA = 8000

POSICOES = ["Goleiro", "Zagueiro", "Lateral direito", "Lateral esquerdo", "Volante", "Meio-campista",
            "Ponta", "Centroavante", "Técnico", "Preparador físico", "Auxiliar técnico", "Fotógrafo"]
PES = ["", "Destro", "Canhoto", "Ambidestro"]
TIPOS_EVENTO = ["jogo", "treino"]

# categorias do ranking: (campo, rótulo, singular, plural, marcador no ranking.html)
RANKINGS = [
    ("gols", "Artilharia", "Gol", "Gols", "RANKING_ARTILHARIA"),
    ("assistencias", "Assistências", "Assistência", "Assistências", "RANKING_ASSISTENCIAS"),
    ("jogos", "Jogos", "Jogo", "Jogos", "RANKING_JOGOS"),
]


# ====================================================================== utilidades de interface


def _linhas(texto: str) -> list:
    """Texto de uma caixa multilinha -> lista de itens (uma linha = um item; vírgulas também separam)."""
    itens = []
    for linha in texto.splitlines():
        itens += sp._separar_lista(linha)
    return itens


def _tabela(pai, colunas, altura=14):
    """Treeview com barra de rolagem. colunas: [(id, título, largura, âncora)]."""
    quadro = ttk.Frame(pai)
    tv = ttk.Treeview(quadro, columns=[c[0] for c in colunas], show="headings",
                      selectmode="browse", height=altura)
    for id_, titulo, largura, ancora in colunas:
        tv.heading(id_, text=titulo)
        tv.column(id_, width=largura, anchor=ancora, stretch=(id_ in ("nome", "adversario", "titulo")))
    barra = ttk.Scrollbar(quadro, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=barra.set)
    tv.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")
    return quadro, tv


class Dialogo(tk.Toplevel):
    """
    Formulário genérico. campos: [(chave, rótulo, tipo, extra)] com tipo 'entry', 'combo' (extra = valores)
    ou 'text' (extra = altura). ao_salvar(dict) -> True fecha o diálogo; False mantém aberto
    (assim o que foi digitado não se perde quando há erro de validação).
    """

    def __init__(self, mestre, titulo, campos, valores=None, ao_salvar=None, dica=None, largura=46):
        super().__init__(mestre)
        self.title(titulo)
        self.transient(mestre)
        self.resizable(False, False)
        self.ao_salvar = ao_salvar
        self.widgets = {}
        valores = valores or {}

        corpo = ttk.Frame(self, padding=12)
        corpo.grid(sticky="nsew")
        linha = 0
        if dica:
            ttk.Label(corpo, text=dica, foreground="#555", wraplength=470, justify="left").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
            linha = 1
        for i, campo in enumerate(campos, start=linha):
            chave, rotulo, tipo = campo[0], campo[1], campo[2]
            extra = campo[3] if len(campo) > 3 else None
            ttk.Label(corpo, text=rotulo).grid(row=i, column=0, sticky="nw", padx=(0, 10), pady=3)
            inicial = str(valores.get(chave, "") or "")
            if tipo == "combo":
                w = ttk.Combobox(corpo, values=extra or [], width=largura - 3)
                w.set(inicial)
            elif tipo == "text":
                w = tk.Text(corpo, width=largura, height=extra or 5, wrap="word", undo=True)
                w.insert("1.0", inicial)
            else:
                w = ttk.Entry(corpo, width=largura)
                w.insert(0, inicial)
            if tipo != "text":
                w.bind("<Return>", lambda _e: self._salvar())
            w.grid(row=i, column=1, sticky="ew", pady=3)
            self.widgets[chave] = (tipo, w)

        botoes = ttk.Frame(corpo)
        botoes.grid(row=len(campos) + linha, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(botoes, text="Salvar", command=self._salvar).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())

        self.update_idletasks()
        x = mestre.winfo_rootx() + (mestre.winfo_width() - self.winfo_width()) // 2
        y = mestre.winfo_rooty() + max(20, (mestre.winfo_height() - self.winfo_height()) // 3)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        primeiro = next(iter(self.widgets.values()))[1]
        primeiro.focus_set()
        self.grab_set()
        self.wait_window()

    def _valores(self) -> dict:
        saida = {}
        for chave, (tipo, w) in self.widgets.items():
            saida[chave] = w.get("1.0", "end").strip() if tipo == "text" else w.get().strip()
        return saida

    def _salvar(self):
        if self.ao_salvar is None or self.ao_salvar(self._valores()):
            self.destroy()


# ====================================================================== ranking (HTML a partir do elenco)


def _ranking_ordenado(atletas, campo):
    com_valor = [a for a in atletas if a["grupo"] != sp.GRUPO_STAFF and a.get(campo, 0) > 0]
    com_valor.sort(key=lambda a: (a.get(campo, 0), a.get("jogos", 0)), reverse=True)
    return com_valor


def _posicoes_ranking(ordenados, campo):
    """[(posição, atleta)] - empates dividem a mesma posição."""
    saida, pos, ultimo = [], 0, None
    for a in ordenados:
        if a[campo] != ultimo:
            pos += 1
            ultimo = a[campo]
        saida.append((pos, a))
    return saida


def _html_ranking(atletas, campo, singular, plural) -> str:
    ordenados = _ranking_ordenado(atletas, campo)
    if not ordenados:
        return '<div class="vazio">Nenhum registro para esta categoria.</div>'
    elementos, ultimo = [], None
    for pos, a in _posicoes_ranking(ordenados, campo):
        valor = a[campo]
        if valor != ultimo:
            ultimo = valor
            elementos.append(f'<div class="ranking-divisor-grupo">{valor} {singular if valor == 1 else plural}</div>')
        nome = html.escape(a["nome"], quote=True)
        camisa = f'<span class="atleta-numero">#{a["numero"]}</span>' if a["numero"] is not None else ""
        foto = html.escape("imagens/jogadores/" + a["foto"], quote=True)
        elementos.append(f'''<a class="ranking-card-item" href="jogador.html?id={a["slug"]}">
  <div class="ranking-card-esquerda">
    <span class="ranking-posicao">{pos}º</span>
    <img src="{foto}" alt="{nome}" class="ranking-foto-mini" onerror="this.src='imagens/logo.jpeg'">
    <div class="ranking-info-atleta">
      <div class="ranking-nome-linha">
        <strong>{nome}</strong>
        {camisa}
      </div>
      <span class="ranking-posicao-sub">{html.escape(a["posicao"] or "-")}</span>
    </div>
  </div>
  <div class="ranking-stat-valor">{valor}</div>
</a>''')
    return "\n".join(elementos)


def gerar_ranking_html(site: "sp.Site", atletas) -> bool:
    """Regrava os blocos de ranking.html. Devolve True se o arquivo mudou."""
    arquivo = site.raiz / "ranking.html"
    if not arquivo.exists():
        raise sp.ErroArquivo(f"não encontrei ranking.html em {site.raiz}.")
    texto = original = arquivo.read_text(encoding="utf-8")
    for campo, _, singular, plural, marca in RANKINGS:
        padrao = re.compile(rf"<!-- {marca}_INICIO -->.*?<!-- {marca}_FIM -->", re.DOTALL)
        if not padrao.search(texto):
            raise sp.ErroArquivo(f"ranking.html não tem os marcadores <!-- {marca}_INICIO --> e "
                                 f"<!-- {marca}_FIM -->.")
        novo = f"<!-- {marca}_INICIO -->\n{_html_ranking(atletas, campo, singular, plural)}\n<!-- {marca}_FIM -->"
        texto = padrao.sub(lambda _m, n=novo: n, texto, count=1)
    if texto != original:
        arquivo.write_text(texto, encoding="utf-8")
        return True
    return False


# ====================================================================== calendário (JSON mensal -> HTML)


def _html_grade_calendario(dados: dict) -> str:
    saida = []
    for dia in dados.get("offset_dias_anteriores", []):
        saida.append(f'          <div class="dia-celula outro-mes"><span class="num-dia">{dia}</span></div>')
    eventos = dados.get("eventos", {})
    for d in range(1, int(dados.get("total_dias_mes", 31)) + 1):
        bloco = f'          <div class="dia-celula">\n            <span class="num-dia">{d}</span>'
        ev = eventos.get(str(d))
        if ev:
            classe = "evento-jogo" if ev.get("tipo") == "jogo" else "evento-treino"
            bloco += (f'\n            <div class="evento {classe}">\n              '
                      f'<strong>{html.escape(ev.get("hora", ""))}</strong> {html.escape(ev.get("titulo", ""))}\n'
                      f'            </div>')
        saida.append(bloco + "\n          </div>")
    return "\n".join(saida)


def gerar_calendario_html(site: "sp.Site", dados: dict) -> None:
    arquivo = site.raiz / "calendario.html"
    if not arquivo.exists():
        raise sp.ErroArquivo(f"não encontrei calendario.html em {site.raiz}.")
    texto = arquivo.read_text(encoding="utf-8")
    titulo = f'<h2>{html.escape(dados.get("mes_ano", "Calendário"))}</h2>'
    trocas = [
        (r"<!-- TITULO_MES:INICIO -->.*?<!-- TITULO_MES:FIM -->",
         f"<!-- TITULO_MES:INICIO -->\n          {titulo}\n          <!-- TITULO_MES:FIM -->"),
        (r"<!-- CALENDARIO_INICIO -->.*?<!-- CALENDARIO_FIM -->",
         f"<!-- CALENDARIO_INICIO -->\n{_html_grade_calendario(dados)}\n          <!-- CALENDARIO_FIM -->"),
    ]
    for padrao, novo in trocas:
        regex = re.compile(padrao, re.DOTALL)
        if not regex.search(texto):
            raise sp.ErroArquivo("calendario.html não tem os marcadores TITULO_MES / CALENDARIO.")
        texto = regex.sub(lambda _m, n=novo: n, texto, count=1)
    arquivo.write_text(texto, encoding="utf-8")


# ====================================================================== aplicativo


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pétalas Negras - gerenciador do site")
        self.geometry("1000x740")
        self.minsize(860, 580)
        self.site = None
        self.servidor = None
        self.caminho_cal = None
        self.dados_cal = {}
        self.var_pasta = tk.StringVar()
        self.var_auto = tk.BooleanVar(value=True)
        self.var_ranking = tk.StringVar(value=RANKINGS[0][0])

        self._montar_topo()
        self._montar_abas()
        self._montar_rodape()
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        pasta = self._config().get("pasta", "")
        if pasta and Path(pasta).is_dir():
            self.abrir_site(pasta)
        else:
            self.after(200, self.escolher_pasta)

    # ------------------------------------------------------------ montagem

    def _montar_topo(self):
        topo = ttk.Frame(self, padding=(10, 8))
        topo.pack(fill="x")
        ttk.Label(topo, text="Pasta do site:").pack(side="left")
        ttk.Entry(topo, textvariable=self.var_pasta, state="readonly").pack(
            side="left", fill="x", expand=True, padx=8)
        ttk.Button(topo, text="Escolher...", command=self.escolher_pasta).pack(side="left")
        ttk.Button(topo, text="Recarregar", command=self.recarregar).pack(side="left", padx=(6, 0))
        ttk.Button(topo, text="Ver no navegador", command=self.abrir_navegador).pack(side="left", padx=(6, 0))

    def _montar_abas(self):
        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=10)
        self._aba_elenco()
        self._aba_jogos()
        self._aba_calendario()
        self._aba_ranking()

    def _aba_elenco(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Elenco  ")
        quadro, self.tv_elenco = _tabela(aba, [
            ("numero", "Nº", 50, "center"), ("nome", "Nome", 220, "w"), ("posicao", "Posição", 170, "w"),
            ("jogos", "Jogos", 70, "center"), ("gols", "Gols", 70, "center"),
            ("assistencias", "Assist.", 70, "center")])
        quadro.pack(fill="both", expand=True)
        self.tv_elenco.bind("<Double-1>", lambda _e: self.editar_pessoa())

        barra = ttk.Frame(aba)
        barra.pack(fill="x", pady=(8, 0))
        for texto, cmd in (("Adicionar...", self.adicionar_pessoa), ("Editar...", self.editar_pessoa),
                           ("Remover", self.remover_pessoa)):
            ttk.Button(barra, text=texto, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=8)
        for texto, campo in (("+1 jogo", "jogos"), ("+1 gol", "gols"), ("+1 assistência", "assistencias")):
            ttk.Button(barra, text=texto, command=lambda c=campo: self.somar_estatistica(c)).pack(
                side="left", padx=(0, 6))
        ttk.Button(barra, text="Sincronizar fotos de perfil", command=self.sincronizar_fotos_perfil).pack(
            side="right")

    def _aba_jogos(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Jogos  ")
        quadro, self.tv_jogos = _tabela(aba, [
            ("data", "Data", 90, "center"), ("hora", "Hora", 60, "center"),
            ("adversario", "Adversário", 240, "w"), ("local", "Local", 200, "w"),
            ("placar", "Placar", 80, "center"), ("resultado", "Resultado", 90, "center")])
        quadro.pack(fill="both", expand=True)
        self.tv_jogos.bind("<Double-1>", lambda _e: self.editar_jogo())

        barra = ttk.Frame(aba)
        barra.pack(fill="x", pady=(8, 0))
        for texto, cmd in (("Adicionar...", self.adicionar_jogo), ("Editar...", self.editar_jogo),
                           ("Remover", self.remover_jogo)):
            ttk.Button(barra, text=texto, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=8)
        for texto, cmd in (("Placar...", self.definir_placar), ("Escalação...", self.definir_escalacao),
                           ("Gols...", self.definir_gols)):
            ttk.Button(barra, text=texto, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Button(barra, text="Sincronizar fotos dos jogos", command=self.sincronizar_fotos_jogos).pack(
            side="right")

    def _aba_calendario(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Calendário  ")

        topo = ttk.Frame(aba)
        topo.pack(fill="x", pady=(0, 8))
        ttk.Button(topo, text="Abrir JSON do mês...", command=self.abrir_json_calendario).pack(side="left")
        ttk.Button(topo, text="Novo mês...", command=self.novo_mes).pack(side="left", padx=6)
        self.lbl_cal = ttk.Label(topo, text="Nenhum arquivo selecionado", foreground="#b00020")
        self.lbl_cal.pack(side="left", padx=8)

        quadro, self.tv_cal = _tabela(aba, [
            ("dia", "Dia", 60, "center"), ("tipo", "Tipo", 90, "center"),
            ("hora", "Hora", 70, "center"), ("titulo", "Descrição / Adversário", 380, "w")])
        quadro.pack(fill="both", expand=True)
        self.tv_cal.bind("<Double-1>", lambda _e: self.editar_evento())

        barra = ttk.Frame(aba)
        barra.pack(fill="x", pady=(8, 0))
        for texto, cmd in (("Adicionar...", self.adicionar_evento), ("Editar...", self.editar_evento),
                           ("Remover", self.remover_evento)):
            ttk.Button(barra, text=texto, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Button(barra, text="Atualizar calendario.html", command=self.atualizar_calendario).pack(side="right")

    def _aba_ranking(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Ranking  ")

        topo = ttk.Frame(aba)
        topo.pack(fill="x", pady=(0, 8))
        for campo, rotulo, *_ in RANKINGS:
            ttk.Radiobutton(topo, text=rotulo, value=campo, variable=self.var_ranking,
                            command=self._preencher_ranking).pack(side="left", padx=(0, 12))

        quadro, self.tv_ranking = _tabela(aba, [
            ("pos", "Pos.", 60, "center"), ("nome", "Nome", 260, "w"), ("posicao", "Posição", 170, "w"),
            ("valor", "Total", 80, "center")])
        quadro.pack(fill="both", expand=True)

        barra = ttk.Frame(aba)
        barra.pack(fill="x", pady=(8, 0))
        ttk.Label(barra, text="Os números vêm da aba Elenco.", foreground="#555").pack(side="left")
        ttk.Button(barra, text="Atualizar ranking.html", command=self.atualizar_ranking).pack(side="right")

    def _montar_rodape(self):
        rodape = ttk.Frame(self, padding=(10, 6))
        rodape.pack(fill="both")
        linha = ttk.Frame(rodape)
        linha.pack(fill="x")
        ttk.Button(linha, text="Atualizar site agora", command=self.atualizar_site).pack(side="left")
        ttk.Checkbutton(linha, text="Atualizar o site automaticamente após cada alteração",
                        variable=self.var_auto).pack(side="left", padx=12)
        ttk.Button(linha, text="Limpar log", command=self._limpar_log).pack(side="right")
        self.txt_log = ScrolledText(rodape, height=7, state="disabled", wrap="word")
        self.txt_log.pack(fill="both", expand=True, pady=(6, 0))
        self.txt_log.tag_configure("erro", foreground="#b00020")
        self.txt_log.tag_configure("aviso", foreground="#9a6700")

    # ------------------------------------------------------------ log e execução

    def log(self, texto: str, tag: str = ""):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", texto + "\n", tag)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _limpar_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    def _erro(self, e: Exception):
        self.log(f"Erro: {e}", "erro")
        messagebox.showerror("Não foi possível concluir", str(e), parent=self)

    def _executar(self, descricao, func, *args, **kwargs):
        """Chama a biblioteca. Devolve (ok, resultado). Erros viram mensagem na tela."""
        if self.site is None:
            messagebox.showinfo("Pasta do site", "Escolha primeiro a pasta do site.", parent=self)
            return False, None
        try:
            resultado = func(*args, **kwargs)
        except (sp.ErroDados, OSError, ValueError) as e:
            self._erro(e)
            return False, None
        self.log(descricao)
        return True, resultado

    def _depois_de_alterar(self):
        self.recarregar_listas()
        if self.var_auto.get():
            self.atualizar_site()

    # ------------------------------------------------------------ configuração e pasta do site

    @staticmethod
    def _config() -> dict:
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _salvar_config(self, **novos):
        dados = self._config()
        dados.update(novos)
        try:
            CONFIG.write_text(json.dumps(dados), encoding="utf-8")
        except OSError:
            pass

    def escolher_pasta(self):
        pasta = filedialog.askdirectory(parent=self, title="Escolha a pasta do site (com index.html)",
                                        initialdir=self.var_pasta.get() or str(Path.home()))
        if pasta:
            self.abrir_site(pasta)

    def abrir_site(self, pasta: str):
        self._parar_servidor()
        self.site = sp.Site(pasta)
        self.var_pasta.set(str(self.site.raiz))
        self._salvar_config(pasta=str(self.site.raiz))
        self.log(f"Site aberto: {self.site.raiz} (dados em {self.site.pasta_dados})")
        self.recarregar_listas()
        ultimo = self._config().get("calendario", "")
        if ultimo and Path(ultimo).is_file():
            self._carregar_calendario(ultimo)

    def recarregar(self):
        if self.site is not None:
            self.abrir_site(str(self.site.raiz))

    def recarregar_listas(self):
        self._preencher_elenco()
        self._preencher_jogos()
        self._preencher_ranking()

    def _preencher_elenco(self):
        self.tv_elenco.delete(*self.tv_elenco.get_children())
        if self.site is None:
            return
        try:
            for a in self.site.listar_elenco():
                staff = a["grupo"] == sp.GRUPO_STAFF
                self.tv_elenco.insert("", "end", iid=a["nome"], values=(
                    "" if a["numero"] is None else a["numero"], a["nome"], a["posicao"],
                    "" if staff else a["jogos"], "" if staff else a["gols"],
                    "" if staff else a["assistencias"]))
        except sp.ErroDados as e:
            self.log(f"Erro ao ler o elenco: {e}", "erro")

    def _preencher_jogos(self):
        self.tv_jogos.delete(*self.tv_jogos.get_children())
        if self.site is None:
            return
        rotulos = {"vitoria": "Vitória", "derrota": "Derrota", "empate": "Empate", "": ""}
        try:
            for j in self.site.listar_jogos():
                self.tv_jogos.insert("", "end", iid=j["id"], values=(
                    j["data_br"], j["hora"], j["adversario"], j["local"], j["placar"],
                    rotulos.get(j["resultado"], "")))
        except sp.ErroDados as e:
            self.log(f"Erro ao ler os jogos: {e}", "erro")

    def _preencher_ranking(self):
        self.tv_ranking.delete(*self.tv_ranking.get_children())
        if self.site is None:
            return
        campo = self.var_ranking.get()
        try:
            ordenados = _ranking_ordenado(self.site.listar_elenco(), campo)
        except sp.ErroDados as e:
            self.log(f"Erro ao ler o elenco: {e}", "erro")
            return
        for i, (pos, a) in enumerate(_posicoes_ranking(ordenados, campo)):
            self.tv_ranking.insert("", "end", iid=str(i), values=(f"{pos}º", a["nome"], a["posicao"], a[campo]))

    def _selecionado(self, tv, o_que):
        sel = tv.selection()
        if not sel:
            messagebox.showinfo("Seleção", f"Selecione {o_que} na lista.", parent=self)
            return None
        return sel[0]

    # ------------------------------------------------------------ atualizar páginas

    def atualizar_site(self):
        """Regrava elenco.html, jogos.html, index.html, JSONs e (se existir) ranking.html."""
        ok, rel = self._executar("Gerando páginas e JSONs...",
                                 self.site.atualizar_tudo if self.site else None)
        if not ok or rel is None:
            return
        e, j = rel["elenco"], rel["jogos"]
        self.log(f"Site atualizado: {e['atletas']} atletas, {e['comissao']} na comissão técnica, "
                 f"{j['jogos']} jogos ({j['proximos']} próximos, {j['realizados']} realizados).")
        for aviso in rel["avisos"]:
            self.log(f"Aviso: {aviso}", "aviso")
        if (self.site.raiz / "ranking.html").exists():
            self._gerar_ranking(silencioso=True)

    def _gerar_ranking(self, silencioso=False):
        try:
            gerar_ranking_html(self.site, self.site.listar_elenco())
        except (sp.ErroDados, OSError) as e:
            if silencioso:
                self.log(f"Aviso: ranking.html não atualizado ({e})", "aviso")
            else:
                self._erro(e)
            return False
        self.log("ranking.html atualizado.")
        return True

    def atualizar_ranking(self):
        if self.site is None:
            return self.escolher_pasta()
        self._gerar_ranking()

    # ------------------------------------------------------------ servidor local

    def abrir_navegador(self):
        if self.site is None:
            return self.escolher_pasta()
        if self.servidor is None:
            try:
                manipulador = functools.partial(http.server.SimpleHTTPRequestHandler,
                                                directory=str(self.site.raiz))
                self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", PORTA), manipulador)
            except OSError as e:
                return self._erro(OSError(f"não consegui abrir a porta {PORTA}: {e}"))
            threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
            self.log(f"Servidor local iniciado em http://localhost:{PORTA}")
        webbrowser.open(f"http://localhost:{PORTA}")

    def _parar_servidor(self):
        if self.servidor is not None:
            self.servidor.shutdown()
            self.servidor.server_close()
            self.servidor = None

    def _fechar(self):
        self._parar_servidor()
        self.destroy()

    # ------------------------------------------------------------ elenco

    def _campos_pessoa(self, com_stats: bool):
        campos = [
            ("nome", "Nome", "entry"), ("posicao", "Posição", "combo", POSICOES),
            ("numero", "Camisa (vazio p/ comissão)", "entry"), ("idade", "Idade", "entry"),
            ("pe", "Pé", "combo", PES), ("altura", "Altura (m)", "entry"),
            ("titulos", "Títulos", "entry"), ("formacao", "Formação (comissão)", "entry"),
            ("foto", "Arquivo da foto (vazio = padrão)", "entry"),
            ("fotos_jogo", "Fotos em jogo (separadas por vírgula)", "text", 2),
        ]
        if com_stats:
            campos += [("jogos", "Jogos", "entry"), ("gols", "Gols", "entry"),
                       ("assistencias", "Assistências", "entry")]
        return campos

    def adicionar_pessoa(self):
        if self.site is None:
            return self.escolher_pasta()

        def salvar(v):
            extras = {k: val for k, val in v.items()
                      if k not in ("nome", "posicao", "numero") and val != ""}
            ok, _ = self._executar(f"Adicionado: {v['nome']}", self.site.adicionar_pessoa,
                                   v["nome"], v["posicao"], v["numero"] or None, **extras)
            if ok:
                self._depois_de_alterar()
            return ok

        Dialogo(self, "Adicionar ao elenco", self._campos_pessoa(False), ao_salvar=salvar,
                dica="Jogadores precisam de camisa. Para a comissão técnica use uma posição como "
                     "Técnico, Preparador físico ou Fotógrafo e deixe a camisa vazia.")

    def editar_pessoa(self):
        nome = self._selecionado(self.tv_elenco, "uma pessoa")
        if nome is None:
            return
        ok, p = self._executar(f"Abrindo {nome}...", self.site.obter_pessoa, nome)
        if not ok:
            return
        staff = p["grupo"] == sp.GRUPO_STAFF
        valores = dict(p)
        valores["numero"] = "" if p["numero"] is None else p["numero"]
        valores["fotos_jogo"] = ", ".join(p["fotos_jogo"])
        valores["foto"] = p["foto"] if p["foto"] != sp._foto_padrao(p["nome"]) else ""

        def salvar(v):
            ok2, _ = self._executar(f"Atualizado: {v['nome']}", self.site.editar_pessoa, nome, **dict(v))
            if ok2:
                self._depois_de_alterar()
            return ok2

        Dialogo(self, f"Editar - {nome}", self._campos_pessoa(not staff), valores, salvar,
                dica="Campo vazio apaga o valor. Mudar o nome muda o endereço do perfil "
                     "(e a pasta imagens/perfil/<nome>/).")

    def remover_pessoa(self):
        nome = self._selecionado(self.tv_elenco, "uma pessoa")
        if nome is None:
            return
        if not messagebox.askyesno("Remover", f"Remover {nome} do elenco?\n(As fotos não são apagadas.)",
                                   parent=self):
            return
        ok, _ = self._executar(f"Removido: {nome}", self.site.remover_pessoa, nome)
        if ok:
            self._depois_de_alterar()

    def somar_estatistica(self, campo: str):
        nome = self._selecionado(self.tv_elenco, "um jogador")
        if nome is None:
            return
        ok, _ = self._executar(f"{nome}: +1 {campo}", self.site.atualizar_estatisticas, nome,
                               **{campo: "+1"})
        if ok:
            self._depois_de_alterar()

    def sincronizar_fotos_perfil(self):
        ok, mudou = self._executar("Sincronizando fotos de perfil...", self.site.sincronizar_fotos_perfil)
        if not ok:
            return
        if mudou:
            for nome, fotos in mudou.items():
                self.log(f"  {nome}: {len(fotos)} foto(s)")
            self._depois_de_alterar()
        else:
            self.log("  nada novo em imagens/perfil/.")

    # ------------------------------------------------------------ jogos

    def adicionar_jogo(self):
        if self.site is None:
            return self.escolher_pasta()

        def salvar(v):
            ok, _ = self._executar(f"Jogo adicionado: {v['adversario']} em {v['data']}",
                                   self.site.adicionar_jogo, v["data"], v["adversario"],
                                   hora=v["hora"], local=v["local"], placar=v["placar"])
            if ok:
                self._depois_de_alterar()
            return ok

        Dialogo(self, "Adicionar jogo", [
            ("data", "Data (DD/MM/AAAA)", "entry"), ("hora", "Hora (ex.: 10:00)", "entry"),
            ("adversario", "Adversário", "entry"), ("local", "Local", "entry"),
            ("placar", "Placar (nossos x deles)", "entry")],
            {"data": date.today().strftime("%d/%m/%Y")}, salvar)

    def _jogo_selecionado(self):
        return self._selecionado(self.tv_jogos, "um jogo")

    def _linha_bruta_jogo(self, id_jogo: str) -> dict:
        _, linhas, _ = self.site._tabela_jogos()
        return self.site._achar_jogo(linhas, id_jogo)

    def editar_jogo(self):
        id_jogo = self._jogo_selecionado()
        if id_jogo is None:
            return
        ok, j = self._executar("Abrindo jogo...", self.site.obter_jogo, id_jogo)
        if not ok:
            return
        valores = {"data": j["data_br"], "hora": j["hora"], "adversario": j["adversario"],
                   "local": j["local"], "placar": j["placar"], "fotos": ", ".join(j["fotos"])}

        def salvar(v):
            ok2, _ = self._executar(f"Jogo atualizado: {v['adversario']}", self.site.editar_jogo,
                                    id_jogo, **v)
            if ok2:
                self._depois_de_alterar()
            return ok2

        Dialogo(self, "Editar jogo", [
            ("data", "Data (DD/MM/AAAA)", "entry"), ("hora", "Hora", "entry"),
            ("adversario", "Adversário", "entry"), ("local", "Local", "entry"),
            ("placar", "Placar (nossos x deles)", "entry"),
            ("fotos", "Fotos (separadas por vírgula)", "text", 2)], valores, salvar,
            dica="Campo vazio apaga o valor.")

    def remover_jogo(self):
        id_jogo = self._jogo_selecionado()
        if id_jogo is None:
            return
        if not messagebox.askyesno("Remover", f"Remover o jogo {id_jogo}?\n(As fotos não são apagadas.)",
                                   parent=self):
            return
        ok, _ = self._executar(f"Jogo removido: {id_jogo}", self.site.remover_jogo, id_jogo)
        if ok:
            self._depois_de_alterar()

    def definir_placar(self):
        id_jogo = self._jogo_selecionado()
        if id_jogo is None:
            return
        atual = self.tv_jogos.set(id_jogo, "placar")
        texto = simpledialog.askstring("Placar", "Placar no formato nossos x deles (ex.: 2 x 1).\n"
                                       "Deixe vazio para apagar.", initialvalue=atual, parent=self)
        if texto is None:
            return
        ok, _ = self._executar(f"Placar de {id_jogo}: {texto.strip() or '(apagado)'}",
                               self.site.definir_placar, id_jogo, texto.strip())
        if ok:
            self._depois_de_alterar()

    def definir_escalacao(self):
        id_jogo = self._jogo_selecionado()
        if id_jogo is None:
            return
        try:
            bruta = self._linha_bruta_jogo(id_jogo)
        except sp.ErroDados as e:
            return self._erro(e)
        valores = {c: "\n".join(sp._separar_lista(bruta.get(c, "")))
                   for c in ("escalacao", "reservas", "substituicoes")}

        def salvar(v):
            ok, _ = self._executar(f"Escalação atualizada: {id_jogo}", self.site.definir_escalacao,
                                   id_jogo, titulares=_linhas(v["escalacao"]),
                                   reservas=_linhas(v["reservas"]),
                                   substituicoes=_linhas(v["substituicoes"]))
            if ok:
                self._depois_de_alterar()
            return ok

        Dialogo(self, f"Escalação - {id_jogo}", [
            ("escalacao", "Titulares", "text", 8), ("reservas", "Reservas", "text", 4),
            ("substituicoes", "Substituições", "text", 3)], valores, salvar, largura=52,
            dica="Um por linha: nome ou número da camisa. Quem não é do elenco: "
                 "Fulano (suporte) ou Fulano (suporte, Goleiro).\n"
                 "Substituições: Quem entrou > Quem saiu 60'  (o minuto é opcional).")

    def definir_gols(self):
        id_jogo = self._jogo_selecionado()
        if id_jogo is None:
            return
        try:
            bruta = self._linha_bruta_jogo(id_jogo)
        except sp.ErroDados as e:
            return self._erro(e)
        valores = {"gols": "\n".join(sp._separar_lista(bruta.get("gols", "")))}

        def salvar(v):
            ok, _ = self._executar(f"Gols atualizados: {id_jogo}", self.site.definir_gols,
                                   id_jogo, _linhas(v["gols"]))
            if ok:
                self._depois_de_alterar()
            return ok

        Dialogo(self, f"Gols - {id_jogo}", [("gols", "Gols", "text", 10)], valores, salvar, largura=52,
                dica="Um por linha, ex.:\n  Rulim 23' (ast. Paiva)\n  adv 40'\n  Novaes 70'\n"
                     "Use 'adv' para gol do adversário. Os gols devem bater com o placar.")

    def sincronizar_fotos_jogos(self):
        ok, mudou = self._executar("Sincronizando fotos dos jogos...", self.site.sincronizar_fotos_jogos)
        if not ok:
            return
        if mudou:
            for id_jogo, fotos in mudou.items():
                self.log(f"  {id_jogo}: {len(fotos)} foto(s)")
            self._depois_de_alterar()
        else:
            self.log("  nada novo em imagens/jogos/.")

    # ------------------------------------------------------------ calendário

    def _carregar_calendario(self, caminho: str) -> bool:
        try:
            dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
            if not isinstance(dados, dict):
                raise ValueError("o JSON do calendário deve ser um objeto.")
        except (OSError, ValueError) as e:
            self._erro(e)
            return False
        self.caminho_cal, self.dados_cal = caminho, dados
        self.lbl_cal.config(text=f"{dados.get('mes_ano', '?')}  ({Path(caminho).name})", foreground="#15803d")
        self._salvar_config(calendario=caminho)
        self.log(f"Calendário carregado: {caminho}")
        self._preencher_calendario()
        return True

    def _preencher_calendario(self):
        self.tv_cal.delete(*self.tv_cal.get_children())
        eventos = self.dados_cal.get("eventos", {})
        for dia in sorted(eventos, key=lambda d: int(d) if str(d).isdigit() else 0):
            ev = eventos[dia]
            self.tv_cal.insert("", "end", iid=str(dia), values=(
                dia, ev.get("tipo", ""), ev.get("hora", ""), ev.get("titulo", "")))

    def _gravar_calendario(self) -> bool:
        try:
            Path(self.caminho_cal).write_text(
                json.dumps(self.dados_cal, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            self._erro(e)
            return False
        self._preencher_calendario()
        if self.var_auto.get():
            self.atualizar_calendario()
        return True

    def _exige_calendario(self) -> bool:
        if self.site is None:
            self.escolher_pasta()
            return False
        if not self.caminho_cal:
            messagebox.showinfo("Calendário", "Abra um JSON do mês (ou crie um novo) primeiro.", parent=self)
            return False
        return True

    def abrir_json_calendario(self):
        if self.site is None:
            return self.escolher_pasta()
        caminho = filedialog.askopenfilename(
            parent=self, title="JSON do mês", filetypes=[("Arquivos JSON", "*.json")],
            initialdir=str(self.site.pasta_dados))
        if caminho:
            self._carregar_calendario(caminho)

    def novo_mes(self):
        if self.site is None:
            return self.escolher_pasta()

        def salvar(v):
            if not v["mes_ano"] or not v["total"].isdigit() or not 28 <= int(v["total"]) <= 31:
                messagebox.showwarning("Aviso", "Informe o mês/ano e o total de dias (28 a 31).", parent=self)
                return False
            anteriores = [int(x) for x in re.split(r"[,\s;]+", v["anteriores"]) if x.isdigit()]
            sugerido = f"eventos_{sp.slug(v['mes_ano']).replace('-', '_')}.json"
            caminho = filedialog.asksaveasfilename(
                parent=self, defaultextension=".json", initialfile=sugerido,
                initialdir=str(self.site.pasta_dados), filetypes=[("Arquivos JSON", "*.json")])
            if not caminho:
                return False
            novo = {"mes_ano": v["mes_ano"], "offset_dias_anteriores": anteriores,
                    "total_dias_mes": int(v["total"]), "eventos": {}}
            try:
                Path(caminho).write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as e:
                self._erro(e)
                return False
            return self._carregar_calendario(caminho)

        Dialogo(self, "Novo mês", [
            ("mes_ano", "Mês e ano (ex.: Novembro 2026)", "entry"),
            ("anteriores", "Dias do mês anterior (ex.: 29, 30, 31)", "entry"),
            ("total", "Total de dias do mês", "entry")],
            {"total": "30"}, salvar)

    def _dialogo_evento(self, titulo, valores, dia_fixo=None):
        total = int(self.dados_cal.get("total_dias_mes", 31))

        def salvar(v):
            dia = dia_fixo or v["dia"]
            if not dia.isdigit() or not 1 <= int(dia) <= total:
                messagebox.showwarning("Aviso", f"O dia deve ser um número de 1 a {total}.", parent=self)
                return False
            try:
                hora = sp.normalizar_hora(v["hora"]) if v["hora"] else ""
            except sp.ErroDados as e:
                messagebox.showwarning("Aviso", str(e), parent=self)
                return False
            self.dados_cal.setdefault("eventos", {})[str(int(dia))] = {
                "tipo": v["tipo"] if v["tipo"] in TIPOS_EVENTO else "jogo", "hora": hora, "titulo": v["titulo"]}
            self.log(f"Evento salvo no dia {int(dia)}: [{v['tipo'].upper()}] {hora} - {v['titulo']}")
            return self._gravar_calendario()

        Dialogo(self, titulo, [
            ("dia", "Dia do mês", "entry"), ("tipo", "Tipo", "combo", TIPOS_EVENTO),
            ("hora", "Horário (ex.: 10:00)", "entry"), ("titulo", "Descrição / Adversário", "entry")],
            valores, salvar, dica="Se já houver evento no dia, ele é substituído.")

    def adicionar_evento(self):
        if self._exige_calendario():
            self._dialogo_evento("Adicionar evento", {"tipo": "jogo"})

    def editar_evento(self):
        if not self._exige_calendario():
            return
        dia = self._selecionado(self.tv_cal, "um evento")
        if dia is None:
            return
        ev = self.dados_cal.get("eventos", {}).get(dia, {})
        self._dialogo_evento(f"Editar evento do dia {dia}", {"dia": dia, **ev})

    def remover_evento(self):
        if not self._exige_calendario():
            return
        dia = self._selecionado(self.tv_cal, "um evento")
        if dia is None:
            return
        if not messagebox.askyesno("Remover", f"Remover o evento do dia {dia}?", parent=self):
            return
        self.dados_cal.get("eventos", {}).pop(dia, None)
        self.log(f"Evento do dia {dia} removido.")
        self._gravar_calendario()

    def atualizar_calendario(self):
        if not self._exige_calendario():
            return
        ok, _ = self._executar("calendario.html atualizado.", gerar_calendario_html, self.site, self.dados_cal)
        return ok


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
