"""
Integracao com GoHighLevel (GHL) via API REST.

Funcionalidades:
- Criar/atualizar oportunidades com dados das simulacoes
- Atualizar custom fields do contato
- Enviar mensagem WhatsApp (via SMS custom provider)
"""

import os
import logging
import httpx

from app.models import ResultadoCliente, Simulacao

logger = logging.getLogger(__name__)

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_KEY = os.getenv("GHL_API_KEY", "")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "")
GHL_PIPELINE_ID = os.getenv("GHL_PIPELINE_ID", "")
GHL_STAGE_ID = os.getenv("GHL_STAGE_ID", "")  # Stage para simulacoes prontas

# Custom field keys (configurar na GHL)
CF_VALOR_LIBERADO = os.getenv("GHL_CF_VALOR_LIBERADO", "")
CF_BANCO_DESTINO = os.getenv("GHL_CF_BANCO_DESTINO", "")
CF_BANCO_ORIGEM = os.getenv("GHL_CF_BANCO_ORIGEM", "")
CF_PARCELA_ATUAL = os.getenv("GHL_CF_PARCELA_ATUAL", "")
CF_SALDO_DEVEDOR = os.getenv("GHL_CF_SALDO_DEVEDOR", "")
CF_TOTAL_FINANCIADO = os.getenv("GHL_CF_TOTAL_FINANCIADO", "")
CF_SIMULACAO_RESUMO = os.getenv("GHL_CF_SIMULACAO_RESUMO", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GHL_API_KEY}",
        "Content-Type": "application/json",
        "Version": "2021-07-28",
    }


async def criar_oportunidade(
    resultado: ResultadoCliente,
    pipeline_id: str | None = None,
    stage_id: str | None = None,
) -> dict | None:
    """
    Cria uma oportunidade na GHL com os dados da melhor simulacao.
    """
    if not GHL_API_KEY or not resultado.contact_id:
        logger.warning("GHL_API_KEY ou contact_id nao configurado, pulando criacao de oportunidade")
        return None

    melhor = resultado.melhor_simulacao
    if not melhor:
        logger.info(f"Nenhuma simulacao valida para CPF {resultado.cpf}")
        return None

    pipe = pipeline_id or GHL_PIPELINE_ID
    stage = stage_id or GHL_STAGE_ID

    # Montar custom fields
    custom_fields = []
    if CF_VALOR_LIBERADO:
        custom_fields.append({"id": CF_VALOR_LIBERADO, "value": str(melhor.valor_liberado)})
    if CF_BANCO_DESTINO:
        custom_fields.append({"id": CF_BANCO_DESTINO, "value": melhor.banco_destino})
    if CF_BANCO_ORIGEM:
        custom_fields.append({"id": CF_BANCO_ORIGEM, "value": melhor.banco_origem})
    if CF_PARCELA_ATUAL:
        custom_fields.append({"id": CF_PARCELA_ATUAL, "value": str(melhor.valor_parcela_atual)})
    if CF_SALDO_DEVEDOR:
        custom_fields.append({"id": CF_SALDO_DEVEDOR, "value": str(melhor.saldo_devedor)})
    if CF_TOTAL_FINANCIADO:
        custom_fields.append({"id": CF_TOTAL_FINANCIADO, "value": str(melhor.total_financiado)})
    if CF_SIMULACAO_RESUMO:
        resumo = formatar_resumo_simulacoes(resultado)
        custom_fields.append({"id": CF_SIMULACAO_RESUMO, "value": resumo})

    payload = {
        "pipelineId": pipe,
        "locationId": GHL_LOCATION_ID,
        "name": f"Portabilidade - {resultado.cpf}",
        "status": "open",
        "contactId": resultado.contact_id,
        "monetaryValue": melhor.valor_liberado,
    }

    if stage:
        payload["pipelineStageId"] = stage
    if custom_fields:
        payload["customFields"] = custom_fields

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GHL_API_BASE}/opportunities/",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            opp_id = data.get("opportunity", {}).get("id")
            logger.info(f"Oportunidade criada: {opp_id}")
            return data
    except Exception as e:
        logger.error(f"Erro ao criar oportunidade: {e}")
        return None


async def atualizar_contact_fields(
    contact_id: str,
    resultado: ResultadoCliente,
) -> dict | None:
    """
    Atualiza custom fields do contato com dados da simulacao.
    """
    if not GHL_API_KEY or not contact_id:
        return None

    melhor = resultado.melhor_simulacao
    if not melhor:
        return None

    custom_fields = []
    if CF_VALOR_LIBERADO:
        custom_fields.append({"id": CF_VALOR_LIBERADO, "value": str(melhor.valor_liberado)})
    if CF_BANCO_DESTINO:
        custom_fields.append({"id": CF_BANCO_DESTINO, "value": melhor.banco_destino})
    if CF_BANCO_ORIGEM:
        custom_fields.append({"id": CF_BANCO_ORIGEM, "value": melhor.banco_origem})
    if CF_PARCELA_ATUAL:
        custom_fields.append({"id": CF_PARCELA_ATUAL, "value": str(melhor.valor_parcela_atual)})
    if CF_SALDO_DEVEDOR:
        custom_fields.append({"id": CF_SALDO_DEVEDOR, "value": str(melhor.saldo_devedor)})
    if CF_TOTAL_FINANCIADO:
        custom_fields.append({"id": CF_TOTAL_FINANCIADO, "value": str(melhor.total_financiado)})
    if CF_SIMULACAO_RESUMO:
        resumo = formatar_resumo_simulacoes(resultado)
        custom_fields.append({"id": CF_SIMULACAO_RESUMO, "value": resumo})

    payload = {"customFields": custom_fields}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{GHL_API_BASE}/contacts/{contact_id}",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Erro ao atualizar contato: {e}")
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


async def enviar_whatsapp(
    contact_id: str,
    mensagem: str,
) -> dict | None:
    """
    Envia WhatsApp via SMS custom provider na GHL.
    """
    if not GHL_API_KEY or not contact_id:
        return None

    payload = {
        "type": "SMS",
        "contactId": contact_id,
        "message": mensagem,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GHL_API_BASE}/conversations/messages",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"WhatsApp enviado para contato {contact_id}")
            return data
    except Exception as e:
        logger.error(f"Erro ao enviar WhatsApp: {e}")
        return None


def formatar_resumo_simulacoes(resultado: ResultadoCliente) -> str:
    """Formata um resumo textual das simulacoes para custom field."""
    if not resultado.simulacoes:
        return "Nenhuma simulacao disponivel"

    linhas = []
    for i, sim in enumerate(resultado.simulacoes[:5], 1):  # Top 5
        linhas.append(
            f"{i}. {sim.banco_origem} -> {sim.banco_destino}: "
            f"Liberado R${sim.valor_liberado:,.2f} "
            f"(Parcela R${sim.valor_parcela_atual:,.2f} | "
            f"Saldo R${sim.saldo_devedor:,.2f})"
        )
    return "\n".join(linhas)


def formatar_mensagem_whatsapp(resultado: ResultadoCliente) -> str:
    """Formata a mensagem de WhatsApp com a melhor simulacao."""
    melhor = resultado.melhor_simulacao
    if not melhor:
        return ""

    return (
        f"Ola! Temos uma oportunidade especial para voce.\n\n"
        f"Identificamos que voce pode fazer a portabilidade do seu "
        f"emprestimo consignado do {melhor.banco_origem} para o {melhor.banco_destino}.\n\n"
        f"Parcela atual: R$ {melhor.valor_parcela_atual:,.2f}\n"
        f"Saldo devedor: R$ {melhor.saldo_devedor:,.2f}\n"
        f"Valor que pode ser liberado: R$ {melhor.valor_liberado:,.2f}\n\n"
        f"Deseja saber mais? Responda esta mensagem!"
    )
