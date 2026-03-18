"""
FastAPI app — endpoints webhook para integracao GHL <-> Sistema Corban.

Endpoints:
  POST /webhook/ghl             -> Recebe webhook direto da GHL (formato nativo)
  POST /webhook/processar       -> Processa 1 CPF (formato simples)
  POST /webhook/processar-lista -> Processa lista de CPFs (async, retorna job_id)
  GET  /webhook/status/{job_id} -> Status do processamento em lote
  GET  /health                  -> Health check
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    ProcessarClienteRequest,
    ProcessarListaRequest,
    ResultadoCliente,
    StatusJob,
    StatusProcessamento,
)
from app.scraper import coletar_dados_cliente_async
from app.simulador import processar_cliente
from app.ghl import atualizar_contato_simulacao, adicionar_tag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Storage em memoria para jobs (para producao, usar Redis)
jobs: dict[str, StatusJob] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Floracred API iniciada")
    yield
    logger.info("Floracred API encerrada")


app = FastAPI(
    title="Floracred Portabilidade API",
    description="API para scraping do Sistema Corban, simulacao de portabilidade e integracao GHL",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "floracred-api"}


# ── Webhook GHL (formato nativo) ──────────────────────────

@app.post("/webhook/ghl")
async def webhook_ghl(request: Request, bg: BackgroundTasks):
    """
    Recebe o webhook direto da GHL no formato nativo.
    Extrai contact_id e CPF do payload e processa em background.

    Campos usados do payload GHL:
    - contact_id: ID do contato
    - CPF: custom field do contato
    - customData.cpf: campo alternativo
    """
    body = await request.json()

    # Extrair contact_id
    contact_id = body.get("contact_id", "")

    # Extrair CPF (tentar varias fontes)
    cpf = (
        body.get("CPF", "")
        or body.get("cpf", "")
        or (body.get("customData") or {}).get("cpf", "")
        or (body.get("customData") or {}).get("CPF", "")
    )

    if not cpf:
        logger.warning(f"Webhook GHL recebido sem CPF: contact_id={contact_id}")
        return {"status": "erro", "mensagem": "CPF nao encontrado no payload"}

    if not contact_id:
        logger.warning(f"Webhook GHL recebido sem contact_id")
        return {"status": "erro", "mensagem": "contact_id nao encontrado no payload"}

    # Limpar CPF
    cpf_limpo = cpf.replace(".", "").replace("-", "").replace(" ", "")

    logger.info(f"Webhook GHL: CPF={cpf_limpo}, contact_id={contact_id}")

    # Processar em background para responder rapido ao GHL
    bg.add_task(_processar_ghl_background, cpf_limpo, contact_id)

    return {
        "status": "recebido",
        "cpf": cpf_limpo,
        "contact_id": contact_id,
        "mensagem": "Processamento iniciado em background",
    }


async def _processar_ghl_background(cpf: str, contact_id: str):
    """Processa um CPF recebido via webhook GHL."""
    try:
        logger.info(f"[GHL BG] Iniciando processamento CPF contact_id={contact_id}")

        # 1. Scraping
        dados = await coletar_dados_cliente_async(cpf)

        # 2. Simulacao
        resultado = processar_cliente(dados, contact_id=contact_id)

        # 3. Atualizar GHL
        await atualizar_contato_simulacao(contact_id, resultado)

        tem_sim = any(se.melhor_simulacao for se in resultado.simulacoes_por_emprestimo)
        if tem_sim:
            await adicionar_tag(contact_id, ["simulacao-portabilidade"])
        else:
            await adicionar_tag(contact_id, ["sem-portabilidade"])

        logger.info(
            f"[GHL BG] Concluido: contact_id={contact_id}, "
            f"liberado=R${resultado.valor_liberado_total:,.2f}"
        )
    except Exception as e:
        logger.exception(f"[GHL BG] Erro ao processar contact_id={contact_id}")


# ── Processar 1 CPF (formato simples) ────────────────────

@app.post("/webhook/processar", response_model=ResultadoCliente)
async def processar_cpf(req: ProcessarClienteRequest):
    """
    Recebe 1 CPF, faz scraping, aplica regras, gera simulacoes.
    Atualiza custom fields na GHL:
    - Possibilidade Portabilidade = Sim/Nao
    - Valor Liberado Total
    - Resumo Simulacao (detalhamento por parcela)
    """
    logger.info(f"Processando CPF (contact_id={req.contact_id})")

    # 1. Scraping (roda em thread separada para nao bloquear o event loop)
    dados = await coletar_dados_cliente_async(req.cpf)

    # 2. Simulacao com regras e prioridade de bancos
    resultado = processar_cliente(dados, contact_id=req.contact_id)

    # 3. Atualizar GHL (se tiver contact_id)
    if req.contact_id:
        await atualizar_contato_simulacao(req.contact_id, resultado)

        if resultado.simulacoes_por_emprestimo:
            await adicionar_tag(req.contact_id, ["simulacao-portabilidade"])
        else:
            await adicionar_tag(req.contact_id, ["sem-portabilidade"])

    return resultado


# ── Processar Lista (bulk) ────────────────────────────────

@app.post("/webhook/processar-lista")
async def processar_lista(req: ProcessarListaRequest, bg: BackgroundTasks):
    """
    Recebe lista de CPFs, processa em background.
    Retorna job_id para consultar status.
    """
    job_id = str(uuid.uuid4())[:8]
    job = StatusJob(
        job_id=job_id,
        total=len(req.clientes),
        status=StatusProcessamento.PROCESSANDO,
    )
    jobs[job_id] = job

    bg.add_task(_processar_lista_background, job_id, req.clientes)

    logger.info(f"Job {job_id} criado com {len(req.clientes)} CPFs")
    return {"job_id": job_id, "total": len(req.clientes), "status": "processando"}


async def _processar_lista_background(
    job_id: str,
    clientes: list[ProcessarClienteRequest],
):
    """Processa lista de CPFs sequencialmente em background."""
    job = jobs[job_id]

    for cliente in clientes:
        try:
            logger.info(f"[Job {job_id}] Processando CPF (contact_id={cliente.contact_id})")

            dados = await coletar_dados_cliente_async(cliente.cpf)
            resultado = processar_cliente(dados, contact_id=cliente.contact_id)

            # GHL
            if cliente.contact_id:
                await atualizar_contato_simulacao(cliente.contact_id, resultado)

                if resultado.simulacoes_por_emprestimo:
                    await adicionar_tag(cliente.contact_id, ["simulacao-portabilidade"])
                else:
                    await adicionar_tag(cliente.contact_id, ["sem-portabilidade"])

            job.resultados.append(resultado)
            job.processados += 1

        except Exception as e:
            logger.exception(f"[Job {job_id}] Erro no CPF")
            job.resultados.append(
                ResultadoCliente(
                    cpf=cliente.cpf,
                    contact_id=cliente.contact_id,
                    erro=str(e),
                )
            )
            job.processados += 1

        # Pausa entre clientes para nao sobrecarregar o Corban
        await asyncio.sleep(2)

    job.status = StatusProcessamento.CONCLUIDO
    logger.info(f"[Job {job_id}] Concluido: {job.processados}/{job.total}")


# ── Status do Job ─────────────────────────────────────────

@app.get("/webhook/status/{job_id}")
async def status_job(job_id: str):
    """Consulta status de um processamento em lote."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    return job


# ── Listar Jobs ───────────────────────────────────────────

@app.get("/webhook/jobs")
async def listar_jobs():
    """Lista todos os jobs."""
    return {
        jid: {
            "total": j.total,
            "processados": j.processados,
            "status": j.status,
        }
        for jid, j in jobs.items()
    }
