"""
Coleta de dados do Sistema Corban via Supabase Edge Function proxy.

A Edge Function (floracred-corban) faz login no gestao.sistemacorban.com.br,
obtem JWT e chama services.sistemacorban.com.br/consulta-inss/consultar.
Isso contorna o bloqueio Cloudflare em IPs de datacenter.
"""

import os
import logging
import httpx

from app.models import DadosBeneficio, Emprestimo, DadosCliente

logger = logging.getLogger(__name__)

CORBAN_EDGE_FN = os.getenv(
    "CORBAN_EDGE_FN",
    "https://mlntilbkenjjejksevdx.supabase.co/functions/v1/floracred-corban",
)


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


async def coletar_dados_cliente_async(cpf: str, nb: str = "") -> DadosCliente:
    """
    Chama a Edge Function no Supabase para coletar dados do INSS.
    A Edge Function faz: login -> JWT -> consulta-inss.
    """
    cpf_limpo = cpf.replace(".", "").replace("-", "").replace(" ", "")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            logger.info(f"Chamando Edge Function para CPF")

            payload = {"cpf": cpf_limpo}
            if nb:
                payload["nb"] = nb

            r = await client.post(
                CORBAN_EDGE_FN,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if r.status_code != 200:
                erro = r.json().get("error", f"Status {r.status_code}")
                logger.error(f"Edge Function erro: {erro}")
                return DadosCliente(cpf=cpf_limpo, erro=erro)

            data = r.json()

            if "error" in data:
                return DadosCliente(cpf=cpf_limpo, erro=data["error"])

            beneficio, emprestimos = _parse_consulta(data)

            logger.info(
                f"Dados coletados: {len(emprestimos)} emprestimos, "
                f"idade={beneficio.idade}"
            )

            return DadosCliente(
                cpf=cpf_limpo,
                beneficio=beneficio,
                emprestimos=emprestimos,
            )

    except Exception as e:
        logger.exception("Erro ao chamar Edge Function")
        return DadosCliente(cpf=cpf_limpo, erro=str(e))
