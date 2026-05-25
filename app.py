import os

import pandas as pd
import streamlit as st

# Injeta secrets do Streamlit como variáveis de ambiente (compatibilidade com api_client.py)
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass

from api_client import MSG_ESGOTADO, campos_disponiveis, consultar_varios, status_uso
from cpf_utils import extrair_cpfs_com_nascimento, rotulo_campo, validar_cpf

st.set_page_config(page_title="Consulta CPF", page_icon="🔍", layout="wide")

_TIPO_LABEL = {"diario": "hoje", "mensal": "mês", "total": "total"}
_CAMPOS_PADRAO = {"cpf", "nome", "situacao"}

# ---------------------------------------------------------------------------
# Executa consulta (antes do sidebar para que session_state esteja atualizado)
# ---------------------------------------------------------------------------

st.title("🔍 Consulta CPF")
st.caption("Rotação automática de provedores: API_CPF → CPF_Hub → Consultar.io")

texto = st.text_area(
    "CPFs",
    placeholder=(
        "111.444.777-35\n"
        "529.982.247-25\n"
        "11144477735|1990-01-15  ← com data de nascimento (Consultar.io)"
    ),
    height=170,
    label_visibility="collapsed",
)

col_btn, col_hint = st.columns([1, 5])
consultar = col_btn.button("🔎 Consultar", type="primary", use_container_width=True)
col_hint.caption("Use `CPF|YYYY-MM-DD` para incluir data de nascimento (necessário para Consultar.io).")

if consultar:
    cpfs, nascimentos = extrair_cpfs_com_nascimento(texto)

    if not cpfs:
        st.warning("⚠️ Informe ao menos um CPF com 11 dígitos.")
    else:
        invalidos = [c for c in cpfs if not validar_cpf(c)]
        if invalidos:
            st.error(f"CPFs inválidos (dígito verificador): {', '.join(invalidos)}")
        else:
            with st.spinner(f"Consultando {len(cpfs)} CPF(s)..."):
                try:
                    resultados = consultar_varios(cpfs, nascimentos)
                    st.session_state["resultados"] = resultados
                    st.session_state["campos_disponíveis"] = campos_disponiveis(resultados)

                    # Inicializa seleção com campos padrão presentes
                    if "campos_sel" not in st.session_state:
                        st.session_state["campos_sel"] = [
                            c for c in st.session_state["campos_disponíveis"]
                            if c in _CAMPOS_PADRAO
                        ]
                except ValueError as exc:
                    st.error(f"⚙️ Configuração: {exc}")

# ---------------------------------------------------------------------------
# Sidebar — créditos + filtro de campos
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📊 Créditos disponíveis")

    uso = status_uso()
    algum_configurado = any(info["tem_chave"] for info in uso.values())

    if not algum_configurado:
        st.warning("Nenhuma chave de API configurada. Preencha os Secrets da aplicação.")
    else:
        for info in uso.values():
            if not info["tem_chave"]:
                continue
            restante = info["restante"]
            maximo = info["maximo"]
            tipo = _TIPO_LABEL[info["tipo"]]
            pct = restante / maximo if maximo else 0.0
            cor_delta = "normal" if restante > maximo * 0.2 else "inverse"

            st.metric(
                label=info["label"],
                value=f"{restante} restantes",
                delta=f"/{maximo} {tipo}",
                delta_color=cor_delta,
            )
            st.progress(pct)

    st.divider()

    # Filtro de campos
    st.header("🎛️ Campos visíveis")

    todos_campos = st.session_state.get("campos_disponíveis", list(_CAMPOS_PADRAO))
    rotulos_map = {c: rotulo_campo(c) for c in todos_campos}

    campos_sel = st.multiselect(
        "Selecione as colunas",
        options=todos_campos,
        default=st.session_state.get("campos_sel", [c for c in todos_campos if c in _CAMPOS_PADRAO]),
        format_func=lambda c: rotulos_map.get(c, c),
    )
    st.session_state["campos_sel"] = campos_sel

    if st.button("Apenas nome"):
        st.session_state["campos_sel"] = [c for c in todos_campos if c in {"cpf", "nome"}]
        st.rerun()

    if st.button("Todos os campos"):
        st.session_state["campos_sel"] = todos_campos
        st.rerun()

# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------

resultados: list[dict] = st.session_state.get("resultados", [])

if resultados:
    esgotados = [r.get("cpf", "") for r in resultados if r.get("erro") == MSG_ESGOTADO]
    if esgotados:
        st.error(
            "⛔ **Créditos esgotados!** Todos os provedores atingiram o limite.\n\n"
            "- API_CPF: 100 consultas/dia  \n"
            "- CPF_Hub: 50 consultas/mês  \n"
            "- Consultar.io: 25 consultas no total"
        )

    cols_exibir = [c for c in (st.session_state.get("campos_sel") or []) if c != ""]

    if not cols_exibir:
        st.info("Selecione ao menos um campo no painel lateral.")
    else:
        df_full = pd.DataFrame(resultados)
        cols_presentes = [c for c in cols_exibir if c in df_full.columns]

        if cols_presentes:
            df_show = df_full[cols_presentes].rename(
                columns={c: rotulo_campo(c) for c in cols_presentes}
            ).fillna("")

            # Destaca linhas com erro
            def _estilizar(row: pd.Series) -> list[str]:
                tem_erro = any(
                    str(v).strip() and str(v) != MSG_ESGOTADO
                    for col, v in row.items()
                    if "erro" in col.lower() or "Erro" in col
                )
                esg = any(str(v) == MSG_ESGOTADO for v in row)
                if esg:
                    return ["background-color: #fde8e8"] * len(row)
                if tem_erro:
                    return ["background-color: #fff3cd"] * len(row)
                return [""] * len(row)

            st.dataframe(
                df_show.style.apply(_estilizar, axis=1),
                use_container_width=True,
                hide_index=True,
            )

            csv = df_show.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Baixar CSV",
                data=csv,
                file_name="consulta_cpf.csv",
                mime="text/csv",
            )

            st.caption(f"{len(resultados)} CPF(s) consultado(s).")
