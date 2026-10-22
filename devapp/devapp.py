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
from datetime import date, datetime
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
        # --- CONFIGURAÇÃO DE ESTILO MODERNO (Ttk.Style) ---
        estilo = ttk.Style(self)
        
        # Tenta usar o tema 'clam' como base, pois aceita customização de cores perfeitamente no Linux/Windows
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")

        # Paleta de Cores Moderna (Tons de Cinza Slate + Azul Corporativo)
        COR_BG_GERAL = "#f8fafc"      # Fundo claro limpo
        COR_PRIMARIA = "#2563eb"      # Azul moderno
        COR_HOVER = "#1d4ed8"         # Azul mais escuro para hover
        COR_TEXTO = "#1e293b"         # Texto escuro legível
        COR_TEXTO_CLARO = "#64748b"   # Texto secundário

        # Configurações globais de fontes e cores
        self.configure(bg=COR_BG_GERAL)
        
        estilo.configure(".", 
                         background=COR_BG_GERAL, 
                         foreground=COR_TEXTO, 
                         font=("Helvetica", 10))

        # Estilo para os Notebooks (Abas)
        estilo.configure("TNotebook", background=COR_BG_GERAL, borderwidth=0)
        estilo.configure("TNotebook.Tab", 
                         padding=(12, 8), 
                         font=("Helvetica", 10, "bold"),
                         background="#e2e8f0", 
                         foreground="#475569")
        estilo.map("TNotebook.Tab", 
                   background=[("selected", COR_PRIMARIA)], 
                   foreground=[("selected", "#ffffff")])

        # Estilo para Botões Padrão TTK
        estilo.configure("TButton", 
                         padding=(10, 6), 
                         font=("Helvetica", 9, "bold"), 
                         relief="flat", 
                         background="#e2e8f0", 
                         foreground=COR_TEXTO)
        
        # Estilo para Tabelas (Treeview) mais limpas e espaçadas
        estilo.configure("Treeview", 
                         background="#ffffff", 
                         foreground=COR_TEXTO, 
                         rowheight=26, 
                         fieldbackground="#ffffff",
                         font=("Helvetica", 9))
        
        estilo.configure("Treeview.Heading", 
                         font=("Helvetica", 9, "bold"), 
                         background="#e2e8f0", 
                         foreground=COR_TEXTO,
                         relief="flat")
        
        estilo.map("Treeview", 
                   background=[('selected', COR_PRIMARIA)], 
                   foreground=[('selected', '#ffffff')])

        self.title("Pétalas Negras - gerenciador do site")
        self.geometry("1000x740")
        self.minsize(860, 580)
        
        try:
            self.state("fullscreen")
        except tk.TclError:
            try:
                self.attributes("-fullscreen", True)
            except tk.TclError:
                pass
                
        self.site = None
        self.servidor = None
        self.caminho_cal = None
        self.dados_cal = {}
        self.var_pasta = tk.StringVar()
        self.var_auto = tk.BooleanVar(value=True)
        self.var_ranking = tk.StringVar(value=RANKINGS[0][0])

        self._montar_topo()
        self._montar_abas()
        self.after(200, self._atualizar_cards_dashboard)
        self._montar_rodape()
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        pasta = self._config().get("pasta", "")
        if pasta and Path(pasta).is_dir():
            # Abre a pasta e joga o carregamento pesado para um micro-atraso (0.1s)
            self.site = sp.Site(pasta)
            self.var_pasta.set(str(self.site.raiz))
            self.log(f"Site aberto: {self.site.raiz}")
            self.after(100, self.recarregar_listas)
            ultimo = self._config().get("calendario", "")
            if ultimo and Path(ultimo).is_file():
                self.after(150, lambda: self._carregar_calendario(ultimo))
        else:
            self.after(200, self.escolher_pasta)

    # ------------------------------------------------------------ montagem

    def _montar_topo(self):
        # Barra de ferramentas superior (Toolbar)
        topo = ttk.Frame(self, padding=(10, 8))
        topo.pack(fill="x", side="top")
        
        # 1. Seleção da pasta do site
        ttk.Label(topo, text="Pasta do site:").pack(side="left", padx=(0, 4))
        ttk.Entry(topo, textvariable=self.var_pasta, state="readonly", width=35).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(topo, text="Escolher...", command=self.escolher_pasta).pack(side="left", padx=(0, 6))
        
        # 2. Ações do sistema
        ttk.Button(topo, text="🔄 Recarregar", command=self.recarregar).pack(side="left", padx=(0, 4))
        ttk.Button(topo, text="🌐 Ver no Navegador", command=self.abrir_navegador).pack(side="left", padx=(0, 4))
        ttk.Button(topo, text="📦 Gerar Zip", command=self.fazer_backup).pack(side="left", padx=(0, 4))

        # Divisor visual antes do botão de fechar
        ttk.Separator(topo, orient="vertical").pack(side="left", fill="y", padx=8)
        
        # Botão para fechar o aplicativo com destaque
        btn_fechar = tk.Button(topo, text="✕ Fechar App", command=self._fechar, 
                               bg="#ef4444", fg="#ffffff", activebackground="#dc2626", activeforeground="#ffffff",
                               relief="flat", padx=10, pady=3, font=("Helvetica", 9, "bold"))
        btn_fechar.pack(side="left")

    def _montar_abas(self):
        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=10)
        self._aba_dashboard()
        self._aba_elenco()
        self._aba_jogos()
        self._aba_treinos()
        self._aba_calendario()
        self._aba_ranking()
        self._aba_financas()
        self._aba_mensalidades()

    def _aba_elenco(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Elenco  ")

        # Utilizando a função padrão de busca
        self.var_busca_elenco = self._criar_barra_busca(aba, self._preencher_elenco)

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

        # Utilizando a função padrão de busca
        self.var_busca_jogos = self._criar_barra_busca(aba, self._preencher_jogos)

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
    
    def _aba_treinos(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Treinos & Presença  ")

        # Divisão em duas partes: Esquerda (Lista de Treinos), Direita (Ranking de Presença)
        painel_principal = ttk.PanedWindow(aba, orient="horizontal")
        painel_principal.pack(fill="both", expand=True)

        # --- Lado Esquerdo: Treinos Cadastrados ---
        frame_esq = ttk.Frame(painel_principal, padding=4)
        painel_principal.add(frame_esq, weight=3)

        self.var_busca_treinos = self._criar_barra_busca(frame_esq, self._preencher_treinos)

        quadro_t, self.tv_treinos = _tabela(frame_esq, [
            ("data", "Data", 85, "center"), 
            ("hora", "Hora", 60, "center"), 
            ("descricao", "Descrição do Treino", 250, "w"),
            ("presentes", "Presenças", 70, "center")
        ], altura=16)
        quadro_t.pack(fill="both", expand=True)
        self.tv_treinos.bind("<Double-1>", lambda _e: self.gerenciar_presenca_treino())

        barra_t = ttk.Frame(frame_esq)
        barra_t.pack(fill="x", pady=(8, 0))
        ttk.Button(barra_t, text="Novo Treino...", command=self.adicionar_treino).pack(side="left", padx=(0, 6))
        ttk.Button(barra_t, text="Editar Treino...", command=self.editar_treino).pack(side="left", padx=(0, 6)) # <--- Novo botão
        ttk.Button(barra_t, text="Lista de Chamada...", command=self.gerenciar_presenca_treino).pack(side="left", padx=(0, 6))
        ttk.Button(barra_t, text="Remover Treino", command=self.remover_treino).pack(side="left")


        # --- Lado Direito: Resumo de Frequência dos Atletas (Com Barra de Busca Própria) ---
        frame_dir = ttk.Frame(painel_principal, padding=4)
        painel_principal.add(frame_dir, weight=2)

        ttk.Label(frame_dir, text="Frequência Geral dos Atletas", font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 2))
        
        # Filtro específico para o ranking de presença
        self.var_busca_frequencia = self._criar_barra_busca(frame_dir, self._preencher_treinos)

        quadro_p, self.tv_presenca_resumo = _tabela(frame_dir, [
            ("nome", "Atleta", 160, "w"),
            ("freq", "% Presença", 90, "center"),
            ("detalhes", "Pres / Just", 90, "center")
        ], altura=14)
        quadro_p.pack(fill="both", expand=True)

        # Carrega automaticamente ao montar a aba
        self.after(100, self._preencher_treinos)

    def editar_treino(self):
        sel = self.tv_treinos.selection()
        if not sel:
            messagebox.showinfo("Seleção", "Selecione um treino na lista para editar.", parent=self)
            return
        
        t_id = sel[0]
        treinos = self.site.carregar_treinos()
        treino = treinos.get(t_id, {})

        def salvar(v):
            if not v["descricao"]:
                messagebox.showwarning("Aviso", "Informe a descrição do treino.", parent=self)
                return False
            # Mantém as presenças já salvas, atualizando apenas os dados gerais
            self.site.adicionar_ou_editar_treino(t_id, v["data"], v["hora"], v["descricao"], treino.get("presencas", {}))
            self.log(f"Treino atualizado: {v['descricao']}")
            self._preencher_treinos()
            return True

        Dialogo(self, "Editar Treino", [
            ("data", "Data (DD/MM/AAAA)", "entry"),
            ("hora", "Horário (ex.: 20:00)", "entry"),
            ("descricao", "Descrição do Treino", "entry")
        ], {
            "data": treino.get("data", ""),
            "hora": treino.get("hora", ""),
            "descricao": treino.get("descricao", "")
        }, salvar)

    def _preencher_treinos(self):
        if not hasattr(self, "tv_treinos") or self.site is None:
            return

        self.tv_treinos.delete(*self.tv_treinos.get_children())
        self.tv_presenca_resumo.delete(*self.tv_presenca_resumo.get_children())

        filtro_treinos = sp.sem_acento(self.var_busca_treinos.get().strip()) if hasattr(self, "var_busca_treinos") else ""
        filtro_freq = sp.sem_acento(self.var_busca_frequencia.get().strip()) if hasattr(self, "var_busca_frequencia") else ""
        
        treinos = self.site.carregar_treinos()

        # 1. Preenche tabela de treinos com filtro aplicado
        for t_id, t in sorted(treinos.items(), key=lambda x: x[1].get("data", ""), reverse=True):
            texto_linha = f"{t.get('data')} {t.get('hora')} {t.get('descricao')}"
            if filtro_treinos and filtro_treinos not in sp.sem_acento(texto_linha):
                continue
            
            presencas = t.get("presencas", {})
            total_p = sum(1 for p in presencas.values() if p.get("status") == "presente")

            self.tv_treinos.insert("", "end", iid=t_id, values=(
                t.get("data"), t.get("hora"), t.get("descricao"), f"{total_p} atletas"
            ))

        # 2. Preenche resumo de frequência com filtro de nome aplicado
        freqs = self.site.calcular_porcentagem_presenca()
        for slug, info in sorted(freqs.items(), key=lambda x: x[1]["porcentagem"], reverse=True):
            if filtro_freq and filtro_freq not in sp.sem_acento(info["nome"]):
                continue

            p_val = info["porcentagem"]
            icone_p = "🟢" if p_val >= 75 else ("🟡" if p_val >= 50 else "🔴")
            
            self.tv_presenca_resumo.insert("", "end", iid=slug, values=(
                info["nome"],
                f"{icone_p} {p_val:.1f}%",
                f"{info['presentes']} / {info['justificadas']} just."
            ))
        
        self._aplicar_efeito_zebra(self.tv_treinos)
        self._aplicar_efeito_zebra(self.tv_presenca_resumo)
    
    def adicionar_treino(self):
        if self.site is None:
            return self.escolher_pasta()

        def salvar(v):
            if not v["descricao"]:
                messagebox.showwarning("Aviso", "Informe a descrição do treino.", parent=self)
                return False
            # Cria o treino com lista vazia inicialmente
            self.site.adicionar_ou_editar_treino("", v["data"], v["hora"], v["descricao"], {})
            self.log(f"Treino criado: {v['descricao']} em {v['data']}")
            self._preencher_treinos()
            return True

        Dialogo(self, "Novo Treino", [
            ("data", "Data (DD/MM/AAAA)", "entry"),
            ("hora", "Horário (ex.: 20:00)", "entry"),
            ("descricao", "O que vai ter no treino (ex: Tático/Finalização)", "entry")
        ], {"data": date.today().strftime("%d/%m/%Y"), "hora": "20:00"}, salvar)

    def gerenciar_presenca_treino(self):
        sel = self.tv_treinos.selection()
        if not sel:
            messagebox.showinfo("Seleção", "Selecione um treino na lista para gerenciar a chamada.", parent=self)
            return
        
        t_id = sel[0]
        treinos = self.site.carregar_treinos()
        treino = treinos.get(t_id, {})
        
        # Abre a janela personalizada de Chamada / Presença
        janela_chamada = tk.Toplevel(self)
        janela_chamada.title(f"Chamada - {treino.get('descricao')} ({treino.get('data')})")
        janela_chamada.geometry("600x500")
        janela_chamada.transient(self)

        # ADICIONE ESTAS DUAS LINHAS PARA GARANTIR QUE A JANELA ESTÁ VISÍVEL ANTES DO GRAB:
        janela_chamada.update_idletasks()
        janela_chamada.deiconify()

        janela_chamada.grab_set()

        ttk.Label(janela_chamada, text=f"Treino: {treino.get('descricao')} | Data: {treino.get('data')}", font=("Helvetica", 11, "bold")).pack(pady=10)
        ttk.Label(janela_chamada, text="Marque a presença ou clique duas vezes para justificar falta informando o motivo.", foreground="#555").pack(pady=(0, 10))

        # Tabela de atletas dentro da janela de chamada
        quadro, tv_chamada = _tabela(janela_chamada, [
            ("nome", "Atleta", 180, "w"),
            ("status", "Status", 120, "center"),
            ("motivo", "Motivo da Justificativa", 220, "w")
        ], altura=14)
        quadro.pack(fill="both", expand=True, padx=10)

        atletas = [a for a in self.site.listar_elenco() if a["grupo"] != sp.GRUPO_STAFF]
        presencas_atuais = treino.get("presencas", {})

        for a in atletas:
            slug = a["slug"]
            p_info = presencas_atuais.get(slug, {"status": "ausente", "motivo": ""}) # Padrão: presente
            status_txt = "✅ Presente" if p_info["status"] == "presente" else ("❌ Ausente" if p_info["status"] == "ausente" else "⚠️ Justificado")
            
            tv_chamada.insert("", "end", iid=slug, values=(
                a["nome"], status_txt, p_info.get("motivo", "")
            ))

        # Funções para alterar status direto na janela
        def alterar_status(novo_status):
            selecionado = tv_chamada.selection()
            if not selecionado:
                messagebox.showwarning("Aviso", "Selecione um atleta na tabela.", parent=janela_chamada)
                return
            slug = selecionado[0]
            motivo = ""
            if novo_status == "justificado":
                motivo = simpledialog.askstring("Justificativa", "Informe o motivo da falta justificada:", parent=janela_chamada)
                if motivo is None: return
            
            # Atualiza no dicionário local do treino
            presencas_atuais[slug] = {"status": novo_status, "motivo": motivo or ""}
            status_txt = "✅ Presente" if novo_status == "presente" else ("❌ Ausente" if novo_status == "ausente" else "⚠️ Justificado")
            tv_chamada.item(slug, values=(tv_chamada.item(slug, "values")[0], status_txt, motivo or ""))

        barra_botoes = ttk.Frame(janela_chamada, padding=10)
        barra_botoes.pack(fill="x")
        
        ttk.Button(barra_botoes, text="Marcar Presente ✅", command=lambda: alterar_status("presente")).pack(side="left", padx=4)
        ttk.Button(barra_botoes, text="Marcar Ausente ❌", command=lambda: alterar_status("ausente")).pack(side="left", padx=4)
        ttk.Button(barra_batoroes := barra_botoes, text="Justificar Falta ⚠️", command=lambda: alterar_status("justificado")).pack(side="left", padx=4)

        def salvar_e_fechar():
            self.site.adicionar_ou_editar_treino(t_id, treino.get("data"), treino.get("hora"), treino.get("descricao"), presencas_atuais)
            self.log(f"Chamada salva para o treino: {treino.get('descricao')}")
            self._preencher_treinos()
            janela_chamada.destroy()

        ttk.Button(barra_botoes, text="Salvar Chamada", command=salvar_e_fechar).pack(side="right", padx=4)

    def remover_treino(self):
        sel = self.tv_treinos.selection()
        if not sel:
            messagebox.showinfo("Seleção", "Selecione um treino para remover.", parent=self)
            return
        t_id = sel[0]
        if not messagebox.askyesno("Confirmação", "Deseja realmente remover este treino e suas chamadas?", parent=self):
            return
        self.site.remover_treino(t_id)
        self.log("Treino removido.")
        self._preencher_treinos()
            
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

    def _aba_financas(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Finanças  ")

        # Formulário organizado com campos separados
        form_frame = ttk.LabelFrame(aba, text=" Registrar Movimentação ", padding=10)
        form_frame.pack(fill="x", pady=(0, 10))

        # Linha 1 do formulário
        ttk.Label(form_frame, text="Tipo:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.var_tipo_fin = tk.StringVar(value="Recebido")
        cb_tipo = ttk.Combobox(form_frame, values=["Recebido", "Gasto"], textvariable=self.var_tipo_fin, width=12, state="readonly")
        cb_tipo.grid(row=0, column=1, sticky="w", padx=5, pady=3)

        ttk.Label(form_frame, text="Data (DD/MM/AAAA):").grid(row=0, column=2, sticky="w", padx=5, pady=3)
        self.entry_data_fin = ttk.Entry(form_frame, width=12)
        self.entry_data_fin.grid(row=0, column=3, sticky="w", padx=5, pady=3)
        self.entry_data_fin.insert(0, date.today().strftime("%d/%m/%Y")) # Preenche com a data de hoje por padrão

        ttk.Label(form_frame, text="Valor (R$):").grid(row=0, column=4, sticky="w", padx=5, pady=3)
        self.entry_valor = ttk.Entry(form_frame, width=12)
        self.entry_valor.grid(row=0, column=5, sticky="w", padx=5, pady=3)

        # Linha 2 do formulário
        ttk.Label(form_frame, text="Quem (Elenco/Fora):").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.entry_nome_fin = ttk.Entry(form_frame, width=22)
        self.entry_nome_fin.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Label(form_frame, text="Descrição:").grid(row=1, column=3, sticky="w", padx=5, pady=3)
        self.entry_desc_fin = ttk.Entry(form_frame, width=35)
        self.entry_desc_fin.grid(row=1, column=4, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Button(form_frame, text="Salvar Transação", command=self.salvar_transacao).grid(row=1, column=6, padx=10, pady=3)

        # Histórico formatado em texto (tipo log)
        log_frame = ttk.LabelFrame(aba, text=" Histórico Salvo de Caixa ", padding=10)
        log_frame.pack(fill="both", expand=True)

        self.txt_historico_fin = ScrolledText(log_frame, state="disabled", wrap="word", height=15)
        self.txt_historico_fin.pack(fill="both", expand=True)
        
        self.atualizar_historico_financas()

    def salvar_transacao(self):
        if self.site is None:
            return self.escolher_pasta()
        
        tipo = self.var_tipo_fin.get()
        data_txt = self.entry_data_fin.get().strip()
        nome = self.entry_nome_fin.get().strip()
        descricao = self.entry_desc_fin.get().strip()
        valor_str = self.entry_valor.get().strip().replace(",", ".")

        if not nome:
            messagebox.showwarning("Aviso", "Informe quem enviou ou o responsável pelo gasto.", parent=self)
            return
        
        try:
            valor = float(valor_str)
        except ValueError:
            messagebox.showwarning("Aviso", "Valor inválido. Use números (ex: 50.00).", parent=self)
            return

        tipo_cod = "recebita" if tipo == "Recebido" else "gasto"
        
        # Salva no arquivo CSV
        self.site.adicionar_transacao(tipo_cod, nome, descricao, valor, data_txt)
        
        # Limpa os campos de digitação (mantém a data atual opcionalmente)
        self.entry_nome_fin.delete(0, "end")
        self.entry_desc_fin.delete(0, "end")
        self.entry_valor.delete(0, "end")

        # Atualiza a tela e o log geral
        self.atualizar_historico_financas()
        self.log(f"Financeiro salvo: [{tipo.upper()}] {nome} - R$ {valor:.2f}")

    def atualizar_historico_financas(self):
        if self.site is None:
            return
        
        transacoes = self.site.listar_financas()
        
        self.txt_historico_fin.configure(state="normal")
        self.txt_historico_fin.delete("1.0", "end")

        if not transacoes:
            self.txt_historico_fin.insert("end", "Nenhum histórico financeiro encontrado. (Arquivo vazio)\n")
        else:
            # Cabeçalho formatado para acomodar os novos campos
            header = f"{'DATA':<12} | {'TIPO':<10} | {'QUEM':<20} | {'DESCRIÇÃO':<25} | {'VALOR':<10}\n"
            self.txt_historico_fin.insert("end", header)
            self.txt_historico_fin.insert("end", "-" * 85 + "\n")
            
            total_caixa = 0.0
            for t in transacoes:
                tipo_txt = "ENTRADA" if t.get("tipo") == "recebita" else "SAÍDA"
                val = float(t.get("valor", 0))
                if t.get("tipo") == "recebita":
                    total_caixa += val
                else:
                    total_caixa -= val

                data = t.get('data', '')
                nome = t.get('nome', '')
                desc = t.get('descricao', '')

                linha = f"{data:<12} | {tipo_txt:<10} | {nome:<20} | {desc:<25} | R$ {val:>7.2f}\n"
                self.txt_historico_fin.insert("end", linha)
            
            self.txt_historico_fin.insert("end", "-" * 85 + "\n")
            self.txt_historico_fin.insert("end", f"SALDO ATUAL EM CAIXA: R$ {total_caixa:.2f}\n")

        self.txt_historico_fin.configure(state="disabled")

    def fazer_backup(self):
        if self.site is None:
            return self.escolher_pasta()
        
        # Chama a função de backup direto da biblioteca site_petalas (self.site)
        ok, caminho = self._executar("Gerando backup em .zip...", self.site.gerar_backup)
        if ok and caminho:
            self.log(f"Backup gerado com sucesso: {Path(caminho).name}")
            messagebox.showinfo("Backup Concluído", f"Backup criado com sucesso em:\n{caminho}", parent=self)

    def _aba_mensalidades(self):
        aba = ttk.Frame(self.abas, padding=8)
        self.abas.add(aba, text="  Mensalidades  ")

        # Topo: Configuração do valor da mensalidade e ações em lote
        topo_frame = ttk.Frame(aba)
        topo_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(topo_frame, text="Valor da Mensalidade (R$):").pack(side="left", padx=(0, 4))
        self.entry_val_mensalidade = ttk.Entry(topo_frame, width=8)
        self.entry_val_mensalidade.pack(side="left", padx=(0, 8))
        
        ttk.Button(topo_frame, text="Atualizar Valor", command=self.salvar_valor_mensalidade_config).pack(side="left", padx=(0, 20))
        ttk.Button(topo_frame, text="Marcar como Pago", command=lambda: self.mudar_status_selecionado("pago")).pack(side="left", padx=(0, 6))
        ttk.Button(topo_frame, text="Marcar como Pendente", command=lambda: self.mudar_status_selecionado("pendente")).pack(side="left", padx=(0, 6))
        ttk.Button(topo_frame, text="Atualizar mês", command=self.marcar_todos_pendente).pack(side="left", padx=(0, 6)) # <--- ADICIONE ESTA LINHA

        # UTILIZANDO A FUNÇÃO PADRÃO DE BUSCA AQUI:
        self.var_busca_mensalidades = self._criar_barra_busca(aba, self._preencher_mensalidades)

        # Tabela de mensalidades
        quadro, self.tv_mensalidades = _tabela(aba, [
            ("numero", "Nº", 50, "center"), 
            ("nome", "Nome", 250, "w"), 
            ("posicao", "Posição", 200, "w"),
            ("status", "Status da Mensalidade", 150, "center")
        ], altura=16)
        quadro.pack(fill="both", expand=True)
        
        self.tv_mensalidades.bind("<Double-1>", lambda _e: self.alternar_status_duplo_clique())

        if self.site:
            self.entry_val_mensalidade.insert(0, f"{self.site.obter_valor_mensalidade():.2f}")
            self._preencher_mensalidades()

    def _preencher_mensalidades(self):
        self.tv_mensalidades.delete(*self.tv_mensalidades.get_children())
        if self.site is None:
            return
        
        # Pega o texto digitado na barra de busca de mensalidades
        filtro = sp.sem_acento(self.var_busca_mensalidades.get().strip()) if hasattr(self, "var_busca_mensalidades") else ""
        
        try:
            atletas = [a for a in self.site.listar_elenco() if a["grupo"] != sp.GRUPO_STAFF]
            status_dict = self.site.carregar_status_mensalidades()

            for a in atletas:
                slug_a = a["slug"]
                estado = status_dict.get(slug_a, "pendente")
                status_txt = "✅ PAGO" if estado == "pago" else "❌ PENDENTE"
                
                # Aplica o filtro de texto (nome, posição, número ou status)
                texto_linha = f"{a['numero']} {a['nome']} {a['posicao']} {status_txt}"
                if filtro and filtro not in sp.sem_acento(texto_linha):
                    continue

                self.tv_mensalidades.insert("", "end", iid=slug_a, values=(
                    "" if a["numero"] is None else a["numero"], 
                    a["nome"], 
                    a["posicao"], 
                    status_txt
                ))
        except Exception as e:
            self.log(f"Erro ao carregar mensalidades: {e}", "erro")
        
        self._aplicar_efeito_zebra(self.tv_mensalidades)

    def salvar_valor_mensalidade_config(self):
        if self.site is None:
            return
        try:
            val = float(self.entry_val_mensalidade.get().strip().replace(",", "."))
            self.site.definir_valor_mensalidade(val)
            self.log(f"Valor padrão da mensalidade alterado para: R$ {val:.2f}")
            messagebox.showinfo("Sucesso", f"Valor da mensalidade atualizado para R$ {val:.2f}", parent=self)
        except ValueError:
            messagebox.showwarning("Aviso", "Insira um valor numérico válido.", parent=self)

    def mudar_status_selecionado(self, novo_estado: str):
        if self.site is None:
            return
        sel = self.tv_mensalidades.selection()
        if not sel:
            messagebox.showinfo("Seleção", "Selecione um atleta na lista.", parent=self)
            return
        
        slug_atleta = sel[0]
        # Descobre o nome do atleta pelo slug na lista do elenco
        atletas = self.site.listar_elenco()
        atleta_obj = next((a for a in atletas if a["slug"] == slug_atleta), None)
        if not atleta_obj:
            return

        pago = (novo_estado == "pago")
        self.site.atualizar_status_mensalidade(slug_atleta, pago, atleta_obj["nome"])
        
        self._preencher_mensalidades()
        # Atualiza também a aba de finanças caso esteja aberta
        if hasattr(self, "txt_historico_fin"):
            self.atualizar_historico_financas()
        
        self.log(f"Mensalidade de {atleta_obj['nome']} alterada para: {novo_estado.upper()}")

    def alternar_status_duplo_clique(self):
        if self.site is None:
            return
        sel = self.tv_mensalidades.selection()
        if not sel:
            return
        slug_atleta = sel[0]
        status_dict = self.site.carregar_status_mensalidades()
        estado_atual = status_dict.get(slug_atleta, "pendente")
        
        # Inverte o estado atual
        novo_estado = "pendente" if estado_atual == "pago" else "pago"
        self.mudar_status_selecionado(novo_estado)

    def marcar_todos_pendente(self):
        if self.site is None:
            return
        if not messagebox.askyesno("Confirmação", "Deseja realmente marcar a mensalidade de TODOS os atletas como PENDENTE?", parent=self):
            return
        
        status_dict = {}
        atletas = [a for a in self.site.listar_elenco() if a["grupo"] != sp.GRUPO_STAFF]
        for a in atletas:
            status_dict[a["slug"]] = "pendente"
        
        self.site.salvar_status_mensalidades(status_dict)
        self._preencher_mensalidades()
        self.log("Todas as mensalidades foram redefinidas para PENDENTE.")

    def _criar_card_dashboard(self, parent, titulo, valor_inicial, cor_borda="#2563eb"):
        """Cria um card visual moderno com borda colorida e destaque para o valor."""
        card = tk.Frame(parent, bg="#ffffff", bd=0, relief="flat", highlightbackground="#e2e8f0", highlightthickness=1)
        
        # Detalhe lateral colorido para dar um toque moderno
        barra = tk.Frame(card, bg=cor_borda, width=4)
        barra.pack(side="left", fill="y")
        
        conteudo = tk.Frame(card, bg="#ffffff", padx=12, pady=10)
        conteudo.pack(side="left", fill="both", expand=True)
        
        lbl_titulo = tk.Label(conteudo, text=titulo.upper(), font=("Helvetica", 8, "bold"), fg="#64748b", bg="#ffffff")
        lbl_titulo.pack(anchor="w")
        
        lbl_valor = tk.Label(conteudo, text=str(valor_inicial), font=("Helvetica", 16, "bold"), fg="#1e293b", bg="#ffffff")
        lbl_valor.pack(anchor="w", pady=(2, 0))
        
        # Guarda referência do label de valor para poder atualizar depois
        card.lbl_valor = lbl_valor
        return card

    def _aba_dashboard(self):
        aba = ttk.Frame(self.abas, padding=12)
        self.abas.add(aba, text="  Dashboard  ")

        # Container superior para os Cards de Resumo (lado a lado)
        frame_cards = tk.Frame(aba, bg="#f8fafc")
        frame_cards.pack(fill="x", pady=(0, 10))

        # Cria os 4 cards principais
        self.card_atletas = self._criar_card_dashboard(frame_cards, "Atletas Ativos", "0", "#2563eb")
        self.card_atletas.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.card_caixa = self._criar_card_dashboard(frame_cards, "Caixa (Saldo)", "R$ 0,00", "#16a34a")
        self.card_caixa.pack(side="left", fill="both", expand=True, padx=8)

        self.card_treinos = self._criar_card_dashboard(frame_cards, "Média Presença", "0%", "#d97706")
        self.card_treinos.pack(side="left", fill="both", expand=True, padx=8)

        self.card_prox_jogo = self._criar_card_dashboard(frame_cards, "Próximo Jogo", "Nenhum", "#9333ea")
        self.card_prox_jogo.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # Moldura compacta para a foto (sem expand=True para não empurrar para baixo)
        frame_baixo = ttk.LabelFrame(aba, text=" 📸 Foto Oficial da Equipe ", padding=8)
        frame_baixo.pack(fill="x", pady=(0, 0))

        # Label que conterá a imagem de forma compacta
        self.lbl_foto_time = ttk.Label(frame_baixo, anchor="center")
        self.lbl_foto_time.pack(fill="x", padx=5, pady=2)

        # Tenta carregar a foto do time ao iniciar
        self.after(150, self._carregar_foto_dashboard)

        # Garante a atualização automática ao trocar para esta aba
        self.abas.bind("<<NotebookTabChanged>>", self._ao_trocar_aba)

        # Carrega na inicialização
        self.after(100, self._atualizar_cards_dashboard)

    def _carregar_foto_dashboard(self):
        """Carrega, redimensiona e exibe a foto do time no dashboard."""
        if self.site is None:
            return
            
        try:
            caminho_foto = self.site.raiz / "imagens" / "elenco.png"
            if not caminho_foto.exists():
                caminho_foto = self.site.raiz / "imagens" / "elenco.jpg"
            if not caminho_foto.exists():
                caminho_foto = self.site.raiz / "imagens" / "time.png"
            if not caminho_foto.exists():
                caminho_foto = self.site.raiz / "imagens" / "time.jpeg"
                
            if caminho_foto.exists():
                img_original = tk.PhotoImage(file=str(caminho_foto))
                
                # Reduz a imagem proporcionalmente (ajuste o valor se precisar menor/maior, ex: subsample(3,3))
                self.img_time = img_original.subsample(2, 2)
                
                self.lbl_foto_time.config(image=self.img_time, text="")
            else:
                self.lbl_foto_time.config(
                    text="Nenhuma foto encontrada na pasta 'imagens/' (ex: elenco.png ou time.png).",
                    font=("Helvetica", 9)
                )
        except Exception as e:
            self.lbl_foto_time.config(text=f"Não foi possível carregar a imagem: {e}")

    def _ao_trocar_aba(self, event):
        """Atualiza o dashboard automaticamente sempre que o usuário clica na aba."""
        try:
            aba_atual = self.abas.tab(self.abas.select(), "text").strip()
            if "Dashboard" in aba_atual:
                self._atualizar_cards_dashboard()
        except Exception:
            pass

    def _atualizar_cards_dashboard(self):
        if self.site is None:
            return
            
        try:
            # 1. Atletas Ativos
            atletas = [a for a in self.site.listar_elenco() if a.get("grupo") != sp.GRUPO_STAFF]
            if hasattr(self, "card_atletas") and self.card_atletas:
                self.card_atletas.lbl_valor.config(text=str(len(atletas)))

            # 2. Saldo em Caixa (Lendo direto do arquivo de finanças/transações)
            saldo = 0.0
            try:
                transacoes = self.site.listar_financas()
                for t in transacoes:
                    val = float(t.get("valor", 0))
                    if t.get("tipo") == "recebita":
                        saldo += val
                    else:
                        saldo -= val
            except Exception:
                pass
            
            saldo_fmt = f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if hasattr(self, "card_caixa") and self.card_caixa:
                self.card_caixa.lbl_valor.config(text=saldo_fmt)

            # 3. Média de Presença
            media_geral = 0.0
            try:
                freqs = self.site.calcular_porcentagem_presenca()
                if freqs:
                    media_geral = sum(info["porcentagem"] for info in freqs.values()) / len(freqs)
            except Exception:
                pass

            if hasattr(self, "card_treinos") and self.card_treinos:
                self.card_treinos.lbl_valor.config(text=f"{media_geral:.1f}%")

            # 4. Próximo Jogo
            proximo_adversario = "Nenhum"
            try:
                jogos_dict = self.site.listar_jogos()
                if jogos_dict:
                    hoje = date.today()
                    proximos = [j for j in jogos_dict if datetime.strptime(j["data_br"], "%d/%m/%Y").date() >= hoje]
                    proximos.sort(key=lambda j: datetime.strptime(j["data_br"], "%d/%m/%Y").date())
                    if proximos:
                        p = proximos[0]
                        proximo_adversario = f"{p['adversario']} ({p['data_br']})"
            except Exception:
                pass

            if hasattr(self, "card_prox_jogo") and self.card_prox_jogo:
                self.card_prox_jogo.lbl_valor.config(text=proximo_adversario)

            # 5. Artilheiros e Assistências
            artilheiros_lista, assistentes_lista = [], []
            for a in atletas:
                nome = a.get("nome", "Atleta")
                gols = int(a.get("gols", 0))
                assts = int(a.get("assistencias", 0))
                if gols > 0:
                    artilheiros_lista.append((nome, gols))
                if assts > 0:
                    assistentes_lista.append((nome, assts))

            melhor_artilheiro = "Nenhum gol registrado"
            melhor_assistente = "Nenhuma assistência registrada"
            if artilheiros_lista:
                artilheiros_lista.sort(key=lambda x: x[1], reverse=True)
                melhor_artilheiro = f"⚽ {artilheiros_lista[0][0]} — {artilheiros_lista[0][1]} gols"
            if assistentes_lista:
                assistentes_lista.sort(key=lambda x: x[1], reverse=True)
                melhor_assistente = f"👟 {assistentes_lista[0][0]} — {assistentes_lista[0][1]} assistências"

            if hasattr(self, "lbl_artilheiro"):
                self.lbl_artilheiro.config(text=melhor_artilheiro)
            if hasattr(self, "lbl_assistencias"):
                self.lbl_assistencias.config(text=melhor_assistente)

            total_treinos = len(self.site.carregar_treinos()) if hasattr(self.site, "carregar_treinos") else 0
            texto_ind = (
                f"• Atletas Ativos: {len(atletas)}\n"
                f"• Treinos Registrados: {total_treinos}\n"
                f"• Jogos Cadastrados: {len(self.site.listar_jogos())}\n"
                f"• Caixa Líquido: {saldo_fmt}"
            )
            if hasattr(self, "lbl_indicadores"):
                self.lbl_indicadores.config(text=texto_ind)

        except Exception as e:
            print(f"Erro detalhado no dashboard: {e}")

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
        
        # ---> ADICIONE ESTA LINHA ABAIXO <---
        self._atualizar_cards_dashboard()

    def recarregar(self):
        if self.site is not None:
            self.abrir_site(str(self.site.raiz))
        
        self._atualizar_cards_dashboard()
        self._carregar_foto_dashboard()
        self._preencher_treinos()

    def recarregar_listas(self):
        self._preencher_elenco()
        self._preencher_jogos()
        self._preencher_ranking()
        if hasattr(self, "txt_historico_fin"):
            self.atualizar_historico_financas()
        if hasattr(self, "tv_mensalidades"):
            self._preencher_mensalidades()
            if self.site:
                self.entry_val_mensalidade.delete(0, "end")
                self.entry_val_mensalidade.insert(0, f"{self.site.obter_valor_mensalidade():.2f}")

        if hasattr(self, "atualizar_cards_dashboard"):
            self._atualizar_cards_dashboard()

    def _preencher_elenco(self):
        self.tv_elenco.delete(*self.tv_elenco.get_children())
        if self.site is None:
            return
        filtro = sp.sem_acento(self.var_busca_elenco.get().strip())
        try:
            for a in self.site.listar_elenco():
                # Aplica o filtro de texto (nome, posição ou número)
                texto_linha = f"{a['numero']} {a['nome']} {a['posicao']}"
                if filtro and filtro not in sp.sem_acento(texto_linha):
                    continue
                
                staff = a["grupo"] == sp.GRUPO_STAFF
                self.tv_elenco.insert("", "end", iid=a["nome"], values=(
                    "" if a["numero"] is None else a["numero"], a["nome"], a["posicao"],
                    "" if staff else a["jogos"], "" if staff else a["gols"],
                    "" if staff else a["assistencias"]))
        except sp.ErroDados as e:
            self.log(f"Erro ao ler o elenco: {e}", "erro")
        
        self._aplicar_efeito_zebra(self.tv_elenco)

    def _preencher_jogos(self):
        self.tv_jogos.delete(*self.tv_jogos.get_children())
        if self.site is None:
            return
        filtro = sp.sem_acento(self.var_busca_jogos.get().strip())
        rotulos = {"vitoria": "Vitória", "derrota": "Derrota", "empate": "Empate", "": ""}
        try:
            for j in self.site.listar_jogos():
                # Aplica o filtro de texto (adversário, data, local ou resultado)
                texto_linha = f"{j['data_br']} {j['adversario']} {j['local']} {j['placar']}"
                if filtro and filtro not in sp.sem_acento(texto_linha):
                    continue

                self.tv_jogos.insert("", "end", iid=j["id"], values=(
                    j["data_br"], j["hora"], j["adversario"], j["local"], j["placar"],
                    rotulos.get(j["resultado"], "")))
        except sp.ErroDados as e:
            self.log(f"Erro ao ler os jogos: {e}", "erro")
        
        self._aplicar_efeito_zebra(self.tv_jogos)

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

        self._aplicar_efeito_zebra(self.tv_ranking)

    def _selecionado(self, tv, o_que):
        sel = tv.selection()
        if not sel:
            messagebox.showinfo("Seleção", f"Selecione {o_que} na lista.", parent=self)
            return None
        return sel[0]

    def _criar_barra_busca(self, aba, comando_atualizar, largura=30):
        """Cria um painel padrão de busca/filtro no topo de uma aba."""
        topo_busca = ttk.Frame(aba)
        topo_busca.pack(fill="x", pady=(0, 6))
        
        ttk.Label(topo_busca, text="Filtrar:").pack(side="left", padx=(0, 6))
        
        var_busca = tk.StringVar()
        # Sempre que o texto mudar, chama a função de atualização correspondente
        var_busca.trace("w", lambda *_: comando_atualizar())
        
        entry_busca = ttk.Entry(topo_busca, textvariable=var_busca, width=largura)
        entry_busca.pack(side="left")
        
        ttk.Button(topo_busca, text="Limpar", command=lambda: var_busca.set("")).pack(side="left", padx=6)
        
        return var_busca

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
        
        self._aplicar_efeito_zebra(self.tv_cal)

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

    def fazer_backup(self):
        if self.site is None:
            return self.escolher_pasta()
        
        ok, caminho = self._executar("Gerando backup em .zip...", self.site.gerar_backup)
        if ok and caminho:
            self.log(f"Backup gerado com sucesso: {caminho.name}")
            messagebox.showinfo("Backup Concluído", f"Backup criado com sucesso em:\n{caminho}", parent=self)

    def _calcular_metricas_dashboard(self) -> dict:
        """Calcula todas as estatísticas para exibição no Dashboard Resumo."""
        if self.site is None:
            return {}

        atletas = [a for a in self.site.listar_elenco() if a["grupo"] != sp.GRUPO_STAFF]
        jogos = self.site.listar_jogos()
        transacoes = self.site.listar_financas()

        # 1. Artilheiro e Garçom
        artilheiro = max(atletas, key=lambda a: a.get("gols", 0), default=None)
        garcom = max(atletas, key=lambda a: a.get("assistencias", 0), default=None)

        # 2. Desempenho do Time
        vitorias = sum(1 for j in jogos if j.get("resultado") == "vitoria")
        empates = sum(1 for j in jogos if j.get("resultado") == "empate")
        derrotas = sum(1 for j in jogos if j.get("resultado") == "derrota")
        total_jogos = len([j for j in jogos if j.get("placar")])

        aproveitamento = 0.0
        if total_jogos > 0:
            pontos_ganhos = (vitorias * 3) + (empates * 1)
            pontos_possiveis = total_jogos * 3
            aproveitamento = (pontos_ganhos / pontos_possiveis) * 100

        # 3. Financeiro
        saldo = 0.0
        for t in transacoes:
            val = float(t.get("valor", 0))
            if t.get("tipo") == "recebita":
                saldo += val
            else:
                saldo -= val

        # 4. Próximo Jogo
        hoje = date.today()
        proximos = [j for j in jogos if datetime.strptime(j["data_br"], "%d/%m/%Y").date() >= hoje]
        proximos.sort(key=lambda j: datetime.strptime(j["data_br"], "%d/%m/%Y").date())
        proximo_jogo = proximos[0] if proximos else None

        return {
            "artilheiro": f"{artilheiro['nome']} ({artilheiro['gols']} gols)" if artilheiro and artilheiro.get("gols", 0) > 0 else "Nenhum",
            "garcom": f"{garcom['nome']} ({garcom['assistencias']} assist.)" if garcom and garcom.get("assistencias", 0) > 0 else "Nenhum",
            "retrospecto": f"{vitorias}V - {empates}E - {derrotas}D ({aproveitamento:.1f}%)",
            "saldo_caixa": f"R$ {saldo:.2f}",
            "proximo_jogo": f"{proximo_jogo['data_br']} {proximo_jogo['hora']} vs {proximo_jogo['adversario']}" if proximo_jogo else "Nenhum jogo agendado"
        }
    
    def _aplicar_efeito_zebra(self, treeview):
        """Aplica cores alternadas (efeito zebra) nas linhas da Treeview."""
        linhas = treeview.get_children()
        for i, item_id in enumerate(linhas):
            if i % 2 == 0:
                treeview.item(item_id, tags=("par",))
            else:
                treeview.item(item_id, tags=("impar",))
        
        # Configura as cores das tags
        treeview.tag_configure("par", background="#ffffff")
        treeview.tag_configure("impar", background="#f8fafc")

def main():
    App().mainloop()


if __name__ == "__main__":
    main()
