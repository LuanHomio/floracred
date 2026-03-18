"""
Calculadora de simulacoes de portabilidade.

Formula:
  total_financiado = valor_parcela / coeficiente
  valor_liberado = total_financiado - saldo_devedor

Para cada emprestimo, encontra o melhor banco destino por prioridade.
Soma o valor liberado de todos os emprestimos portaveis.
Gera resumo formatado por parcela.
"""

import logging

from app.models import (
    DadosBeneficio,
    DadosCliente,
    Emprestimo,
    ResultadoCliente,
    Simulacao,
    SimulacaoEmprestimo,
)
from app.regras import REGRAS, verificar_elegibilidade

logger = logging.getLogger(__name__)

# Coeficiente medio para simulacao em 84x
COEFICIENTE_84X = 0.02180


def simular_emprestimo(
    emprestimo: Emprestimo,
    beneficio: DadosBeneficio,
    coeficiente: float = COEFICIENTE_84X,
) -> list[Simulacao]:
    """
    Para um emprestimo, verifica todos os bancos destino e retorna simulacoes validas.
    Ordenadas por prioridade do banco destino.
    """
    simulacoes = []

    parcela = emprestimo.valor_parcela or 0
    saldo = emprestimo.saldo_devedor or 0
    codigo_origem = emprestimo.codigo_banco or "???"
    nome_origem = emprestimo.nome_banco or f"Banco {codigo_origem}"

    if parcela <= 0 or saldo <= 0:
        return simulacoes

    total_financiado = parcela / coeficiente
    valor_liberado = total_financiado - saldo

    for chave, regra in REGRAS.items():
        pode, motivos = verificar_elegibilidade(emprestimo, beneficio, regra)

        if not pode:
            continue

        # Verificar troco minimo
        if regra.troco_minimo > 0 and valor_liberado < regra.troco_minimo:
            continue

        # Valor liberado precisa ser positivo
        if valor_liberado <= 0:
            continue

        sim = Simulacao(
            banco_origem=nome_origem,
            banco_destino=regra.nome,
            prioridade_banco=regra.prioridade,
            codigo_banco_origem=codigo_origem,
            valor_parcela_atual=parcela,
            saldo_devedor=saldo,
            parcelas_pagas=emprestimo.parcelas_pagas or 0,
            taxa_juros_atual=emprestimo.taxa_juros or 0,
            coeficiente_usado=coeficiente,
            total_financiado=round(total_financiado, 2),
            valor_liberado=round(valor_liberado, 2),
        )
        simulacoes.append(sim)

    # Ordenar por prioridade (menor = melhor)
    simulacoes.sort(key=lambda s: s.prioridade_banco)
    return simulacoes


def processar_cliente(dados: DadosCliente, contact_id: str | None = None) -> ResultadoCliente:
    """
    Processa todos os emprestimos de um cliente.
    Para cada emprestimo, encontra o melhor banco destino.
    Soma valores liberados e gera resumo.
    """
    resultado = ResultadoCliente(
        cpf=dados.cpf,
        contact_id=contact_id,
        beneficio=dados.beneficio,
        emprestimos_encontrados=len(dados.emprestimos),
    )

    if dados.erro:
        resultado.erro = dados.erro
        return resultado

    beneficio = dados.beneficio or DadosBeneficio()

    for i, emp in enumerate(dados.emprestimos, 1):
        sims = simular_emprestimo(emp, beneficio)

        sim_emp = SimulacaoEmprestimo(
            indice=i,
            emprestimo=emp,
            todas_simulacoes=sims,
        )

        if sims:
            sim_emp.melhor_simulacao = sims[0]  # Melhor por prioridade
            sim_emp.valor_liberado = sims[0].valor_liberado

        resultado.simulacoes_por_emprestimo.append(sim_emp)

    # Somar valor liberado total (apenas emprestimos com simulacao valida)
    resultado.valor_liberado_total = sum(
        se.valor_liberado for se in resultado.simulacoes_por_emprestimo if se.melhor_simulacao
    )

    # Gerar resumo texto
    resultado.resumo_texto = formatar_resumo(resultado)

    logger.info(
        f"CPF processado: {len(dados.emprestimos)} emprestimos, "
        f"{sum(1 for se in resultado.simulacoes_por_emprestimo if se.melhor_simulacao)} com portabilidade, "
        f"total liberado R$ {resultado.valor_liberado_total:,.2f}"
    )
    return resultado


def formatar_resumo(resultado: ResultadoCliente) -> str:
    """
    Formata resumo das simulacoes para o custom field LARGE_TEXT.

    Formato:
    VALOR TOTAL LIBERADO: R$ X.XXX,XX

    DETALHAMENTO POR PARCELA:
    1. Parcela R$ 500,00 - Banco atual: INBURSA - Banco destino: Daycoval - Liberado: R$ 2.935,78
    2. Parcela R$ 350,00 - Banco atual: FACTA - Banco destino: Banrisul - Liberado: R$ 1.055,05
    """
    emprestimos_com_sim = [
        se for se in resultado.simulacoes_por_emprestimo if se.melhor_simulacao
    ]

    if not emprestimos_com_sim:
        return "Nenhuma portabilidade disponivel."

    linhas = [
        f"VALOR TOTAL LIBERADO: R$ {resultado.valor_liberado_total:,.2f}",
        "",
        "DETALHAMENTO POR PARCELA:",
    ]

    for se in emprestimos_com_sim:
        m = se.melhor_simulacao
        linhas.append(
            f"{se.indice}. Parcela R$ {m.valor_parcela_atual:,.2f} "
            f"- Banco atual: {m.banco_origem} "
            f"- Banco destino: {m.banco_destino} "
            f"- Saldo: R$ {m.saldo_devedor:,.2f} "
            f"- Liberado: R$ {m.valor_liberado:,.2f}"
        )

    # Listar outras opcoes se houver
    emprestimos_sem_sim = [
        se for se in resultado.simulacoes_por_emprestimo
        if not se.melhor_simulacao and se.emprestimo.valor_parcela and se.emprestimo.valor_parcela > 0
    ]
    if emprestimos_sem_sim:
        linhas.append("")
        linhas.append("SEM PORTABILIDADE:")
        for se in emprestimos_sem_sim:
            emp = se.emprestimo
            linhas.append(
                f"- Parcela R$ {emp.valor_parcela or 0:,.2f} "
                f"- Banco: {emp.nome_banco or emp.codigo_banco or '?'} "
                f"- Pagas: {emp.parcelas_pagas or 0}"
            )

    return "\n".join(linhas)
