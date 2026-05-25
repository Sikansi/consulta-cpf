import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

from cpf_utils import formatar_cpf, limpar_cpf

_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env")

TIMEOUT_SEG = 60
ARQUIVO_USO = _BASE_DIR / "usage.json"

# Ordem de uso: mais créditos/dia primeiro → preserva os mais escassos
PROVEDORES = ["apicpf", "cpfhub", "consultario"]

LIMITES: dict[str, dict] = {
    "apicpf":      {"tipo": "diario",  "max": 100, "label": "API_CPF"},
    "cpfhub":      {"tipo": "mensal",  "max": 50,  "label": "CPF_Hub"},
    "consultario": {"tipo": "total",   "max": 25,  "label": "Consultar.io"},
}

CAMPOS_PRIORITARIOS = [
    "cpf", "nome", "nomeSocial", "nascimento", "mae", "genero",
    "situacao", "cidade", "uf", "endereco", "cep", "bairro",
    "telefones", "emails", "erro",
]

MSG_ESGOTADO = "__TODOS_ESGOTADOS__"


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

def _config(chave: str) -> str:
    return os.getenv(chave, "").strip()


def _chave_provedor(provedor: str) -> str:
    return _config({"apicpf": "APICPF_KEY", "cpfhub": "CPFHUB_KEY", "consultario": "CONSULTARIO_TOKEN"}[provedor])


# ---------------------------------------------------------------------------
# Persistência de uso
# ---------------------------------------------------------------------------

def _carregar_uso() -> dict:
    if ARQUIVO_USO.exists():
        try:
            return json.loads(ARQUIVO_USO.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _salvar_uso(uso: dict) -> None:
    ARQUIVO_USO.write_text(json.dumps(uso, indent=2, ensure_ascii=False), encoding="utf-8")


def _uso_atual(provedor: str, uso: dict) -> int:
    entrada = uso.get(provedor, {})
    tipo = LIMITES[provedor]["tipo"]
    if tipo == "diario":
        return entrada.get("uso", 0) if entrada.get("data") == date.today().isoformat() else 0
    if tipo == "mensal":
        return entrada.get("uso", 0) if entrada.get("mes") == date.today().strftime("%Y-%m") else 0
    return entrada.get("uso", 0)  # total


def _incrementar(provedor: str, uso: dict) -> None:
    tipo = LIMITES[provedor]["tipo"]
    entrada = uso.get(provedor, {})
    if tipo == "diario":
        hoje = date.today().isoformat()
        if entrada.get("data") != hoje:
            entrada = {"data": hoje, "uso": 0}
        entrada["uso"] = entrada.get("uso", 0) + 1
    elif tipo == "mensal":
        mes = date.today().strftime("%Y-%m")
        if entrada.get("mes") != mes:
            entrada = {"mes": mes, "uso": 0}
        entrada["uso"] = entrada.get("uso", 0) + 1
    else:
        entrada["uso"] = entrada.get("uso", 0) + 1
    uso[provedor] = entrada


# ---------------------------------------------------------------------------
# Status público (usado pela GUI)
# ---------------------------------------------------------------------------

def status_uso() -> dict[str, dict]:
    uso = _carregar_uso()
    resultado = {}
    for prov in PROVEDORES:
        usado = _uso_atual(prov, uso)
        maximo = LIMITES[prov]["max"]
        resultado[prov] = {
            "label":     LIMITES[prov]["label"],
            "tipo":      LIMITES[prov]["tipo"],
            "usado":     usado,
            "maximo":    maximo,
            "restante":  max(0, maximo - usado),
            "tem_chave": bool(_chave_provedor(prov)),
        }
    return resultado


def todos_esgotados() -> bool:
    uso = _carregar_uso()
    for prov in PROVEDORES:
        if _chave_provedor(prov) and _uso_atual(prov, uso) < LIMITES[prov]["max"]:
            return False
    return True


# ---------------------------------------------------------------------------
# Normalização de resposta
# ---------------------------------------------------------------------------

def _get_campo(dados: dict, *chaves: str) -> Any:
    for c in chaves:
        v = dados.get(c)
        if v not in (None, ""):
            return v
    return None


def _normalizar(dados: dict[str, Any]) -> dict[str, Any]:
    for campo_omitir in ("comprovantePdf", "situacaoComprovantePdf", "pdf", "base64"):
        dados.pop(campo_omitir, None)

    r: dict[str, Any] = {}
    r["cpf"]         = _get_campo(dados, "cpf", "CPF", "documento") or ""
    r["nome"]        = _get_campo(dados, "nome", "name", "NomePF") or ""
    r["nomeSocial"]  = _get_campo(dados, "nomeSocial", "nome_social") or ""
    r["nascimento"]  = _get_campo(dados, "nascimento", "data_nascimento", "DataNascimento") or ""
    r["mae"]         = _get_campo(dados, "mae", "nome_mae", "NomeMae", "nomeMae") or ""
    r["genero"]      = _get_campo(dados, "genero", "sexo", "gender") or ""
    r["situacao"]    = _get_campo(dados, "situacao", "status_receita", "SituacaoCadastral", "situacao_cadastral") or ""
    r["cidade"]      = _get_campo(dados, "cidade", "municipio", "Municipio", "city") or ""
    r["uf"]          = _get_campo(dados, "uf", "estado", "UF", "state") or ""
    r["endereco"]    = _get_campo(dados, "endereco", "logradouro", "address") or ""
    r["cep"]         = _get_campo(dados, "cep", "CEP") or ""
    r["bairro"]      = _get_campo(dados, "bairro", "neighborhood") or ""
    r["telefones"]   = _get_campo(dados, "telefones", "telefone", "phone") or ""
    r["emails"]      = _get_campo(dados, "emails", "email") or ""

    for campo in ("telefones", "emails"):
        if isinstance(r[campo], list):
            r[campo] = ", ".join(str(v) for v in r[campo] if v)

    # Remove vazios
    r = {k: v for k, v in r.items() if v not in (None, "", [])}

    # Preserva campos extras não-binários que possam ser úteis
    campos_ja_mapeados = {
        "cpf", "CPF", "nome", "name", "NomePF", "nomeSocial", "nome_social",
        "nascimento", "data_nascimento", "DataNascimento", "mae", "nome_mae",
        "NomeMae", "nomeMae", "genero", "sexo", "gender", "situacao",
        "status_receita", "SituacaoCadastral", "situacao_cadastral", "cidade",
        "municipio", "Municipio", "city", "uf", "estado", "UF", "state",
        "endereco", "logradouro", "address", "cep", "CEP", "bairro",
        "neighborhood", "telefones", "telefone", "phone", "emails", "email",
        "status", "saldo", "delay", "consultaID", "pacoteUsado",
    }
    for chave, valor in dados.items():
        if chave not in campos_ja_mapeados and not isinstance(valor, (dict, list, bytes)):
            r[chave] = valor

    return r


# ---------------------------------------------------------------------------
# Chamadas por provedor
# ---------------------------------------------------------------------------

def _consultar_apicpf(cpf: str, uso: dict) -> dict[str, Any]:
    url = f"https://apicpf.com/api/consulta?cpf={cpf}"
    resp = requests.get(url, headers={"X-API-KEY": _chave_provedor("apicpf")}, timeout=TIMEOUT_SEG)
    resp.raise_for_status()
    dados = resp.json()
    _incrementar("apicpf", uso)
    return _normalizar(dados)


def _consultar_cpfhub(cpf: str, uso: dict) -> dict[str, Any]:
    url = f"https://api.cpfhub.io/cpf/{cpf}"
    resp = requests.get(url, headers={"x-api-key": _chave_provedor("cpfhub")}, timeout=TIMEOUT_SEG)
    resp.raise_for_status()
    dados = resp.json()
    _incrementar("cpfhub", uso)
    return _normalizar(dados)


def _consultar_consultario(cpf: str, nascimento: Optional[str], uso: dict) -> dict[str, Any]:
    if not nascimento:
        raise ValueError("Consultar.io requer data de nascimento (use CPF|YYYY-MM-DD na entrada)")
    url = (
        f"https://consultar.io/api/v1/cpf/consultar"
        f"?cpf={cpf}&data_nascimento={nascimento}"
    )
    resp = requests.get(
        url,
        headers={"Authorization": f"Token {_chave_provedor('consultario')}"},
        timeout=TIMEOUT_SEG,
    )
    resp.raise_for_status()
    dados = resp.json()
    _incrementar("consultario", uso)
    return _normalizar(dados)


# ---------------------------------------------------------------------------
# Consulta principal com rotação de provedores
# ---------------------------------------------------------------------------

def _disponivel(provedor: str, uso: dict) -> bool:
    return bool(_chave_provedor(provedor)) and _uso_atual(provedor, uso) < LIMITES[provedor]["max"]


def consultar_cpf(cpf: str, nascimento: Optional[str] = None) -> dict[str, Any]:
    uso = _carregar_uso()
    erros: list[str] = []

    tentativas = [
        ("apicpf",      lambda: _consultar_apicpf(cpf, uso)),
        ("cpfhub",      lambda: _consultar_cpfhub(cpf, uso)),
        ("consultario", lambda: _consultar_consultario(cpf, nascimento, uso)),
    ]

    for provedor, fn in tentativas:
        if not _disponivel(provedor, uso):
            continue
        try:
            resultado = fn()
            _salvar_uso(uso)
            if not resultado.get("cpf"):
                resultado["cpf"] = formatar_cpf(cpf)
            return resultado
        except ValueError as exc:
            erros.append(f"{LIMITES[provedor]['label']}: {exc}")
        except requests.HTTPError as exc:
            codigo = exc.response.status_code if exc.response is not None else "?"
            erros.append(f"{LIMITES[provedor]['label']}: HTTP {codigo}")
        except requests.RequestException as exc:
            erros.append(f"{LIMITES[provedor]['label']}: {exc}")

    _salvar_uso(uso)
    return {
        "cpf": formatar_cpf(cpf),
        "erro": MSG_ESGOTADO if not erros else "; ".join(erros),
    }


def consultar_varios(
    cpfs: list[str],
    nascimentos: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    if not cpfs:
        return []

    if not any(_chave_provedor(p) for p in PROVEDORES):
        raise ValueError(
            "Nenhuma chave configurada. Preencha o .env com "
            "APICPF_KEY, CPFHUB_KEY ou CONSULTARIO_TOKEN."
        )

    nascimentos = nascimentos or {}
    return [consultar_cpf(cpf, nascimentos.get(cpf)) for cpf in cpfs]


def campos_disponiveis(resultados: list[dict[str, Any]]) -> list[str]:
    campos: set[str] = set()
    for item in resultados:
        campos.update(item.keys())
    ordenados = [c for c in CAMPOS_PRIORITARIOS if c in campos]
    ordenados.extend(sorted(c for c in campos if c not in ordenados))
    return ordenados
