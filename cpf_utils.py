import re
from typing import Optional


def limpar_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf or "")


def validar_cpf(cpf: str) -> bool:
    numeros = limpar_cpf(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False

    def digito(base: str, peso: int) -> str:
        total = sum(int(n) * p for n, p in zip(base, range(peso, 1, -1)))
        resto = (total * 10) % 11
        return "0" if resto == 10 else str(resto)

    return numeros[-2:] == digito(numeros[:9], 10) + digito(numeros[:10], 11)


def formatar_cpf(cpf: str) -> str:
    numeros = limpar_cpf(cpf)
    if len(numeros) != 11:
        return cpf
    return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"


def _validar_nascimento(texto: str) -> Optional[str]:
    """Valida e normaliza data no formato YYYY-MM-DD ou DD/MM/YYYY."""
    texto = texto.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", texto):
        return texto
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", texto)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def extrair_cpfs(texto: str) -> list[str]:
    """Extrai só CPFs (sem nascimento). Suporta CPF|DATA."""
    cpfs, _ = extrair_cpfs_com_nascimento(texto)
    return cpfs


def extrair_cpfs_com_nascimento(texto: str) -> tuple[list[str], dict[str, str]]:
    """
    Extrai CPFs e datas de nascimento opcionais.

    Formatos aceitos por linha/item:
      - 111.444.777-35
      - 11144477735|1990-01-15
      - 111.444.777-35|15/01/1990
    Separadores entre itens: newline, vírgula, ponto-e-vírgula.
    """
    cpfs: list[str] = []
    nascimentos: dict[str, str] = {}
    vistos: set[str] = set()

    for parte in re.split(r"[\n,;]+", texto.strip()):
        parte = parte.strip()
        if not parte:
            continue

        nascimento: Optional[str] = None
        if "|" in parte:
            cpf_raw, _, nasc_raw = parte.partition("|")
            nascimento = _validar_nascimento(nasc_raw)
        else:
            cpf_raw = parte

        cpf = limpar_cpf(cpf_raw)
        if len(cpf) != 11 or cpf in vistos:
            continue

        vistos.add(cpf)
        cpfs.append(cpf)
        if nascimento:
            nascimentos[cpf] = nascimento

    return cpfs, nascimentos


def rotulo_campo(campo: str) -> str:
    rotulos = {
        "cpf": "CPF",
        "nome": "Nome",
        "nomeSocial": "Nome social",
        "nascimento": "Data de nascimento",
        "mae": "Nome da mãe",
        "genero": "Gênero",
        "situacao": "Situação cadastral",
        "situacaoDigito": "Situação (código)",
        "situacaoMotivo": "Motivo da situação",
        "situacaoAnoObito": "Ano óbito",
        "situacaoInscricao": "Data inscrição",
        "situacaoComprovante": "Comprovante",
        "situacaoComprovanteEmissao": "Emissão comprovante",
        "endereco": "Endereço",
        "numero": "Número",
        "complemento": "Complemento",
        "bairro": "Bairro",
        "cep": "CEP",
        "cidade": "Cidade",
        "uf": "UF",
        "ibge": "Código IBGE",
        "telefones": "Telefones",
        "whatsapp": "WhatsApp",
        "emails": "E-mails",
        "enderecos": "Histórico de endereços",
        "pacoteUsado": "Pacote usado",
        "saldo": "Saldo restante",
        "consultaID": "ID da consulta",
        "delay": "Tempo (s)",
        "erro": "Erro",
        "erroCodigo": "Código do erro",
    }
    if campo in rotulos:
        return rotulos[campo]
    return campo.replace(".", " · ").replace("[", " ").replace("]", "")
