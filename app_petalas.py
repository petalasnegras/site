#!/usr/bin/env python3
"""
app_petalas - interface gráfica (tkinter) para a biblioteca site_petalas.

Coloque este arquivo na mesma pasta do site_petalas.py e execute:

    python app_petalas.py

Na primeira vez, escolha a pasta do site (a que tem index.html e a pasta dados/ com os CSVs).
A pasta escolhida fica salva em ~/.petalas_gui.json.

Só usa a biblioteca padrão (Python 3.8+).
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
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
                         "Coloque o app_petalas.py na mesma pasta do site_petalas.py.")
    raise SystemExit(1)

CONFIG = Path.home() / ".petalas_gui.json"

POSICOES = ["Goleiro", "Zagueiro", "Lateral direito", "Lateral esquerdo", "Volante", "Meio-campista",
            "Ponta", "Centroavante", "Técnico", "Preparador físico", "Auxiliar técnico", "Fotógrafo"]
PES = ["", "Destro", "Canhoto", "Ambidestro"]


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
        tv.column(id_, width=largura, anchor=ancora, stretch=(id_ in ("nome", "adversario")))
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


# ====================================================================== aplicativo


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pétalas Negras - gerenciador do site")
        self.geometry("1000x720")
        self.minsize(860, 560)
        self.site = None
        self.var_pasta = tk.StringVar()
        self.var_auto = tk.BooleanVar(value=True)

        self._montar_topo()
        self._montar_abas()
        self._montar_rodape()

        pasta = self._pasta_salva()
        if pasta:
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

    def _montar_abas(self):
        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=10)
        self._aba_elenco()
        self._aba_jogos()

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
        except (sp.ErroDados, OSError) as e:
            self._erro(e)
            return False, None
        self.log(descricao)
        return True, resultado

    def _depois_de_alterar(self):
        self.recarregar_listas()
        if self.var_auto.get():
            self.atualizar_site()

    # ------------------------------------------------------------ pasta do site

    @staticmethod
    def _pasta_salva():
        try:
            pasta = json.loads(CONFIG.read_text(encoding="utf-8")).get("pasta", "")
            return pasta if pasta and Path(pasta).is_dir() else ""
        except (OSError, ValueError):
            return ""

    def escolher_pasta(self):
        pasta = filedialog.askdirectory(parent=self, title="Escolha a pasta do site (com index.html)",
                                        initialdir=self.var_pasta.get() or str(Path.home()))
        if pasta:
            self.abrir_site(pasta)

    def abrir_site(self, pasta: str):
        self.site = sp.Site(pasta)
        self.var_pasta.set(str(self.site.raiz))
        try:
            CONFIG.write_text(json.dumps({"pasta": str(self.site.raiz)}), encoding="utf-8")
        except OSError:
            pass
        self.log(f"Site aberto: {self.site.raiz} (dados em {self.site.pasta_dados})")
        self.recarregar_listas()

    def recarregar(self):
        if self.site is not None:
            self.abrir_site(str(self.site.raiz))

    def recarregar_listas(self):
        self._preencher_elenco()
        self._preencher_jogos()

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

    def _selecionado(self, tv, o_que):
        sel = tv.selection()
        if not sel:
            messagebox.showinfo("Seleção", f"Selecione {o_que} na lista.", parent=self)
            return None
        return sel[0]

    # ------------------------------------------------------------ atualizar páginas

    def atualizar_site(self):
        ok, rel = self._executar("Gerando páginas e JSONs...", self.site.atualizar_tudo
                                 if self.site else (lambda: None))
        if not ok or rel is None:
            return
        e, j = rel["elenco"], rel["jogos"]
        self.log(f"Site atualizado: {e['atletas']} atletas, {e['comissao']} na comissão técnica, "
                 f"{j['jogos']} jogos ({j['proximos']} próximos, {j['realizados']} realizados).")
        for aviso in rel["avisos"]:
            self.log(f"Aviso: {aviso}", "aviso")

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
            campos = dict(v)
            ok2, _ = self._executar(f"Atualizado: {v['nome']}", self.site.editar_pessoa, nome, **campos)
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


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
