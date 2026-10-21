#!/usr/bin/env python3

import json
import re
import os
import unicodedata
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class GerenciadorJogadoresApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gerenciador de Ranking - Pétalas Negras FC")
        self.root.geometry("620x480")
        self.root.minsize(580, 440)

        self.caminho_json = "jogadores.json"
        self.caminho_html = "ranking.html"
        self.dados_json = {}

        self.estilo = ttk.Style()
        self.estilo.theme_use("clam")
        
        self.cor_bg = "#f8fafc"
        self.cor_primaria = "#6d28d9"
        self.cor_texto = "#1e293b"
        
        self.root.configure(bg=self.cor_bg)
        self.estilo.configure(".", background=self.cor_bg, foreground=self.cor_texto, font=("Segoe UI", 10))
        self.estilo.configure("TLabelframe", background=self.cor_bg, bordercolor="#cbd5e1", relief="solid")
        self.estilo.configure("TLabelframe.Label", background=self.cor_bg, foreground=self.cor_primaria, font=("Segoe UI", 10, "bold"))
        self.estilo.configure("Accent.TButton", background=self.cor_primaria, foreground="#ffffff", font=("Segoe UI", 10, "bold"))

        self.criar_widgets()
        self.tentar_carregar_json_padrao()

    def criar_widgets(self):
        frame_principal = ttk.LabelFrame(self.root, text=" Gerenciamento de Estatísticas ", padding=15)
        frame_principal.pack(fill="both", expand=True, padx=15, pady=15)
        frame_principal.columnconfigure(1, weight=1)

        btn_carregar = ttk.Button(frame_principal, text="📂 Selecionar JSON...", command=self.selecionar_json)
        btn_carregar.grid(row=0, column=0, sticky="w", pady=5)

        self.lbl_status_json = ttk.Label(frame_principal, text="Nenhum arquivo selecionado", foreground="#b91c1c")
        self.lbl_status_json.grid(row=0, column=1, sticky="w", pady=5, padx=10)

        ttk.Label(frame_principal, text="Selecionar Atleta:").grid(row=1, column=0, sticky="w", pady=10)
        self.combo_jogadores = ttk.Combobox(frame_principal, state="readonly", width=30)
        self.combo_jogadores.grid(row=1, column=1, sticky="w", pady=10, padx=5)
        self.combo_jogadores.bind("<<ComboboxSelected>>", self.ao_selecionar_jogador)

        ttk.Label(frame_principal, text="Partidas Jogadas:").grid(row=2, column=0, sticky="w", pady=8)
        self.ent_jogos = ttk.Entry(frame_principal, width=15)
        self.ent_jogos.grid(row=2, column=1, sticky="w", pady=8, padx=5)

        ttk.Label(frame_principal, text="Gols Marcados:").grid(row=3, column=0, sticky="w", pady=8)
        self.ent_gols = ttk.Entry(frame_principal, width=15)
        self.ent_gols.grid(row=3, column=1, sticky="w", pady=8, padx=5)

        ttk.Label(frame_principal, text="Assistências:").grid(row=4, column=0, sticky="w", pady=8)
        self.ent_assists = ttk.Entry(frame_principal, width=15)
        self.ent_assists.grid(row=4, column=1, sticky="w", pady=8, padx=5)

        btn_salvar = ttk.Button(frame_principal, text="Salvar Estatísticas no JSON", command=self.salvar_stats)
        btn_salvar.grid(row=5, column=0, columnspan=2, pady=10, sticky="w", padx=5)

        btn_gerar_html = ttk.Button(frame_principal, text="🚀 Gerar / Atualizar 'ranking.html'", style="Accent.TButton", command=self.atualizar_html)
        btn_gerar_html.grid(row=6, column=0, columnspan=2, pady=15, sticky="ew", padx=5)

        frame_log = ttk.LabelFrame(self.root, text=" Log ", padding=6)
        frame_log.pack(fill="x", padx=15, pady=(0, 15))

        self.txt_log = tk.Text(frame_log, height=4, width=70, state="disabled", bg="#ffffff", fg="#334155", font=("Consolas", 9), relief="flat")
        self.txt_log.pack(fill="x", padx=5, pady=5)

    def log(self, mensagem):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", mensagem + "\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def tentar_carregar_json_padrao(self):
        if os.path.exists(self.caminho_json):
            self.carregar_dados_json(self.caminho_json)

    def selecionar_json(self):
        caminho = filedialog.askopenfilename(filetypes=[("Arquivos JSON", "*.json")])
        if caminho:
            self.carregar_dados_json(caminho)

    def carregar_dados_json(self, caminho):
        try:
            self.caminho_json = caminho
            with open(caminho, 'r', encoding='utf-8') as f:
                self.dados_json = json.load(f)

            jogadores_validos = [
                k for k, v in self.dados_json.items()
                if v.get("grupo") != "tecnico" and v.get("posicao") not in ["Técnico", "Fotógrafa"]
            ]
            self.combo_jogadores['values'] = sorted(jogadores_validos)
            if jogadores_validos:
                self.combo_jogadores.current(0)
                self.ao_selecionar_jogador()

            self.lbl_status_json.config(text=os.path.basename(caminho), foreground="#15803d")
            self.log(f"Arquivo carregado: {caminho}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao ler JSON: {e}")

    def ao_selecionar_jogador(self, event=None):
        chave = self.combo_jogadores.get()
        if chave in self.dados_json:
            j = self.dados_json[chave]
            self.ent_jogos.delete(0, tk.END)
            self.ent_jogos.insert(0, str(j.get("jogos", 0)))

            self.ent_gols.delete(0, tk.END)
            self.ent_gols.insert(0, str(j.get("gols", 0)))

            self.ent_assists.delete(0, tk.END)
            self.ent_assists.insert(0, str(j.get("assistencias", 0)))

    def salvar_stats(self):
        chave = self.combo_jogadores.get()
        if not chave or chave not in self.dados_json:
            messagebox.showwarning("Aviso", "Selecione um jogador válido!")
            return

        try:
            jogos = int(self.ent_jogos.get().strip())
            gols = int(self.ent_gols.get().strip())
            assists = int(self.ent_assists.get().strip())

            self.dados_json[chave]["jogos"] = jogos
            self.dados_json[chave]["gols"] = gols
            self.dados_json[chave]["assistencias"] = assists

            with open(self.caminho_json, 'w', encoding='utf-8') as f:
                json.dump(self.dados_json, f, ensure_ascii=False, indent=2)

            self.log(f"Estatísticas atualizadas para {self.dados_json[chave]['nome']}")
            messagebox.showinfo("Sucesso", "Estatísticas salvas no arquivo JSON!")
        except ValueError:
            messagebox.showwarning("Aviso", "Informe valores numéricos válidos nos campos!")

    def obter_caminho_foto(self, nome_jogador):
        nfkd = unicodedata.normalize('NFKD', nome_jogador)
        nome_limpo = "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()
        return f"imagens/jogadores/{nome_limpo}.jpeg"

    def gerar_cards_ranking(self, campo_stat):
        jogadores_filtrados = []
        for k, v in self.dados_json.items():
            if v.get("grupo") == "tecnico" or v.get("posicao") in ["Técnico", "Fotógrafa"]:
                continue
            val = v.get(campo_stat, 0)
            if val > 0:
                # Armazena a chave ID para o link do perfil
                atleta = dict(v)
                atleta['id_link'] = k
                jogadores_filtrados.append(atleta)

        jogadores_filtrados.sort(key=lambda x: (x.get(campo_stat, 0), x.get("jogos", 0)), reverse=True)

        if not jogadores_filtrados:
            return '<div class="vazio">Nenhum registro para esta categoria.</div>'

        elementos = []
        posicao_atual = 1
        ultimo_valor = None

        if campo_stat == "gols":
            label_unidade, label_plural = "Gol", "Gols"
        elif campo_stat == "assistencias":
            label_unidade, label_plural = "Assistência", "Assistências"
        else:
            label_unidade, label_plural = "Jogo", "Jogos"

        for i, j in enumerate(jogadores_filtrados):
            nome_real = j.get('nome', '')
            id_atleta = j.get('id_link', '')
            foto_path = self.obter_caminho_foto(nome_real)
            val_stat = j.get(campo_stat, 0)
            num_camisa = f'<span class="atleta-numero">#{j.get("numero")}</span>' if j.get("numero") else ''

            if val_stat != ultimo_valor:
                if ultimo_valor is not None:
                    posicao_atual += 1
                ultimo_valor = val_stat
                
                txt_subtitulo = f"{val_stat} {label_unidade if val_stat == 1 else label_plural}"
                elementos.append(f'<div class="ranking-divisor-grupo">{txt_subtitulo}</div>')

            # Bloco/Card inteiro clicável redirecionando para jogador.html?id=...
            card = f'''<a class="ranking-card-item" href="jogador.html?id={id_atleta}">
  <div class="ranking-card-esquerda">
    <span class="ranking-posicao">{posicao_atual}º</span>
    <img src="{foto_path}" alt="{nome_real}" class="ranking-foto-mini" onerror="this.src='imagens/logo.jpeg'">
    <div class="ranking-info-atleta">
      <div class="ranking-nome-linha">
        <strong>{nome_real}</strong>
        {num_camisa}
      </div>
      <span class="ranking-posicao-sub">{j.get('posicao', '-')}</span>
    </div>
  </div>
  <div class="ranking-stat-valor">{val_stat}</div>
</a>'''
            elementos.append(card)

        return "\n".join(elementos)

    def atualizar_html(self):
        if not os.path.exists(self.caminho_html):
            messagebox.showerror("Erro", f"Arquivo {self.caminho_html} não foi encontrado!")
            return

        try:
            with open(self.caminho_html, 'r', encoding='utf-8') as f:
                conteudo_html = f.read()

            html_gols = self.gerar_cards_ranking("gols")
            conteudo_html = re.sub(
                r'<!-- RANKING_ARTILHARIA_INICIO -->.*?<!-- RANKING_ARTILHARIA_FIM -->',
                f'<!-- RANKING_ARTILHARIA_INICIO -->\n{html_gols}\n<!-- RANKING_ARTILHARIA_FIM -->',
                conteudo_html,
                flags=re.DOTALL
            )

            html_assists = self.gerar_cards_ranking("assistencias")
            conteudo_html = re.sub(
                r'<!-- RANKING_ASSISTENCIAS_INICIO -->.*?<!-- RANKING_ASSISTENCIAS_FIM -->',
                f'<!-- RANKING_ASSISTENCIAS_INICIO -->\n{html_assists}\n<!-- RANKING_ASSISTENCIAS_FIM -->',
                conteudo_html,
                flags=re.DOTALL
            )

            html_jogos = self.gerar_cards_ranking("jogos")
            conteudo_html = re.sub(
                r'<!-- RANKING_JOGOS_INICIO -->.*?<!-- RANKING_JOGOS_FIM -->',
                f'<!-- RANKING_JOGOS_INICIO -->\n{html_jogos}\n<!-- RANKING_JOGOS_FIM -->',
                conteudo_html,
                flags=re.DOTALL
            )

            with open(self.caminho_html, 'w', encoding='utf-8') as f:
                f.write(conteudo_html)

            self.log("✅ Página 'ranking.html' atualizada com sucesso!")
            messagebox.showinfo("Sucesso", "O ranking foi gerado e atualizado com sucesso!")

        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao atualizar HTML: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = GerenciadorJogadoresApp(root)
    root.mainloop()