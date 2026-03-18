"""
FastAPI app — endpoints webhook para integracao GHL <-> Sistema Corban.

Endpoints:
  POST /webhook/processar       -> Processa 1 CPF (scraping + simulacao + GHL)
  POST /webhook/processar-lista -> Processa lista de CPFs (async, retorna job_id)
  GET  /webhook/status/{job_id} -> Status do processamento em lote
  GET  /health                  -> Health check
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    ProcessarClienteRequest,
    ProcessarListaRequest,
    ResultadoCliente,
    StatusJob,
    StatusProcessamento,
)
from app.scraper import coletar_dados_cliente
from app.simulador import processar_cliente
from app.ghl import (
    criar_oportunidade,
    atualizar_contact_fields,
    adicionar_tag,
    enviar_whatsapp,
    formatar_mensagem_whatsapp,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Storage em memoria para jobs (para producao, usar Redis)
jobs: dict[str, StatusJob] = {}

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
ENVIAR_WHATSAPP_AUTO = os.getenv("ENVIAR_WHATSAPP_AUTO", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Floracred API iniciada")
    yield
    logger.info("Floracred API encerrada")


app = FastAPI(
    title="Floracred Portabilidade API",
    description="API para scraping do Sistema Corban, simulacao de portabilidade e integracao GHL",
    version="1.0.0",
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


# ── Processar 1 CPF ──────────────────────────────────────

@app.post("/webhook/processar", response_model=ResultadoCliente)
async def processar_cpf(req: ProcessarClienteRequest):
    """
    Recebe 1 CPF, faz scraping, aplica regras, gera simulacoes.
    Opcionalmente cria oportunidade na GHL e envia WhatsApp.
    """
    logger.info(f"Processando CPF (contact_id={req.contact_id})")

    # 1. Scraping (roda em thread separada para nao bloquear o event loop)
    dados = await asyncio.to_thread(coletar_dados_cliente, req.cpf)

    # 2. Simulacao
    resultado = processar_cliente(dados, contact_id=req.contact_id)

    # 3. Integracao GHL (se tiver contact_id)
    if req.contact_id and resultado.simulacoes:
        await atualizar_contact_fields(req.contact_id, resultado)
        await criar_oportunidade(resultado, req.pipeline_id, req.stage_id)
        await adicionar_tag(req.contact_id, ["simulacao-portabilidade"])

        if ENVIAR_WHATSAPP_AUTO:
            msg = formatar_mensagem_whatsapp(resultado)
            if msg:
                await enviar_whatsapp(req.contact_id, msg)
    elif req.contact_id and not resultado.simulacoes:
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

    bg.add_task(
        _processar_lista_background,
        job_id,
        req.clientes,
        req.pipeline_id,
    )

    logger.info(f"Job {job_id} criado com {len(req.clientes)} CPFs")
    return {"job_id": job_id, "total": len(req.clientes), "status": "processando"}


async def _processar_lista_background(
    job_id: str,
    clientes: list[ProcessarClienteRequest],
    pipeline_id: str | None,
):
    """Processa lista de CPFs sequencialmente em background."""
    job = jobs[job_id]

    for cliente in clientes:
        try:
            logger.info(f"[Job {job_id}] Processando CPF (contact_id={cliente.contact_id})")

            dados = await asyncio.to_thread(coletar_dados_cliente, cliente.cpf)
            resultado = processar_cliente(dados, contact_id=cliente.contact_id)

            # GHL
            if cliente.contact_id and resultado.simulacoes:
                await atualizar_contact_fields(cliente.contact_id, resultado)
                await criar_oportunidade(resultado, pipeline_id, cliente.stage_id)
                await adicionar_tag(cliente.contact_id, ["simulacao-portabilidade"])

                if ENVIAR_WHATSAPP_AUTO:
                    msg = formatar_mensagem_whatsapp(resultado)
                    if msg:
                        await enviar_whatsapp(cliente.contact_id, msg)
            elif cliente.contact_id and not resultado.simulacoes:
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

        # Pequena pausa entre clientes para nao sobrecarregar o Corban
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
