"""
Motor de regras de portabilidade.

Cada banco destino tem suas regras: quais bancos porta, parcelas minimas,
idade, saldo minimo, etc. Fonte: regras_portabilidade.md (atualizado 04/02/2026).
"""

from dataclasses import dataclass
from app.models import Emprestimo, DadosBeneficio

# ── Bancos na CIP ─────────────────────────────────────────
# Bancos considerados "de rede" — regras especiais para parcelas pagas

BANCOS_CIP = {
    "001",  # BANCO DO BRASIL
    "033",  # SANTANDER
    "041",  # BANRISUL
    "047",  # BANESE
    "070",  # BANCO BRB
    "077",  # BANCO INTER
    "104",  # CEF
    "394",  # BRADESCO FINANCIAMENTOS
    "422",  # SAFRA
}


# ── Regras por banco destino ──────────────────────────────

@dataclass
class RegraPortabilidade:
    nome: str
    prioridade: int = 99  # Menor = maior prioridade. Daycoval = 1
    ativo: bool = True
    # {codigo_banco_origem: parcelas_minimas} — None = aceita todos com o min padrao
    bancos_portados: dict | None = None
    parcelas_minimas_padrao: int = 12  # padrao se banco nao tem regra especifica
    bancos_nao_portados: list[str] | None = None
    idade_min: int = 18
    idade_max: int = 80
    saldo_minimo: float = 0
    parcela_minima: float = 0
    troco_minimo: float = 0
    prazo_maximo: int = 96
    aceita_analfabeto: bool = False
    reducao_parcela: bool = True
    comissiona_menos_12: bool = False
    horario_limite: str = "16:00"
    max_ted: float = 0  # 0 = sem limite definido
    taxa_port: float = 0
    taxa_port_pura: float = 0
    taxa_refin_min: float = 0
    taxa_refin_max: float = 0


REGRAS: dict[str, RegraPortabilidade] = {
    # ── 1. Banrisul ───────────────────────────────────────
    "banrisul": RegraPortabilidade(
        nome="Banrisul",
        prioridade=3,
        bancos_portados={
            "012": 12,   # INBURSA
            "935": 12,   # FACTA
            "121": 12,   # AGIBANK
            "290": 12,   # PAGBANK
            "069": 12,   # CREFISA
            "422": 12,   # SAFRA
            "029": 25,   # ITAU CONSIGNADO
            "623": 25,   # PAN
        },
        bancos_nao_portados=["330", "335"],  # BARIGUI, DIGIO
        idade_max=77,
        saldo_minimo=5000.00,
        troco_minimo=200.00,
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="16:00",
        taxa_port=1.40,
        taxa_port_pura=1.70,
        taxa_refin_min=1.72,
        taxa_refin_max=1.85,
    ),

    # ── 2. Ole ────────────────────────────────────────────
    "ole": RegraPortabilidade(
        nome="Ole",
        ativo=False,  # SUSPENSO
    ),

    # ── 3. Daycoval ───────────────────────────────────────
    "daycoval": RegraPortabilidade(
        nome="Banco Daycoval",
        prioridade=1,  # BANCO PRINCIPAL
        parcelas_minimas_padrao=6,
        bancos_portados={
            "935": 24,   # FACTA
            "623": 25,   # PAN
            "029": 25,   # ITAU CONSIGNADO
            "121": 15,   # AGIBANK
            # Continental nao esta na lista de codigos, mas regra diz 24
        },
        bancos_nao_portados=["626", "422"],  # C6 FICSA, SAFRA
        idade_max=71,
        parcela_minima=20.00,
        troco_minimo=100.00,
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="16:00",
        max_ted=300000.00,
        prazo_maximo=96,
        taxa_port=1.43,
        taxa_refin_min=1.66,
        taxa_refin_max=1.85,
    ),

    # ── 4. Itau ───────────────────────────────────────────
    "itau": RegraPortabilidade(
        nome="Itau",
        ativo=False,  # SUSPENSO
    ),

    # ── 5. Banco PAN ──────────────────────────────────────
    "pan": RegraPortabilidade(
        nome="Banco PAN",
        prioridade=5,
        parcelas_minimas_padrao=20,
        bancos_portados={
            "626": 24,   # C6
            "029": 25,   # ITAU CONSIGNADO
        },
        bancos_nao_portados=["104", "121", "070"],  # CEF, AGIBANK, BRB (Maxima nao tem codigo)
        idade_max=64,
        saldo_minimo=5000.00,
        aceita_analfabeto=True,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="17:00",
        prazo_maximo=96,
        taxa_port=1.50,
        taxa_refin_min=1.78,
        taxa_refin_max=1.85,
    ),

    # ── 6. Safra ──────────────────────────────────────────
    "safra": RegraPortabilidade(
        nome="Safra",
        prioridade=4,
        bancos_nao_portados=[
            "707",  # DAYCOVAL
            "012",  # INBURSA
            # Alfa nao tem codigo mapeado
        ],
        bancos_portados={
            "623": 25,   # PAN >25 pagas
            "626": 18,   # C6 >18 pagas
            "041": 12,   # BANRISUL >12 pagas
            "935": 24,   # FACTA >24 pagas
            "029": 25,   # ITAU 029
        },
        idade_min=26,
        idade_max=75,
        saldo_minimo=5200.00,
        troco_minimo=400.00,
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="16:00",
        taxa_port=1.44,
        taxa_refin_min=1.69,
        taxa_refin_max=1.69,
    ),

    # ── 7. C6 ─────────────────────────────────────────────
    "c6": RegraPortabilidade(
        nome="C6",
        prioridade=6,
        parcelas_minimas_padrao=13,  # BYX 13 pagas como padrao CIP
        bancos_portados={
            "029": 25,   # ITAU CONSIGNADO
            "623": 37,   # PAN
        },
        bancos_nao_portados=[
            "422",  # SAFRA
            "079",  # PICPAY
            "707",  # DAYCOVAL
            "121",  # AGIBANK
            "012",  # INBURSA
            "070",  # BRB
            "935",  # FACTA
            "254",  # PARANA BANCO
            "329",  # QI SOCIEDADE
        ],
        idade_min=21,
        idade_max=73,
        saldo_minimo=2000.00,
        troco_minimo=50.00,
        aceita_analfabeto=True,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="16:00",
        prazo_maximo=96,
        taxa_port=1.35,
        taxa_port_pura=1.75,
        taxa_refin_min=1.55,
        taxa_refin_max=1.55,
    ),

    # ── 8. Facta ──────────────────────────────────────────
    "facta": RegraPortabilidade(
        nome="Facta",
        prioridade=2,
        bancos_portados={
            "121": 15,   # AGIBANK
            "626": 12,   # C6
            "623": 25,   # PAN
            "707": 24,   # DAYCOVAL
            "254": 15,   # PARANA
            "029": 25,   # ITAU 029
            "955": 12,   # OLE
            "033": 12,   # SANTANDER
            "318": 12,   # BMG
            "070": 0,    # BRB — 0 pagas
        },
        bancos_nao_portados=[
            "611",  # BANCO PAULISTA (orig. Facta)
            "359",  # ZEMA (orig. Facta)
            # Socicred 917, Pine, Inbursa
            "643",  # PINE
            "012",  # INBURSA
        ],
        idade_max=72,
        saldo_minimo=100.00,
        parcela_minima=50.00,
        troco_minimo=50.00,
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=True,
        horario_limite="14:00",
        max_ted=150000.00,
        prazo_maximo=96,
        taxa_port=1.00,
        taxa_port_pura=1.70,
        taxa_refin_min=1.50,
        taxa_refin_max=1.80,
    ),

    # ── 9. Digio ──────────────────────────────────────────
    "digio": RegraPortabilidade(
        nome="Digio",
        prioridade=7,
        parcelas_minimas_padrao=12,
        bancos_portados={
            "029": 25,   # ITAU CONSIGNADO
            "623": 25,   # PAN
        },
        bancos_nao_portados=[
            "394",  # BRADESCO
            "001",  # BANCO DO BRASIL
            "041",  # BANRISUL
        ],
        idade_max=70,
        saldo_minimo=4500.00,
        troco_minimo=250.00,
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="16:00",
        max_ted=70000.00,
        prazo_maximo=96,
        taxa_port=1.37,
        taxa_refin_min=1.50,
        taxa_refin_max=1.85,
    ),

    # ── 10. BMG ───────────────────────────────────────────
    "bmg": RegraPortabilidade(
        nome="BMG",
        prioridade=8,
        bancos_portados={
            "422": 12,   # SAFRA
            "707": 15,   # DAYCOVAL
            "623": 25,   # PAN
            "029": 25,   # ITAU 029
        },
        bancos_nao_portados=[
            "121",  # AGIBANK
            "955",  # OLE
            # BCCV 250, Itau BBA 184, Cifra 233 — nao mapeados
        ],
        idade_min=21,
        idade_max=71,
        saldo_minimo=1000.00,
        troco_minimo=50.00,
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="17:45",
        max_ted=70000.00,
        prazo_maximo=96,
        taxa_port=1.40,
        taxa_refin_min=1.85,
        taxa_refin_max=1.85,
    ),

    # ── 11. Happy Consig ──────────────────────────────────
    "happy": RegraPortabilidade(
        nome="Happy Consig",
        prioridade=9,
        bancos_nao_portados=[
            "643",  # PINE
            "935",  # FACTA
            "104",  # CAIXA
            "012",  # INBURSA
            "626",  # C6
        ],
        idade_min=21,
        idade_max=71,
        saldo_minimo=4000.00,
        troco_minimo=50.00,
        aceita_analfabeto=True,
        reducao_parcela=False,  # So na port pura
        comissiona_menos_12=True,
        horario_limite="16:00",
        max_ted=80000.00,
        prazo_maximo=96,
        taxa_port_pura=1.77,
        taxa_refin_min=1.80,
        taxa_refin_max=1.80,
    ),

    # ── 12. BRB ───────────────────────────────────────────
    "brb": RegraPortabilidade(
        nome="BRB",
        prioridade=10,
        parcelas_minimas_padrao=12,
        bancos_portados={
            "029": 25,   # ITAU CONSIGNADO
            "623": 25,   # PAN
        },
        bancos_nao_portados=[
            "932",  # SANTINVEST
            "079",  # PICPAY
            "394",  # BRADESCO
            "012",  # INBURSA
            "290",  # PAGBANK
            "121",  # AGIBANK
            "626",  # C6
        ],
        idade_max=73,
        saldo_minimo=3000.00,
        troco_minimo=0,  # 1 parcela de troco (calculado no simulador)
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=False,
        horario_limite="16:00",
        max_ted=150000.00,
        prazo_maximo=96,
        taxa_refin_min=1.79,
        taxa_refin_max=1.80,
    ),

    # ── 13. Inbursa ───────────────────────────────────────
    "inbursa": RegraPortabilidade(
        nome="Inbursa",
        prioridade=11,
        bancos_portados={
            "707": 13,   # DAYCOVAL
            "623": 25,   # PAN
            "121": 13,   # AGIBANK
            "033": 13,   # SANTANDER
            "041": 13,   # BANRISUL
            "029": 25,   # ITAU 029
        },
        bancos_nao_portados=[
            "935",  # FACTA
            "422",  # SAFRA
            "329",  # QI
            "626",  # C6
            "079",  # PICPAY
            # BNP, Alfa, Sabemi — codigos nao mapeados diretamente
        ],
        idade_min=22,
        idade_max=68,
        saldo_minimo=4000.00,
        aceita_analfabeto=False,
        reducao_parcela=False,
        horario_limite="",
        prazo_maximo=96,
        taxa_port=1.30,
        taxa_refin_min=1.52,
        taxa_refin_max=1.52,
    ),

    # ── 14. Finanlo Bank ──────────────────────────────────
    "finanlo": RegraPortabilidade(
        nome="Finanlo Bank",
        prioridade=12,
        bancos_portados={
            "033": 12,   # SANTANDER
            "389": 12,   # MERCANTIL
            "707": 12,   # DAYCOVAL
            "254": 12,   # PARANA
            "121": 12,   # AGIBANK
            "623": 25,   # PAN
            "029": 25,   # ITAU 029
            "070": 1,    # BRB — 1 paga
            "041": 1,    # BANRISUL — 1 paga
        },
        bancos_nao_portados=[
            "012",  # INBURSA
            "329",  # QI
            "422",  # SAFRA
            "079",  # PICPAY
            "626",  # C6
            "935",  # FACTA
            "643",  # PINE
            # BNP, Alfa — nao mapeados
        ],
        idade_max=69,
        saldo_minimo=4000.00,
        troco_minimo=100.00,
        aceita_analfabeto=False,
        reducao_parcela=False,
        comissiona_menos_12=False,
        horario_limite="16:00",
        prazo_maximo=96,
        taxa_port=1.30,
        taxa_port_pura=1.75,
        taxa_refin_min=1.70,
        taxa_refin_max=1.85,
    ),

    # ── 15. Prospecta Fintech ─────────────────────────────
    "prospecta": RegraPortabilidade(
        nome="Prospecta Fintech",
        prioridade=13,
        parcelas_minimas_padrao=1,  # demais bancos a partir de 1 paga
        bancos_portados={
            "033": 13,   # SANTANDER
            "707": 13,   # DAYCOVAL
            "623": 13,   # PAN
            "121": 13,   # AGIBANK
            "389": 13,   # MERCANTIL
            "041": 13,   # BANRISUL (corban)
        },
        bancos_nao_portados=[
            "329",  # QI
            "935",  # FACTA
            "626",  # C6
            "079",  # PICPAY
            "422",  # SAFRA
            "070",  # BRB
            "254",  # PARANA BANCO
            "753",  # NBC
            "643",  # PINE
            "012",  # INBURSA
            "707",  # DAYCOVAL (tambem nao porta conforme lista)
        ],
        idade_max=68,
        saldo_minimo=1000.00,
        troco_minimo=100.00,
        aceita_analfabeto=False,
        reducao_parcela=False,
        comissiona_menos_12=True,
        horario_limite="16:00",
        max_ted=50000.00,
        prazo_maximo=96,
        taxa_refin_min=1.75,
        taxa_refin_max=1.85,
    ),

    # ── 16. PicPay ────────────────────────────────────────
    "picpay": RegraPortabilidade(
        nome="PicPay",
        prioridade=14,
        bancos_portados={
            "623": 25,   # PAN
            "029": 25,   # ITAU 029
            "626": 24,   # C6
            "955": 24,   # OLE
        },
        bancos_nao_portados=[
            "012",  # INBURSA
            "070",  # BRB
        ],
        idade_min=21,
        idade_max=70,
        parcela_minima=50.00,
        troco_minimo=100.00,
        aceita_analfabeto=False,
        reducao_parcela=False,
        comissiona_menos_12=False,
        horario_limite="16:00",
        max_ted=100000.00,
        prazo_maximo=96,
        taxa_port=1.30,
        taxa_refin_min=1.85,
        taxa_refin_max=1.85,
    ),

    # ── 17. Icred ─────────────────────────────────────────
    "icred": RegraPortabilidade(
        nome="Icred",
        prioridade=15,
        bancos_portados={
            "623": 25,   # PAN
            "029": 25,   # ITAU 029
        },
        bancos_nao_portados=[
            "626",  # C6
            "012",  # INBURSA
            "643",  # PINE
            "329",  # QI
        ],
        idade_min=21,
        idade_max=68,
        saldo_minimo=3000.00,
        troco_minimo=100.00,
        aceita_analfabeto=False,
        reducao_parcela=False,
        comissiona_menos_12=False,
        horario_limite="16:00",
        max_ted=100000.00,
        prazo_maximo=96,
        taxa_refin_min=1.63,
        taxa_refin_max=1.85,
    ),

    # ── 18. BRB Consig 360 ────────────────────────────────
    "brb_consig_360": RegraPortabilidade(
        nome="BRB Consig 360",
        prioridade=16,
        parcelas_minimas_padrao=12,  # consignaveis a partir de 12
        # Bancos de rede com 1 paga (tratado na logica)
        bancos_nao_portados=[
            "070",  # BRB
            "079",  # PICPAY
            "121",  # AGIBANK
            "626",  # C6
        ],
        idade_max=73,
        saldo_minimo=3000.00,
        troco_minimo=100.00,
        aceita_analfabeto=False,
        reducao_parcela=True,
        comissiona_menos_12=True,
        horario_limite="16:00",
        max_ted=150000.00,
        prazo_maximo=96,
        taxa_refin_min=1.79,
        taxa_refin_max=1.85,
    ),
}


def verificar_elegibilidade(
    emprestimo: Emprestimo,
    beneficio: DadosBeneficio,
    regra: RegraPortabilidade,
) -> tuple[bool, list[str]]:
    """
    Verifica se um emprestimo pode ser portado para o banco destino.
    Retorna (pode_portar, lista_de_motivos_rejeicao).
    """
    motivos: list[str] = []

    if not regra.ativo:
        return False, ["Banco destino suspenso"]

    codigo = emprestimo.codigo_banco or ""
    pagas = emprestimo.parcelas_pagas or 0
    saldo = emprestimo.saldo_devedor or 0
    parcela = emprestimo.valor_parcela or 0
    idade = beneficio.idade or 0

    # 1. Banco na lista de nao portados?
    if regra.bancos_nao_portados and codigo in regra.bancos_nao_portados:
        motivos.append(f"Banco {codigo} esta na lista de nao portados")

    # 2. Parcelas pagas suficientes?
    min_pagas = regra.parcelas_minimas_padrao
    if regra.bancos_portados and codigo in regra.bancos_portados:
        min_pagas = regra.bancos_portados[codigo]
    elif regra.bancos_portados and codigo not in regra.bancos_portados:
        # Se tem lista explicita e o banco nao esta, verificar se e CIP
        if codigo in BANCOS_CIP:
            min_pagas = regra.parcelas_minimas_padrao
        else:
            # Banco nao esta na lista de portados nem e CIP
            # Alguns bancos aceitam "demais bancos", usar padrao
            pass

    if pagas < min_pagas:
        motivos.append(f"Parcelas pagas ({pagas}) menor que minimo ({min_pagas})")

    # 3. Idade dentro do range?
    if idade > 0:
        if idade < regra.idade_min:
            motivos.append(f"Idade ({idade}) menor que minimo ({regra.idade_min})")
        if idade > regra.idade_max:
            motivos.append(f"Idade ({idade}) maior que maximo ({regra.idade_max})")

    # 4. Saldo minimo?
    if regra.saldo_minimo > 0 and saldo < regra.saldo_minimo:
        motivos.append(f"Saldo devedor (R${saldo:.2f}) menor que minimo (R${regra.saldo_minimo:.2f})")

    # 5. Parcela minima?
    if regra.parcela_minima > 0 and parcela < regra.parcela_minima:
        motivos.append(f"Parcela (R${parcela:.2f}) menor que minimo (R${regra.parcela_minima:.2f})")

    pode = len(motivos) == 0
    return pode, motivos
