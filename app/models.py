from pydantic import BaseModel
from typing import Optional
from enum import Enum


# ── Requests ──────────────────────────────────────────────

class ProcessarClienteRequest(BaseModel):
    cpf: str
    contact_id: Optional[str] = None  # ID do contato na GHL


class ProcessarListaRequest(BaseModel):
    clientes: list[ProcessarClienteRequest]


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
    prioridade_banco: int  # Prioridade do banco destino (1 = Daycoval)
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


class SimulacaoEmprestimo(BaseModel):
    """Resultado da simulacao para UM emprestimo especifico."""
    indice: int  # Numero do emprestimo (1, 2, 3...)
    emprestimo: Emprestimo
    melhor_simulacao: Optional[Simulacao] = None  # Melhor banco destino (por prioridade)
    todas_simulacoes: list[Simulacao] = []  # Todas as opcoes validas
    valor_liberado: float = 0  # Valor liberado da melhor opcao


class ResultadoCliente(BaseModel):
    cpf: str
    contact_id: Optional[str] = None
    beneficio: Optional[DadosBeneficio] = None
    emprestimos_encontrados: int = 0
    simulacoes_por_emprestimo: list[SimulacaoEmprestimo] = []
    valor_liberado_total: float = 0  # Soma de todos os emprestimos
    resumo_texto: str = ""  # Texto formatado para custom field
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
