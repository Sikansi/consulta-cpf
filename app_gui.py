import tkinter as tk
from tkinter import messagebox, ttk

from api_client import (
    MSG_ESGOTADO,
    campos_disponiveis,
    consultar_varios,
    status_uso,
    todos_esgotados,
)
from cpf_utils import extrair_cpfs_com_nascimento, rotulo_campo, validar_cpf

_NOMES_TIPO = {"diario": "hoje", "mensal": "mês", "total": "total"}


class ConsultaCpfApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Consulta CPF")
        self.geometry("1060x700")
        self.minsize(900, 560)

        self.resultados: list[dict] = []
        self.campos_vars: dict[str, tk.BooleanVar] = {}
        self._campos_padrao = {"cpf", "nome", "situacao"}

        self._montar_layout()
        self._definir_campos_iniciais()
        self._atualizar_contador()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text="Consulta de CPF",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor=tk.W, pady=(0, 4))

        ttk.Label(
            container,
            text="Um CPF por linha. Para usar Consultar.io informe CPF|YYYY-MM-DD (ex: 11144477735|1990-01-15).",
            foreground="#555555",
        ).pack(anchor=tk.W, pady=(0, 8))

        corpo = ttk.Panedwindow(container, orient=tk.HORIZONTAL)
        corpo.pack(fill=tk.BOTH, expand=True)

        painel_entrada = ttk.Frame(corpo, padding=(0, 0, 8, 0))
        painel_direito = ttk.Frame(corpo, width=280)
        corpo.add(painel_entrada, weight=3)
        corpo.add(painel_direito, weight=1)

        # Área de texto
        self.texto_cpfs = tk.Text(painel_entrada, height=10, wrap=tk.WORD, font=("Consolas", 11))
        self.texto_cpfs.pack(fill=tk.BOTH, expand=True)

        # Botões
        acoes = ttk.Frame(painel_entrada)
        acoes.pack(fill=tk.X, pady=(8, 0))

        self.btn_consultar = ttk.Button(acoes, text="Consultar", command=self._consultar)
        self.btn_consultar.pack(side=tk.LEFT)

        ttk.Button(acoes, text="Limpar", command=self._limpar).pack(side=tk.LEFT, padx=(8, 0))

        self.status = ttk.Label(acoes, text="Pronto.")
        self.status.pack(side=tk.LEFT, padx=(12, 0))

        # ---- Painel direito: filtros + contador ----
        ttk.Label(
            painel_direito,
            text="Campos visíveis",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W)

        ttk.Label(
            painel_direito,
            text="Marque apenas o que deseja exibir.",
            wraplength=260,
            foreground="#555555",
        ).pack(anchor=tk.W, pady=(2, 6))

        self.frame_campos = ttk.Frame(painel_direito)
        self.frame_campos.pack(fill=tk.X)

        botoes_filtro = ttk.Frame(painel_direito)
        botoes_filtro.pack(fill=tk.X, pady=(8, 0))

        ttk.Button(botoes_filtro, text="Somente nome", command=self._somente_nome).pack(fill=tk.X)
        ttk.Button(botoes_filtro, text="Marcar todos", command=self._marcar_todos).pack(fill=tk.X, pady=(4, 0))
        ttk.Button(botoes_filtro, text="Atualizar tabela", command=self._atualizar_tabela).pack(fill=tk.X, pady=(4, 0))

        # ---- Contador de créditos ----
        ttk.Separator(painel_direito, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(16, 8))

        ttk.Label(
            painel_direito,
            text="Créditos disponíveis",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W)

        self._widgets_contador: dict[str, dict] = {}
        for prov in ("apicpf", "cpfhub", "consultario"):
            frame = ttk.Frame(painel_direito)
            frame.pack(fill=tk.X, pady=(6, 0))

            lbl_nome = ttk.Label(frame, text="", width=13, anchor=tk.W)
            lbl_nome.pack(side=tk.LEFT)

            bar = ttk.Progressbar(frame, orient=tk.HORIZONTAL, length=80, mode="determinate")
            bar.pack(side=tk.LEFT, padx=(4, 4))

            lbl_num = ttk.Label(frame, text="", width=10, anchor=tk.W)
            lbl_num.pack(side=tk.LEFT)

            self._widgets_contador[prov] = {"nome": lbl_nome, "bar": bar, "num": lbl_num}

        # ---- Tabela de resultados ----
        ttk.Label(container, text="Resultados", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(14, 4))

        area_tabela = ttk.Frame(container)
        area_tabela.pack(fill=tk.BOTH, expand=True)

        self.tabela = ttk.Treeview(area_tabela, show="headings", height=12)
        self.tabela.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scroll_y = ttk.Scrollbar(area_tabela, orient=tk.VERTICAL, command=self.tabela.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tabela.configure(yscrollcommand=scroll_y.set)

    # ------------------------------------------------------------------
    # Contador
    # ------------------------------------------------------------------

    def _atualizar_contador(self) -> None:
        uso = status_uso()
        for prov, widgets in self._widgets_contador.items():
            info = uso[prov]
            label = info["label"]
            restante = info["restante"]
            maximo = info["maximo"]
            tipo = _NOMES_TIPO.get(info["tipo"], info["tipo"])
            tem_chave = info["tem_chave"]

            widgets["nome"].config(text=label)

            if not tem_chave:
                widgets["bar"]["value"] = 0
                widgets["bar"]["maximum"] = 100
                widgets["num"].config(text="sem chave", foreground="#aaaaaa")
            else:
                widgets["bar"]["maximum"] = maximo
                widgets["bar"]["value"] = restante
                cor = "#cc0000" if restante == 0 else ("#e67e00" if restante <= maximo * 0.2 else "#1a7a1a")
                esgotado_txt = " ✗" if restante == 0 else ""
                widgets["num"].config(
                    text=f"{restante}/{maximo} {tipo}{esgotado_txt}",
                    foreground=cor,
                )

    # ------------------------------------------------------------------
    # Campos / filtros
    # ------------------------------------------------------------------

    def _definir_campos_iniciais(self) -> None:
        for campo in ["cpf", "nome", "nascimento", "mae", "genero", "situacao", "cidade", "uf", "erro"]:
            self._adicionar_checkbox_campo(campo, campo in self._campos_padrao)

    def _adicionar_checkbox_campo(self, campo: str, marcado: bool) -> None:
        if campo in self.campos_vars:
            return
        var = tk.BooleanVar(value=marcado)
        self.campos_vars[campo] = var
        ttk.Checkbutton(
            self.frame_campos,
            text=rotulo_campo(campo),
            variable=var,
            command=self._atualizar_tabela,
        ).pack(anchor=tk.W, pady=1)

    def _campos_selecionados(self) -> list[str]:
        return [c for c, v in self.campos_vars.items() if v.get()]

    def _somente_nome(self) -> None:
        for campo, var in self.campos_vars.items():
            var.set(campo in {"cpf", "nome"})
        self._atualizar_tabela()

    def _marcar_todos(self) -> None:
        for var in self.campos_vars.values():
            var.set(True)
        self._atualizar_tabela()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def _limpar(self) -> None:
        self.texto_cpfs.delete("1.0", tk.END)
        self.resultados = []
        self._atualizar_tabela()
        self.status.config(text="Entrada limpa.")

    def _consultar(self) -> None:
        texto = self.texto_cpfs.get("1.0", tk.END)
        cpfs, nascimentos = extrair_cpfs_com_nascimento(texto)

        if not cpfs:
            messagebox.showwarning("Entrada inválida", "Informe ao menos um CPF com 11 dígitos.")
            return

        invalidos = [cpf for cpf in cpfs if not validar_cpf(cpf)]
        if invalidos:
            messagebox.showwarning(
                "CPF inválido",
                f"CPFs inválidos (dígito verificador):\n{', '.join(invalidos)}",
            )
            return

        if todos_esgotados():
            self._popup_esgotado()
            return

        self.btn_consultar.config(state=tk.DISABLED)
        self.status.config(text=f"Consultando {len(cpfs)} CPF(s)...")
        self.update_idletasks()

        try:
            self.resultados = consultar_varios(cpfs, nascimentos)
        except ValueError as exc:
            messagebox.showerror("Configuração", str(exc))
            self.status.config(text="Erro de configuração.")
            return
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha na consulta: {exc}")
            self.status.config(text="Erro na consulta.")
            return
        finally:
            self.btn_consultar.config(state=tk.NORMAL)
            self._atualizar_contador()

        for campo in campos_disponiveis(self.resultados):
            self._adicionar_checkbox_campo(campo, campo in self._campos_padrao)

        self._atualizar_tabela()
        self.status.config(text=f"{len(self.resultados)} consulta(s) concluída(s).")

        # Verifica se algum CPF foi barrado por esgotamento
        esgotados = [r.get("cpf", "") for r in self.resultados if r.get("erro") == MSG_ESGOTADO]
        if esgotados:
            self._popup_esgotado()

    def _popup_esgotado(self) -> None:
        messagebox.showwarning(
            "Créditos esgotados",
            "Todos os provedores de consulta atingiram o limite de créditos.\n\n"
            "• API_CPF: 100 consultas/dia\n"
            "• CPF_Hub: 50 consultas/mês\n"
            "• Consultar.io: 25 consultas no total\n\n"
            "Aguarde a renovação dos créditos ou adquira mais.",
        )

    # ------------------------------------------------------------------
    # Tabela
    # ------------------------------------------------------------------

    def _atualizar_tabela(self) -> None:
        colunas = self._campos_selecionados()
        self.tabela.delete(*self.tabela.get_children())
        self.tabela["columns"] = colunas

        for coluna in colunas:
            self.tabela.heading(coluna, text=rotulo_campo(coluna))
            self.tabela.column(coluna, width=max(120, len(rotulo_campo(coluna)) * 10), anchor=tk.W)

        for item in self.resultados:
            valores = [str(item.get(coluna, "")) for coluna in colunas]
            tag = "erro" if item.get("erro") else ""
            self.tabela.insert("", tk.END, values=valores, tags=(tag,))

        self.tabela.tag_configure("erro", foreground="#cc0000")


def iniciar() -> None:
    app = ConsultaCpfApp()
    app.mainloop()
