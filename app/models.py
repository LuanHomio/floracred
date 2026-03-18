from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ── Requests ──────────────────────────────────────────────

class ProcessarClienteRequest(BaseModel):
    cpf: str
    contact_id: Optional[str] = None  # ID do contato na GHL
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None


class ProcessarListaRequest(BaseModel):
    clientes: list[ProcessarClienteRequest]
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None


# ── Dados coletados do Sistema Corban ─────────────────────

class DadosBeneficio(BaseModel):
    idade: Optional[int] = None
    nascimento: Optional[str] = None
    codigo_beneficio: Optional[str] = None
    especie: Optional[str] = None


class Emprestimo(BaseModel):
    codigo_banco: Optional[str] = None
    nome_banco: Optional[str] = None
    taxa_juros: Optional[float] = None
    saldo_devedor: Optional[float] = None
    parcelas_pagas: Optional[int] = None
    valor_parcela: Optional[float] = None


class DadosCliente(BaseModel):
    cpf: str
    beneficio: Optional[DadosBeneficio] = None
    emprestimos: list[Emprestimo] = []
    erro: Optional[str] = None


# ── Simulacao ─────────────────────────────────────────────

class Simulacao(BaseModel):
    banco_origem: str
    banco_destino: str
    codigo_banco_origem: str
    valor_parcela_atual: float
    saldo_devedor: float
    parcelas_pagas: int
    taxa_juros_atual: float
    coeficiente_usado: float
    total_financiado: float  # parcela / coeficiente
    valor_liberado: float    # total_financiado - saldo_devedor
    pode_portar: bool = True
    motivos_rejeicao: list[str] = []


class ResultadoCliente(BaseModel):
    cpf: str
    contact_id: Optional[str] = None
    beneficio: Optional[DadosBeneficio] = None
    emprestimos_encontrados: int = 0
    simulacoes: list[Simulacao] = []
    melhor_simulacao: Optional[Simulacao] = None
    erro: Optional[str] = None


# ── Status de processamento ───────────────────────────────

class StatusProcessamento(str, Enum):
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    CONCLUIDO = "concluido"
    ERRO = "erro"


class StatusJob(BaseModel):
    job_id: str
    total: int
    processados: int = 0
    status: StatusProcessamento = StatusProcessamento.PENDENTE
    resultados: list[ResultadoCliente] = []
