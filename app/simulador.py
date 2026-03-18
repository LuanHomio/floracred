"""
Calculadora de simulacoes de portabilidade.

Formula:
  total_financiado = valor_parcela / coeficiente
  valor_liberado = total_financiado - saldo_devedor

Coeficiente medio para 84x: 0.02180
"""

import logging

from app.models import (
    DadosBeneficio,
    DadosCliente,
    Emprestimo,
    ResultadoCliente,
    Simulacao,
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
    Para um emprestimo, verifica todos os bancos destino e gera simulacoes.
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

        sim = Simulacao(
            banco_origem=nome_origem,
            banco_destino=regra.nome,
            codigo_banco_origem=codigo_origem,
            valor_parcela_atual=parcela,
            saldo_devedor=saldo,
            parcelas_pagas=emprestimo.parcelas_pagas or 0,
            taxa_juros_atual=emprestimo.taxa_juros or 0,
            coeficiente_usado=coeficiente,
            total_financiado=round(total_financiado, 2),
            valor_liberado=round(valor_liberado, 2),
            pode_portar=pode,
            motivos_rejeicao=motivos,
        )

        # Verificar troco minimo
        if pode and regra.troco_minimo > 0 and valor_liberado < regra.troco_minimo:
            sim.pode_portar = False
            sim.motivos_rejeicao.append(
                f"Valor liberado (R${valor_liberado:.2f}) menor que troco minimo (R${regra.troco_minimo:.2f})"
            )

        simulacoes.append(sim)

    return simulacoes


def processar_cliente(dados: DadosCliente, contact_id: str | None = None) -> ResultadoCliente:
    """
    Processa todos os emprestimos de um cliente e retorna simulacoes.
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

    for emp in dados.emprestimos:
        sims = simular_emprestimo(emp, beneficio)
        # Adicionar apenas simulacoes que podem portar
        validas = [s for s in sims if s.pode_portar]
        resultado.simulacoes.extend(validas)

    # Ordenar por maior valor liberado
    resultado.simulacoes.sort(key=lambda s: s.valor_liberado, reverse=True)

    if resultado.simulacoes:
        resultado.melhor_simulacao = resultado.simulacoes[0]

    logger.info(
        f"CPF processado: {len(dados.emprestimos)} emprestimos, "
        f"{len(resultado.simulacoes)} simulacoes validas"
    )
    return resultado
