#!/usr/bin/env python3
import json
import re
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class GerenciadorCalendarioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gerenciador de Calendário - Pétalas Negras FC")
        self.root.geometry("650x580")
        self.root.minsize(600, 520)

        self.caminho_json = None
        self.caminho_html = "calendario.html"
        self.dados_json = {}

        # Configurar Estilo Moderno
        self.estilo = ttk.Style()
        self.estilo.theme_use("clam")
        
        # Paleta de Cores
        self.cor_bg = "#f8fafc"
        self.cor_primaria = "#6d28d9" # Roxo Pétalas Negras
        self.cor_texto = "#1e293b"
        
        self.root.configure(bg=self.cor_bg)
        self.estilo.configure(".", background=self.cor_bg, foreground=self.cor_texto, font=("Segoe UI", 10))
        self.estilo.configure("TNotebook", background=self.cor_bg, borderwidth=0)
        self.estilo.configure("TNotebook.Tab", padding=[15, 8], font=("Segoe UI", 10, "bold"))
        self.estilo.configure("TLabelframe", background=self.cor_bg, bordercolor="#cbd5e1", relief="solid")
        self.estilo.configure("TLabelframe.Label", background=self.cor_bg, foreground=self.cor_primaria, font=("Segoe UI", 10, "bold"))
        self.estilo.configure("Accent.TButton", background=self.cor_primaria, foreground="#ffffff", font=("Segoe UI", 10, "bold"))

        self.criar_widgets()

    def criar_widgets(self):
        # Notebook (Abas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=15)

        # Aba 1: Gerenciar / Editar Eventos
        self.tab_gerenciar = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_gerenciar, text="📅 Gerenciar Eventos")
        self.construir_aba_gerenciar()

        # Aba 2: Criar Novo JSON
        self.tab_novo = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_novo, text="➕ Criar Novo JSON")
        self.construir_aba_novo()

        # Painel de Log Inferior (Global)
        frame_log = ttk.LabelFrame(self.root, text=" Log de Operações ", padding=8)
        frame_log.pack(fill="x", padx=15, pady=(0, 15))

        self.txt_log = tk.Text(frame_log, height=5, width=70, state="disabled", bg="#ffffff", fg="#334155", font=("Consolas", 9), relief="flat")
        self.txt_log.pack(fill="x", padx=5, pady=5)

    def construir_aba_gerenciar(self):
        # Seleção de JSON
        frame_arquivo = ttk.LabelFrame(self.tab_gerenciar, text=" 1. Base de Dados Atual ", padding=10)
        frame_arquivo.pack(fill="x", pady=(0, 10))

        btn_carregar = ttk.Button(frame_arquivo, text="📂 Selecionar JSON...", command=self.selecionar_json)
        btn_carregar.pack(side="left", padx=5)

        self.lbl_status_json = ttk.Label(frame_arquivo, text="Nenhum arquivo selecionado", foreground="#b91c1c")
        self.lbl_status_json.pack(side="left", padx=10)

        # Edição de Evento
        frame_edicao = ttk.LabelFrame(self.tab_gerenciar, text=" 2. Adicionar / Atualizar Evento no Mês ", padding=10)
        frame_edicao.pack(fill="x", pady=(0, 10))

        frame_edicao.columnconfigure(1, weight=1)

        ttk.Label(frame_edicao, text="Dia do Mês:").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_dia = ttk.Entry(frame_edicao, width=15)
        self.ent_dia.grid(row=0, column=1, sticky="w", pady=5, padx=5)

        ttk.Label(frame_edicao, text="Tipo de Evento:").grid(row=1, column=0, sticky="w", pady=5)
        self.combo_tipo = ttk.Combobox(frame_edicao, values=["jogo", "treino", "remover"], state="readonly", width=18)
        self.combo_tipo.set("jogo")
        self.combo_tipo.grid(row=1, column=1, sticky="w", pady=5, padx=5)

        ttk.Label(frame_edicao, text="Horário (ex: 10:00):").grid(row=2, column=0, sticky="w", pady=5)
        self.ent_hora = ttk.Entry(frame_edicao, width=25)
        self.ent_hora.grid(row=2, column=1, sticky="w", pady=5, padx=5)

        ttk.Label(frame_edicao, text="Descrição / Adversário:").grid(row=3, column=0, sticky="w", pady=5)
        self.ent_titulo = ttk.Entry(frame_edicao, width=40)
        self.ent_titulo.grid(row=3, column=1, sticky="w", pady=5, padx=5)

        btn_salvar_evento = ttk.Button(frame_edicao, text="Salvar Evento no JSON", command=self.salvar_evento_json)
        btn_salvar_evento.grid(row=4, column=0, columnspan=2, pady=10, sticky="w", padx=5)

        # Ação HTML
        frame_acoes = ttk.LabelFrame(self.tab_gerenciar, text=" 3. Publicar Site ", padding=10)
        frame_acoes.pack(fill="x")

        btn_gerar_html = ttk.Button(frame_acoes, text="🚀 Atualizar 'calendario.html'", style="Accent.TButton", command=self.atualizar_html)
        btn_gerar_html.pack(fill="x", pady=5)

    def construir_aba_novo(self):
        frame_novo = ttk.LabelFrame(self.tab_novo, text=" Gerador de Novo Arquivo JSON Mensal ", padding=15)
        frame_novo.pack(fill="both", expand=True)

        frame_novo.columnconfigure(1, weight=1)

        ttk.Label(frame_novo, text="Nome do Mês e Ano (ex: Novembro 2026):").grid(row=0, column=0, sticky="w", pady=8)
        self.ent_novo_mes = ttk.Entry(frame_novo, width=30)
        self.ent_novo_mes.grid(row=0, column=1, sticky="w", pady=8, padx=5)
        self.ent_novo_mes.insert(0, "Novembro 2026")

        ttk.Label(frame_novo, text="Dias do mês anterior (ex: 29,30):").grid(row=1, column=0, sticky="w", pady=8)
        self.ent_novo_anteriores = ttk.Entry(frame_novo, width=30)
        self.ent_novo_anteriores.grid(row=1, column=1, sticky="w", pady=8, padx=5)
        self.ent_novo_anteriores.insert(0, "29, 30, 31")

        ttk.Label(frame_novo, text="Total de dias do mês (ex: 30 ou 31):").grid(row=2, column=0, sticky="w", pady=8)
        self.ent_novo_total = ttk.Entry(frame_novo, width=15)
        self.ent_novo_total.grid(row=2, column=1, sticky="w", pady=8, padx=5)
        self.ent_novo_total.insert(0, "30")

        btn_criar_json = ttk.Button(frame_novo, text="💾 Criar e Salvar Arquivo JSON", style="Accent.TButton", command=self.criar_novo_json_arquivo)
        btn_criar_json.grid(row=3, column=0, columnspan=2, pady=20, sticky="w", padx=5)

    def log(self, mensagem):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", mensagem + "\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def selecionar_json(self):
        caminho = filedialog.askopenfilename(filetypes=[("Arquivos JSON", "*.json")])
        if caminho:
            self.caminho_json = caminho
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    self.dados_json = json.load(f)
                self.lbl_status_json.config(text=os.path.basename(caminho), foreground="#15803d")
                self.log(f"Arquivo carregado com sucesso: {caminho}")
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao ler arquivo JSON: {e}")

    def salvar_evento_json(self):
        if not self.caminho_json:
            messagebox.showwarning("Aviso", "Selecione um arquivo JSON na aba de gerenciamento primeiro!")
            return

        dia = self.ent_dia.get().strip()
        tipo = self.combo_tipo.get()
        hora = self.ent_hora.get().strip()
        titulo = self.ent_titulo.get().strip()

        if not dia.isdigit():
            messagebox.showwarning("Aviso", "O campo 'Dia do Mês' deve conter apenas números!")
            return

        if "eventos" not in self.dados_json:
            self.dados_json["eventos"] = {}

        if tipo == "remover":
            if dia in self.dados_json["eventos"]:
                del self.dados_json["eventos"][dia]
                self.log(f"Evento do dia {dia} removido.")
        else:
            self.dados_json["eventos"][dia] = {
                "tipo": tipo,
                "hora": hora,
                "titulo": titulo
            }
            self.log(f"Evento salvo no dia {dia}: [{tipo.upper()}] {hora} - {titulo}")

        try:
            with open(self.caminho_json, 'w', encoding='utf-8') as f:
                json.dump(self.dados_json, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Sucesso", f"Evento do dia {dia} atualizado no JSON!")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar o JSON: {e}")

    def criar_novo_json_arquivo(self):
        nome_mes = self.ent_novo_mes.get().strip()
        texto_anteriores = self.ent_novo_anteriores.get().strip()
        total_dias_str = self.ent_novo_total.get().strip()

        if not nome_mes or not total_dias_str.isdigit():
            messagebox.showwarning("Aviso", "Preencha o nome do mês e o total de dias corretamente!")
            return

        try:
            # Converte string "29, 30, 31" em lista de inteiros [29, 30, 31]
            anteriores = [int(x.strip()) for x in texto_anteriores.split(",") if x.strip().isdigit()]
        except:
            anteriores = []

        novo_dicionario = {
            "mes_ano": nome_mes,
            "offset_dias_anteriores": anteriores,
            "total_dias_mes": int(total_dias_str),
            "eventos": {}
        }

        arquivo_sugerido = f"eventos_{nome_mes.lower().replace(' ', '_')}.json"
        caminho_salvar = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=arquivo_sugerido,
            filetypes=[("Arquivos JSON", "*.json")]
        )

        if caminho_salvar:
            try:
                with open(caminho_salvar, 'w', encoding='utf-8') as f:
                    json.dump(novo_dicionario, f, ensure_ascii=False, indent=2)
                
                self.caminho_json = caminho_salvar
                with open(caminho_salvar, 'r', encoding='utf-8') as f:
                    self.dados_json = json.load(f)

                self.lbl_status_json.config(text=os.path.basename(caminho_salvar), foreground="#15803d")
                self.log(f"Novo JSON criado: {caminho_salvar}")
                messagebox.showinfo("Sucesso", "Novo arquivo JSON criado e selecionado com sucesso!")
                self.notebook.select(self.tab_gerenciar) # Volta para a aba de gerenciar
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao criar arquivo: {e}")

    def gerar_grid_html(self):
        dias_anteriores = self.dados_json.get("offset_dias_anteriores", [])
        total_dias = self.dados_json.get("total_dias_mes", 31)
        eventos = self.dados_json.get("eventos", {})

        html_buffer = []

        # Dias do mês anterior
        for dia in dias_anteriores:
            html_buffer.append(f'          <div class="dia-celula outro-mes"><span class="num-dia">{dia}</span></div>')

        # Dias do mês atual (sem marcação de dia atual)
        for d in range(1, total_dias + 1):
            dia_str = str(d)
            linha = f'          <div class="dia-celula">\n            <span class="num-dia">{d}</span>'

            if dia_str in eventos:
                ev = eventos[dia_str]
                tipo_classe = "evento-jogo" if ev["tipo"] == "jogo" else "evento-treino"
                linha += f'\n            <div class="evento {tipo_classe}">\n              <strong>{ev["hora"]}</strong> {ev["titulo"]}\n            </div>'

            linha += '\n          </div>'
            html_buffer.append(linha)

        return "\n".join(html_buffer)

    def atualizar_html(self):
        if not self.caminho_json:
            messagebox.showwarning("Aviso", "Selecione um arquivo JSON primeiro!")
            return

        if not os.path.exists(self.caminho_html):
            messagebox.showerror("Erro", f"O arquivo {self.caminho_html} não foi encontrado na pasta!")
            return

        try:
            with open(self.caminho_html, 'r', encoding='utf-8') as f:
                conteudo_html = f.read()

            # Atualiza Título do Mês
            mes_ano = self.dados_json.get("mes_ano", "Calendário")
            conteudo_html = re.sub(
                r'<!-- TITULO_MES:INICIO -->.*?<!-- TITULO_MES:FIM -->',
                f'<!-- TITULO_MES:INICIO -->\n          <h2>{mes_ano}</h2>\n          <!-- TITULO_MES:FIM -->',
                conteudo_html,
                flags=re.DOTALL
            )

            # Atualiza Grid de Dias
            novo_grid = self.gerar_grid_html()
            conteudo_html = re.sub(
                r'<!-- CALENDARIO_INICIO -->.*?<!-- CALENDARIO_FIM -->',
                f'<!-- CALENDARIO_INICIO -->\n{novo_grid}\n          <!-- CALENDARIO_FIM -->',
                conteudo_html,
                flags=re.DOTALL
            )

            with open(self.caminho_html, 'w', encoding='utf-8') as f:
                f.write(conteudo_html)

            self.log("✅ Arquivo 'calendario.html' atualizado com sucesso!")
            messagebox.showinfo("Sucesso", "O site foi atualizado com sucesso com base no JSON!")

        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao atualizar o HTML: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = GerenciadorCalendarioApp(root)
    root.mainloop()