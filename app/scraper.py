"""
Coleta de dados do Sistema Corban via API HTTP.

Fluxo:
1. Login no gestao.sistemacorban.com.br → obter PHPSESSID
2. GET /index.php/index/verificarlogin → confirmar sessao
3. POST services.sistemacorban.com.br/consulta-inss/consultar → dados completos

Sem Selenium, sem Chrome, sem Cloudflare.
"""

import os
import logging
import httpx

from app.models import DadosBeneficio, Emprestimo, DadosCliente

logger = logging.getLogger(__name__)

GESTAO_BASE = "https://gestao.sistemacorban.com.br"
SERVICES_BASE = "https://services.sistemacorban.com.br"
LOGIN_URL = f"{GESTAO_BASE}/index.php/auth/login"

CORBAN_USER = os.getenv("CORBAN_USER", "")
CORBAN_PASS = os.getenv("CORBAN_PASS", "")
AGENCIA = os.getenv("CORBAN_AGENCIA", "25599")

# Headers que imitam um browser real
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Ch-Ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


async def _login(client: httpx.AsyncClient) -> str | None:
    """
    Faz login no Sistema Corban e retorna o token de sessao.
    O PHPSESSID e mantido automaticamente pelo client (cookies).
    """
    # 1. Acessar pagina de login (pegar cookies iniciais)
    logger.info("Acessando pagina de login")
    await client.get(LOGIN_URL, headers=BROWSER_HEADERS)

    # 2. POST login com credenciais
    login_data = {
        "exten": CORBAN_USER,
        "password": CORBAN_PASS,
    }
    logger.info("Enviando credenciais")
    resp = await client.post(
        LOGIN_URL,
        data=login_data,
        headers={**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=True,
    )

    if resp.status_code != 200:
        logger.error(f"Login falhou: status {resp.status_code}")
        return None

    # 3. Verificar login
    logger.info("Verificando login")
    resp = await client.get(
        f"{GESTAO_BASE}/index.php/index/verificarlogin",
        headers={**BROWSER_HEADERS, "Referer": f"{GESTAO_BASE}/index.php/receptivo"},
    )

    if resp.status_code == 200:
        data = resp.json()
        token = data.get("token", "")
        if token:
            logger.info("Login confirmado")
            return token

    logger.error(f"Verificacao de login falhou: {resp.status_code}")
    return None


async def _consultar_inss(
    client: httpx.AsyncClient,
    cpf: str,
    bearer_token: str,
) -> dict | None:
    """
    Consulta dados do INSS via API services.sistemacorban.com.br.
    Retorna o JSON completo com beneficiario, emprestimos, etc.
    """
    headers = {
        **BROWSER_HEADERS,
        "Authorization": f"Bearer {bearer_token}",
        "Origin": GESTAO_BASE,
        "Referer": f"{GESTAO_BASE}/index.php/receptivo",
        "Sec-Fetch-Site": "same-site",
    }

    logger.info("Consultando INSS via API")
    resp = await client.post(
        f"{SERVICES_BASE}/consulta-inss/consultar",
        headers=headers,
    )

    if resp.status_code == 200:
        return resp.json()

    logger.error(f"Consulta INSS falhou: status {resp.status_code}")
    return None


async def _buscar_e_consultar(
    client: httpx.AsyncClient,
    cpf: str,
) -> dict | None:
    """
    Busca CPF no receptivo e inicia a consulta INSS.
    Tenta diferentes abordagens para obter os dados.
    """
    # Primeiro, salvar consulta do cliente (como o frontend faz)
    headers = {
        **BROWSER_HEADERS,
        "Referer": f"{GESTAO_BASE}/index.php/receptivo",
    }

    # Buscar via consultar com agencia
    logger.info(f"Buscando CPF via consultar")
    resp = await client.get(
        f"{GESTAO_BASE}/index.php/receptivo/consultar",
        params={"agencia": AGENCIA},
        headers=headers,
    )

    # Salvar consulta do cliente
    await client.post(
        f"{GESTAO_BASE}/index.php/receptivo/salvar-consulta-cliente",
        data={"cpf": cpf, "agencia": AGENCIA},
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )

    # Tentar consulta INSS com o token JWT
    # O JWT pode ser gerado apos a busca pelo CPF
    # Tentamos obter via buscar-propostas ou consulta direta
    resp = await client.post(
        f"{GESTAO_BASE}/index.php/esteira-consultas/buscar-propostas",
        data={"cpf": cpf},
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )

    if resp.status_code == 200:
        try:
            data = resp.json()
            if data:
                logger.info("Dados obtidos via buscar-propostas")
                return data
        except Exception:
            pass

    return None


def _parse_consulta(data: dict) -> tuple[DadosBeneficio, list[Emprestimo]]:
    """
    Parseia o JSON da consulta INSS para os modelos internos.
    """
    ben_data = data.get("Beneficiario", {})
    beneficio = DadosBeneficio(
        idade=ben_data.get("Idade"),
        nascimento=ben_data.get("DataNascimento"),
        codigo_beneficio=str(ben_data.get("Especie", "")).split(" - ")[0].strip() if ben_data.get("Especie") else None,
        especie=ben_data.get("Especie"),
    )

    emprestimos = []
    emp_list = data.get("Emprestimos", {}).get("Emprestimo", [])

    for emp_data in emp_list:
        tipo = emp_data.get("Tipo", "")
        # Ignorar cartoes e RCC, apenas emprestimos consignados
        if tipo not in ("Emprestimo",):
            continue

        parcela = emp_data.get("Valor")
        quitacao = emp_data.get("Quitacao")
        prazo = emp_data.get("Prazo", 0)
        restantes = emp_data.get("ParcelasRestantes", 0)

        # Converter valores
        try:
            parcela = float(parcela) if parcela else 0
        except (ValueError, TypeError):
            parcela = 0

        try:
            saldo = float(quitacao) if quitacao and str(quitacao) != "NaN" else 0
        except (ValueError, TypeError):
            saldo = 0

        try:
            taxa = float(emp_data.get("Taxa", 0))
        except (ValueError, TypeError):
            taxa = 0

        parcelas_pagas = max(0, prazo - restantes)

        codigo_banco = str(emp_data.get("Banco", "")).zfill(3)

        emp = Emprestimo(
            codigo_banco=codigo_banco,
            nome_banco=f"Banco {codigo_banco}",
            taxa_juros=taxa,
            saldo_devedor=saldo,
            parcelas_pagas=parcelas_pagas,
            valor_parcela=parcela,
        )
        emprestimos.append(emp)

    return beneficio, emprestimos


async def coletar_dados_cliente_async(cpf: str) -> DadosCliente:
    """
    Fluxo completo async: login -> busca CPF -> coleta dados via API HTTP.
    """
    cpf_limpo = cpf.replace(".", "").replace("-", "").replace(" ", "")

    try:
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            verify=True,
        ) as client:
            # 1. Login
            token = await _login(client)
            if not token:
                return DadosCliente(cpf=cpf_limpo, erro="Falha no login do Sistema Corban")

            # 2. Tentar buscar dados via API
            # Primeiro tenta buscar-propostas pelo gestao
            data = await _buscar_e_consultar(client, cpf_limpo)

            if not data or "Beneficiario" not in (data or {}):
                # Se nao conseguiu, tenta consulta INSS direta
                # Para isso, precisamos do JWT Bearer token
                # O token do verificarlogin pode nao ser JWT
                # Tentamos consultar mesmo assim
                data = await _consultar_inss(client, cpf_limpo, token)

            if not data or "Beneficiario" not in (data or {}):
                return DadosCliente(
                    cpf=cpf_limpo,
                    erro="Nao foi possivel obter dados do INSS para este CPF",
                )

            # 3. Parsear dados
            beneficio, emprestimos = _parse_consulta(data)

            logger.info(
                f"Dados coletados via API: {len(emprestimos)} emprestimos, "
                f"idade={beneficio.idade}, especie={beneficio.codigo_beneficio}"
            )

            return DadosCliente(
                cpf=cpf_limpo,
                beneficio=beneficio,
                emprestimos=emprestimos,
            )

    except Exception as e:
        logger.exception("Erro ao coletar dados via API")
        return DadosCliente(cpf=cpf_limpo, erro=str(e))


def coletar_dados_cliente(cpf: str) -> DadosCliente:
    """
    Wrapper sincrono para compatibilidade com asyncio.to_thread().
    """
    import asyncio
    return asyncio.run(coletar_dados_cliente_async(cpf))
