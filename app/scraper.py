"""
Coleta de dados do Sistema Corban via API HTTP.

Fluxo validado:
1. POST /index.php/auth/login (com usuario + senha) -> PHPSESSID
2. POST /index.php/receptivo/consultar-cliente (cpf + nb) -> pega CSRF token
3. POST /index.php/receptivo/consultar-cliente (nb + csrf) -> JWT com cliente_nb
4. POST services.../consulta-inss/consultar (Bearer JWT) -> dados completos
"""

import os
import re
import json
import logging
import base64
import httpx

from app.models import DadosBeneficio, Emprestimo, DadosCliente

logger = logging.getLogger(__name__)

GESTAO_BASE = "https://gestao.sistemacorban.com.br"
SERVICES_BASE = "https://services.sistemacorban.com.br"

CORBAN_USER = os.getenv("CORBAN_USER", "")
CORBAN_PASS = os.getenv("CORBAN_PASS", "")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


async def _login(client: httpx.AsyncClient) -> bool:
    """Login no Sistema Corban. Retorna True se ok."""
    logger.info("Fazendo login no Sistema Corban")
    await client.get(f"{GESTAO_BASE}/index.php/auth/login", headers=BROWSER_HEADERS)
    r = await client.post(
        f"{GESTAO_BASE}/index.php/auth/login",
        data={"exten": CORBAN_USER, "password": CORBAN_PASS},
        headers={**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=True,
    )
    if r.status_code == 200 and "PHPSESSID" in {c.name for c in client.cookies.jar}:
        logger.info("Login OK")
        return True
    logger.error(f"Login falhou: status {r.status_code}")
    return False


async def _obter_jwt(client: httpx.AsyncClient, cpf: str, nb: str) -> str:
    """
    Obtem JWT com cliente_nb para consulta INSS.
    Requer 2 POSTs: primeiro pega CSRF, segundo pega JWT.
    """
    # Primeiro POST: pegar CSRF token
    r = await client.post(
        f"{GESTAO_BASE}/index.php/receptivo/consultar-cliente",
        data={"beneficio": nb, "cpfcli": cpf},
        headers={**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=True,
    )
    csrf_match = re.search(
        r'name=["\']token_verification["\'][^>]*value=["\']([^"\' ]+)', r.text
    )
    if not csrf_match:
        logger.error("CSRF token nao encontrado")
        return ""

    csrf = csrf_match.group(1)
    logger.info(f"CSRF token obtido")

    # Segundo POST: com CSRF -> JWT com cliente_nb
    r = await client.post(
        f"{GESTAO_BASE}/index.php/receptivo/consultar-cliente",
        data={"beneficio": nb, "cpfcli3": "", "token_verification": csrf},
        headers={**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=True,
    )

    # Extrair JWT que tem cliente_nb
    jwts = re.findall(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", r.text)
    for jwt in jwts:
        try:
            payload = jwt.split(".")[1] + "===="
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            if "cliente_nb" in decoded:
                logger.info(f"JWT com cliente_nb obtido")
                return jwt
        except Exception:
            continue

    logger.error("JWT com cliente_nb nao encontrado")
    return ""


async def _buscar_beneficios(client: httpx.AsyncClient, cpf: str) -> list[str]:
    """
    Busca os numeros de beneficio (NB) de um CPF.
    Retorna lista de NBs (10 digitos).
    """
    r = await client.post(
        f"{GESTAO_BASE}/index.php/receptivo/consultar-cliente",
        data={"beneficio": "", "cpfcli": cpf},
        headers={**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=True,
    )
    # Procurar NBs (10 digitos) no contexto de selecionarBeneficio
    nbs = re.findall(r"selecionarBeneficio\(['\"]?(\d{10})['\"]?\)", r.text)
    if nbs:
        logger.info(f"Beneficios encontrados: {nbs}")
        return list(set(nbs))

    # Fallback: procurar NBs genericos
    nbs = re.findall(r"(\d{10})", r.text)
    # Filtrar apenas NBs plausíveis (nao telefones, etc.)
    nbs_filtrados = [nb for nb in set(nbs) if nb[0] in "0123456789" and not nb.startswith("55")]
    if nbs_filtrados:
        logger.info(f"Beneficios (fallback): {nbs_filtrados[:5]}")
        return nbs_filtrados[:5]

    return []


async def _consultar_inss(client: httpx.AsyncClient, jwt: str) -> dict | None:
    """Consulta API INSS com JWT Bearer."""
    r = await client.post(
        f"{SERVICES_BASE}/consulta-inss/consultar",
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": GESTAO_BASE,
        },
    )
    if r.status_code == 200:
        data = r.json()
        if data.get("Beneficiario", {}).get("Nome"):
            return data
    logger.error(f"Consulta INSS falhou: {r.status_code}")
    return None


def _parse_consulta(data: dict) -> tuple[DadosBeneficio, list[Emprestimo]]:
    """Parseia o JSON da consulta INSS para modelos internos."""
    ben_data = data.get("Beneficiario", {})
    especie_raw = ben_data.get("Especie", "")

    beneficio = DadosBeneficio(
        idade=ben_data.get("Idade"),
        nascimento=ben_data.get("DataNascimento"),
        codigo_beneficio=especie_raw.split(" - ")[0].strip() if especie_raw else None,
        especie=especie_raw,
    )

    emprestimos = []
    for emp_data in data.get("Emprestimos", {}).get("Emprestimo", []):
        if emp_data.get("Tipo") != "Emprestimo":
            continue

        try:
            parcela = float(emp_data.get("Valor", 0))
        except (ValueError, TypeError):
            parcela = 0

        try:
            saldo_str = str(emp_data.get("Quitacao", "0"))
            saldo = float(saldo_str) if saldo_str != "NaN" else 0
        except (ValueError, TypeError):
            saldo = 0

        try:
            taxa = float(emp_data.get("Taxa", 0))
        except (ValueError, TypeError):
            taxa = 0

        prazo = emp_data.get("Prazo", 0) or 0
        restantes = emp_data.get("ParcelasRestantes", 0) or 0
        parcelas_pagas = max(0, prazo - restantes)

        emprestimos.append(Emprestimo(
            codigo_banco=str(emp_data.get("Banco", "")).zfill(3),
            nome_banco=f"Banco {str(emp_data.get('Banco', '')).zfill(3)}",
            taxa_juros=taxa,
            saldo_devedor=saldo,
            parcelas_pagas=parcelas_pagas,
            valor_parcela=parcela,
        ))

    return beneficio, emprestimos


async def coletar_dados_cliente_async(cpf: str) -> DadosCliente:
    """Fluxo completo: login -> busca beneficios -> consulta INSS."""
    cpf_limpo = cpf.replace(".", "").replace("-", "").replace(" ", "")

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            # 1. Login
            if not await _login(client):
                return DadosCliente(cpf=cpf_limpo, erro="Falha no login do Sistema Corban")

            # 2. Buscar beneficios
            nbs = await _buscar_beneficios(client, cpf_limpo)
            if not nbs:
                return DadosCliente(cpf=cpf_limpo, erro="Nenhum beneficio encontrado para este CPF")

            # 3. Para cada beneficio, obter JWT e consultar
            # (normalmente 1 beneficio, mas pode ter mais)
            todos_emprestimos = []
            beneficio_final = None

            for nb in nbs[:3]:  # Max 3 beneficios
                jwt = await _obter_jwt(client, cpf_limpo, nb)
                if not jwt:
                    continue

                data = await _consultar_inss(client, jwt)
                if not data:
                    continue

                beneficio_info, emprestimos = _parse_consulta(data)
                if not beneficio_final:
                    beneficio_final = beneficio_info
                todos_emprestimos.extend(emprestimos)

            logger.info(
                f"Dados coletados: {len(todos_emprestimos)} emprestimos, "
                f"idade={beneficio_final.idade if beneficio_final else '?'}"
            )

            return DadosCliente(
                cpf=cpf_limpo,
                beneficio=beneficio_final,
                emprestimos=todos_emprestimos,
            )

    except Exception as e:
        logger.exception("Erro ao coletar dados via API")
        return DadosCliente(cpf=cpf_limpo, erro=str(e))
