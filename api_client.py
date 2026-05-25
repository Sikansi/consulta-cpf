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

_CAMPOS_BINARIOS = {
    "comprovantePdf", "situacaoComprovantePdf", "situacaoComprovantePdf",
    "pdf", "base64", "comprovantePdfBase64", "situacaoComprovantePdfBase64",
}

# Aliases: campo_padrao → possíveis nomes que a API pode retornar
_ALIASES: dict[str, list[str]] = {
    "cpf":        ["cpf", "CPF", "documento", "nr_cpf"],
    "nome":       ["nome", "name", "NomePF", "nome_completo", "NomeCompleto"],
    "nomeSocial": ["nomeSocial", "nome_social", "NomeSocial"],
    "nascimento": ["nascimento", "data_nascimento", "DataNascimento", "dt_nascimento"],
    "mae":        ["mae", "nome_mae", "NomeMae", "nomeMae", "mae_nome"],
    "genero":     ["genero", "sexo", "gender", "Sexo"],
    "situacao":   ["situacao", "situacaoCadastral", "SituacaoCadastral",
                   "status_receita", "situacao_cadastral"],
    "cidade":     ["cidade", "municipio", "Municipio", "city"],
    "uf":         ["uf", "UF", "estado", "state", "sg_uf"],
    "endereco":   ["endereco", "logradouro", "address", "Logradouro"],
    "cep":        ["cep", "CEP"],
    "bairro":     ["bairro", "neighborhood", "Bairro"],
    "telefones":  ["telefones", "telefone", "phone", "Telefone"],
    "emails":     ["emails", "email", "Email"],
}


def _valor_escalar(v: Any) -> str:
    if isinstance(v, list):
        partes = [str(i) for i in v if i not in (None, "")]
        return ", ".join(partes)
    if isinstance(v, dict):
        return str(v)
    return "" if v is None else str(v)


def _normalizar(dados: dict[str, Any]) -> dict[str, Any]:
    # 1. Copia todos os campos não-binários e não-dict como estão
    r: dict[str, Any] = {}
    for chave, valor in dados.items():
        if chave in _CAMPOS_BINARIOS:
            continue
        if isinstance(valor, bytes):
            continue
        if isinstance(valor, dict):
            # achata um nível de dicts simples (ex: {"nome": "X"})
            for sub_k, sub_v in valor.items():
                if not isinstance(sub_v, (dict, bytes)) and sub_k not in _CAMPOS_BINARIOS:
                    r[f"{chave}.{sub_k}"] = _valor_escalar(sub_v)
        elif isinstance(valor, list) and valor and isinstance(valor[0], dict):
            r[chave] = " | ".join(
                ", ".join(f"{k}={v}" for k, v in item.items()
                          if k not in _CAMPOS_BINARIOS and not isinstance(v, (dict, list, bytes)))
                for item in valor
            )
        else:
            r[chave] = _valor_escalar(valor)

    # 2. Adiciona aliases normalizados se o campo padrão não existir diretamente
    for campo_padrao, nomes_api in _ALIASES.items():
        if campo_padrao not in r:
            for nome in nomes_api:
                if nome in r and r[nome] not in ("", None):
                    r[campo_padrao] = r[nome]
                    break

    # Remove strings vazias
    return {k: v for k, v in r.items() if v not in (None, "")}


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
