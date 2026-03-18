"""
Integracao com GoHighLevel (GHL) via PIT (Private Integration Token).

Fluxo:
1. Atualiza custom fields do contato com resultado da simulacao
2. Seta "Possibilidade Portabilidade" = "Sim" ou "Nao"
3. A automacao na GHL e disparada pelo trigger do campo alterado
"""

import os
import logging
import httpx

from app.models import ResultadoCliente

logger = logging.getLogger(__name__)

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_KEY = os.getenv("GHL_API_KEY", "")  # PIT Token
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "HKZiiyzTHht8LVylD97r")

# Custom field IDs — Floracred
CF_POSSIBILIDADE = "Fgf8wJh0LbQ0ZLCJDQYJ"       # Possibilidade Portabilidade (RADIO: Sim/Nao)
CF_VALOR_LIBERADO_TOTAL = "nYm9XkV76FsTiNRcJJPn"  # Valor Liberado Total (TEXT)
CF_RESUMO_SIMULACAO = "mQIVywbqULMxSb4RhvZx"      # Resumo Simulacao (LARGE_TEXT)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GHL_API_KEY}",
        "Content-Type": "application/json",
        "Version": "2021-07-28",
    }


async def atualizar_contato_simulacao(
    contact_id: str,
    resultado: ResultadoCliente,
) -> dict | None:
    """
    Atualiza o contato na GHL com os resultados da simulacao.
    Seta Possibilidade = Sim/Nao, valor total, e resumo por parcela.
    """
    if not GHL_API_KEY or not contact_id:
        logger.warning("GHL_API_KEY ou contact_id nao configurado")
        return None

    tem_simulacao = len(resultado.simulacoes_por_emprestimo) > 0

    custom_fields = [
        {
            "id": CF_POSSIBILIDADE,
            "value": "Sim" if tem_simulacao else "Não",
        },
        {
            "id": CF_VALOR_LIBERADO_TOTAL,
            "value": f"R$ {resultado.valor_liberado_total:,.2f}" if tem_simulacao else "R$ 0,00",
        },
        {
            "id": CF_RESUMO_SIMULACAO,
            "value": resultado.resumo_texto if tem_simulacao else "Nenhuma portabilidade disponivel para este cliente.",
        },
    ]

    payload = {"customFields": custom_fields}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{GHL_API_BASE}/contacts/{contact_id}",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            logger.info(f"Contato {contact_id} atualizado: Possibilidade={'Sim' if tem_simulacao else 'Nao'}")
            return resp.json()
    except Exception as e:
        logger.error(f"Erro ao atualizar contato {contact_id}: {e}")
        return None


async def adicionar_tag(contact_id: str, tags: list[str]) -> dict | None:
    """Adiciona tags ao contato."""
    if not GHL_API_KEY or not contact_id:
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GHL_API_BASE}/contacts/{contact_id}/tags",
                headers=_headers(),
                json={"tags": tags},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Erro ao adicionar tag: {e}")
        return None


async def buscar_contato_por_cpf(cpf: str) -> dict | None:
    """Busca contato na GHL pelo CPF (custom field)."""
    if not GHL_API_KEY:
        return None

    # Limpar CPF para busca
    cpf_limpo = cpf.replace(".", "").replace("-", "").replace(" ", "")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GHL_API_BASE}/contacts/",
                headers=_headers(),
                params={
                    "locationId": GHL_LOCATION_ID,
                    "query": cpf_limpo,
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            contatos = data.get("contacts", [])
            if contatos:
                return contatos[0]
            return None
    except Exception as e:
        logger.error(f"Erro ao buscar contato por CPF: {e}")
        return None
