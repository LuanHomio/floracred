# Estrutura de Regras de Negócio - Portabilidade

## Visão Geral

Este documento descreve a arquitetura proposta para implementar as regras de negócio que determinam quais portabilidades podem ser oferecidas ao cliente, baseadas nos dados coletados do sistema.

---

## 1. Fluxo de Processamento

```
1. Coletar dados do cliente (idade, código do benefício)
2. Coletar empréstimos consignados (parcelas, bancos, taxas, etc.)
3. Para cada empréstimo:
   a. Aplicar regras de filtragem (pode portar? quantas pagas?)
   b. Se passar no filtro, verificar qual banco pode receber essa portabilidade
   c. Calcular simulações (96x, 84x, 72x) com coeficientes
   d. Gerar proposta
4. Consolidar todas as propostas válidas
5. Apresentar resultado final
```

---

## 2. Estrutura de Dados

### 2.1 Dados do Cliente
```python
cliente = {
    "idade": int,              # Ex: 66
    "codigo_beneficio": str,    # Ex: "32"
    "especie": str,             # Ex: "32 - Aposentadoria por invalidez previdenciária"
    "nascimento": str           # Ex: "23/09/1959 - 66 anos"
}
```

### 2.2 Dados de Empréstimo
```python
emprestimo = {
    "codigo_banco": str,        # Ex: "012" (INBURSA)
    "nome_banco": str,          # Ex: "BANCO INBURSA"
    "taxa_juros": float,        # Ex: 1.50
    "saldo_devedor": float,     # Ex: 21734.87
    "parcelas_pagas": int,      # Ex: 7
    "valor_parcela": float,     # Ex: 444.04
    "prazo_total": str,         # Ex: "89/96" (89 de 96 parcelas)
    # Outros campos que possam ser úteis
}
```

### 2.3 Regra de Portabilidade
```python
regra_portabilidade = {
    "banco_destino": str,       # Ex: "Banrisul"
    "bancos_portados": list,    # Lista de códigos de bancos que podem ser portados
    "bancos_nao_portados": list, # Lista de códigos que NÃO podem ser portados
    "parcelas_minimas": dict,   # Ex: {"012": 12, "389": 25} - código banco: qtd mínima
    "saldo_minimo": float,
    "parcela_minima": float,
    "troco_minimo": float,
    "risco_operacao": str,      # "BANCO", "CORRESPONDENTE", "BANCO E CORRESPONDENTE"
    "horario_limite": str,      # Ex: "16h", "17h"
    "reducao_parcela": bool,
    "comissiona_menos_12": bool,
    "analfabeto": bool,
    "idade_min": int,
    "idade_max": int,
    "prazo_maximo": int,        # Ex: 96
    "max_ted": float,
    "taxas": {
        "port_pura": float,
        "port_especial": float,
        "refin": dict           # Ex: {"min": 1.72, "max": 1.85}
    }
}
```

### 2.4 Resultado da Simulação
```python
simulacao = {
    "banco_origem": str,        # Banco do empréstimo atual
    "banco_destino": str,       # Banco que vai receber a portabilidade
    "emprestimo_original": dict, # Dados do empréstimo original
    "pode_portar": bool,        # Se atende todas as regras
    "motivo_rejeicao": list,    # Lista de motivos se não puder portar
    "simulacoes": {
        "96x": {
            "coeficiente": float,
            "taxa": float,
            "valor_liberado": float,
            "nova_parcela": float,
            "economia_mensal": float,
            "economia_total": float
        },
        "84x": {...},
        "72x": {...}
    }
}
```

---

## 3. Regras de Filtragem (Camada 1)

### 3.1 Verificação de Parcelas Pagas

**Regra Principal:**
- Se `parcelas_pagas >= 12`: Pode considerar para portabilidade
- Se `parcelas_pagas < 12`: 
  - Verificar se é banco de rede (CIP)
  - Se for banco de rede: Pode considerar (alguns bancos aceitam 0 pagas)
  - Se não for banco de rede: **EXCLUIR** da simulação

**Implementação:**
```python
def pode_considerar_emprestimo(emprestimo, cliente, bancos_cip):
    """
    Verifica se um empréstimo pode ser considerado para portabilidade
    """
    # Verificar parcelas pagas
    if emprestimo["parcelas_pagas"] >= 12:
        return True, []
    
    # Se tem menos de 12 pagas, verificar se é banco de rede
    if emprestimo["codigo_banco"] in bancos_cip:
        # Alguns bancos de rede aceitam com menos pagas
        return True, []
    else:
        return False, ["Menos de 12 parcelas pagas e não é banco de rede"]
```

### 3.2 Verificação de Banco na CIP

**Fonte de dados:** Arquivo `bancos.md` - coluna "Na CIP"

**Uso:** Determinar se um banco é considerado "banco de rede" para regras especiais

---

## 4. Regras de Portabilidade por Banco (Camada 2)

### 4.1 Estrutura de Regras

Cada banco que oferece portabilidade terá um conjunto de regras específicas:

**Exemplo - Banrisul:**
```python
regras_banrisul = {
    "bancos_portados": {
        "012": 12,      # INBURSA - mínimo 12 pagas
        "935": 12,      # FACTA - mínimo 12 pagas
        "121": 12,      # AGIBANK - mínimo 12 pagas
        "290": 12,      # PAGBANK - mínimo 12 pagas
        "069": 12,      # CREFISA - mínimo 12 pagas
        "422": 12,      # SAFRA - mínimo 12 pagas
        "029": 25,      # ITAU - mínimo 25 pagas
        "623": 25       # PAN - mínimo 25 pagas
    },
    "bancos_nao_portados": ["330", "335"],  # BARIGUI, DIGIO
    "idade_max": 77,
    "idade_max_meses": 11,
    "idade_max_dias": 29,
    "saldo_minimo": 5000.00,
    "parcela_minima": None,  # Não tem
    "troco_minimo": 200.00,
    "prazo_maximo": 96,
    "taxas": {
        "port_especial": 1.40,
        "port_pura": 1.70,
        "refin": {"min": 1.72, "max": 1.85}
    }
}
```

### 4.2 Verificação de Elegibilidade

Para cada banco destino, verificar se o empréstimo atende:

1. **Banco pode ser portado?**
   - Verificar se código do banco está em `bancos_portados`
   - Verificar se quantidade de parcelas pagas atende o mínimo exigido

2. **Banco não está na lista de não portados?**
   - Verificar se código não está em `bancos_nao_portados`

3. **Idade do cliente?**
   - Verificar se idade está dentro do range permitido
   - Considerar meses e dias se especificado

4. **Saldo devedor?**
   - Verificar se atende saldo mínimo

5. **Outras condições específicas**
   - Parcela mínima
   - Troco mínimo
   - Horário limite (se aplicável)

---

## 5. Coeficientes para Cálculo de Simulação

### 5.1 Estrutura de Coeficientes

Os coeficientes variam por:
- Taxa de juros
- Prazo (96x, 84x, 72x)
- Tipo de operação (Port pura, Port especial, Refin)

**Exemplo de estrutura:**
```python
coeficientes = {
    "96x": {
        "1.40": 0.02345,  # Coeficiente para taxa 1.40% em 96x
        "1.50": 0.02456,
        "1.70": 0.02678,
        # ... outros coeficientes
    },
    "84x": {
        "1.40": 0.02678,
        "1.50": 0.02890,
        # ...
    },
    "72x": {
        "1.40": 0.03123,
        "1.50": 0.03456,
        # ...
    }
}
```

### 5.2 Cálculo do Valor Liberado

```python
def calcular_valor_liberado(saldo_devedor, taxa, prazo, coeficientes):
    """
    Calcula o valor que pode ser liberado na portabilidade
    """
    # Buscar coeficiente mais próximo da taxa
    coeficiente = buscar_coeficiente(taxa, prazo, coeficientes)
    
    # Calcular valor liberado
    valor_liberado = saldo_devedor * coeficiente
    
    return valor_liberado

def calcular_nova_parcela(valor_liberado, prazo):
    """
    Calcula o valor da nova parcela
    """
    nova_parcela = valor_liberado / prazo
    return nova_parcela
```

### 5.3 Fonte dos Coeficientes

**Necessário criar:** Arquivo com tabela de coeficientes
- Pode ser Excel, CSV ou JSON
- Estrutura: Taxa x Prazo = Coeficiente
- Exemplo: `coeficientes_portabilidade.json` ou `coeficientes_portabilidade.xlsx`

---

## 6. Arquitetura de Implementação

### 6.1 Módulos Propostos

```
floracred/
├── app.py                    # Script principal (já existe)
├── coletor_dados.py          # Funções de coleta (já existe parcialmente)
├── regras/
│   ├── __init__.py
│   ├── filtros.py            # Regras de filtragem (Camada 1)
│   ├── portabilidade.py      # Regras de portabilidade por banco (Camada 2)
│   ├── calculadora.py        # Cálculos de simulação
│   └── validadores.py        # Validações gerais
├── dados/
│   ├── bancos.json           # Dados dos bancos (convertido de bancos.md)
│   ├── regras_portabilidade.json  # Regras convertidas do markdown
│   └── coeficientes.json     # Tabela de coeficientes
└── utils/
    ├── __init__.py
    └── conversores.py        # Funções para converter markdown/Excel para JSON
```

### 6.2 Fluxo de Processamento Detalhado

```python
def processar_portabilidade(cliente, emprestimos):
    """
    Processa todas as possibilidades de portabilidade
    """
    # 1. Carregar dados de referência
    bancos_cip = carregar_bancos_cip()
    regras_bancos = carregar_regras_portabilidade()
    coeficientes = carregar_coeficientes()
    
    # 2. Filtrar empréstimos elegíveis (Camada 1)
    emprestimos_validos = []
    for emprestimo in emprestimos:
        pode, motivo = pode_considerar_emprestimo(emprestimo, cliente, bancos_cip)
        if pode:
            emprestimos_validos.append(emprestimo)
        else:
            # Log motivo de exclusão
            pass
    
    # 3. Para cada empréstimo válido, verificar bancos destino (Camada 2)
    simulacoes = []
    for emprestimo in emprestimos_validos:
        for banco_destino, regras in regras_bancos.items():
            # Verificar se pode portar para este banco
            pode_portar, motivos = verificar_elegibilidade(
                emprestimo, cliente, regras
            )
            
            if pode_portar:
                # Calcular simulações
                sim = calcular_simulacoes(
                    emprestimo, banco_destino, regras, coeficientes
                )
                simulacoes.append(sim)
    
    # 4. Ordenar e apresentar melhores opções
    simulacoes_ordenadas = ordenar_por_melhor_opcao(simulacoes)
    
    return simulacoes_ordenadas
```

---

## 7. Estrutura de Arquivos de Dados

### 7.1 bancos.json
```json
{
  "000": {
    "nome": "NEO CRÉDITO",
    "na_cip": false
  },
  "001": {
    "nome": "BANCO DO BRASIL",
    "na_cip": true
  }
  // ...
}
```

### 7.2 regras_portabilidade.json
```json
{
  "Banrisul": {
    "bancos_portados": {
      "012": {"min_pagas": 12},
      "935": {"min_pagas": 12},
      "029": {"min_pagas": 25}
    },
    "bancos_nao_portados": ["330", "335"],
    "condicoes": {
      "saldo_minimo": 5000.00,
      "idade_max": {"anos": 77, "meses": 11, "dias": 29},
      "prazo_maximo": 96,
      "taxas": {
        "port_especial": 1.40,
        "port_pura": 1.70,
        "refin": {"min": 1.72, "max": 1.85}
      }
    }
  }
  // ...
}
```

### 7.3 coeficientes.json
```json
{
  "96x": {
    "1.40": 0.02345,
    "1.50": 0.02456,
    "1.70": 0.02678
  },
  "84x": {
    "1.40": 0.02678,
    "1.50": 0.02890
  },
  "72x": {
    "1.40": 0.03123,
    "1.50": 0.03456
  }
}
```

---

## 8. Pontos de Atenção

### 8.1 Regras Especiais
- Alguns bancos têm regras diferentes por estado (ex: Facta)
- Alguns bancos têm condições especiais para analfabetos
- Horário limite pode afetar elegibilidade (verificar se está dentro do horário)

### 8.2 Cálculos
- Considerar arredondamentos
- Validar se valor liberado não ultrapassa margem disponível
- Calcular economia real (diferença entre parcela atual e nova)

### 8.3 Performance
- Se houver muitos empréstimos e muitos bancos destino, pode gerar muitas simulações
- Considerar cache de resultados
- Ordenar por melhor opção (maior economia, menor taxa, etc.)

---

## 9. Próximos Passos

1. **Criar estrutura de pastas e módulos**
2. **Converter dados de markdown/Excel para JSON**
3. **Implementar funções de filtragem (Camada 1)**
4. **Implementar validações de portabilidade (Camada 2)**
5. **Criar/obter tabela de coeficientes**
6. **Implementar calculadora de simulações**
7. **Integrar tudo no fluxo principal**
8. **Criar relatório/saída das simulações**

---

## 10. Exemplo de Saída Final

```python
resultado = {
    "cliente": {
        "idade": 66,
        "codigo_beneficio": "32"
    },
    "emprestimos_processados": 4,
    "emprestimos_validos": 3,
    "simulacoes": [
        {
            "banco_origem": "INBURSA (012)",
            "banco_destino": "Banrisul",
            "emprestimo_original": {
                "saldo_devedor": 21734.87,
                "parcela_atual": 444.04,
                "parcelas_pagas": 7
            },
            "melhor_opcao": {
                "prazo": "96x",
                "taxa": 1.70,
                "valor_liberado": 50923.45,
                "nova_parcela": 530.45,
                "economia_mensal": -86.41,  # Negativo = aumenta parcela
                "economia_total": -8295.36
            },
            "todas_opcoes": {
                "96x": {...},
                "84x": {...},
                "72x": {...}
            }
        }
        // ... outras simulações
    ],
    "melhores_opcoes_gerais": [
        // Top 3 melhores opções considerando todos os empréstimos
    ]
}
```

---

Esta estrutura permite:
- ✅ Separação clara de responsabilidades
- ✅ Fácil manutenção e atualização de regras
- ✅ Testabilidade (cada camada pode ser testada isoladamente)
- ✅ Escalabilidade (fácil adicionar novos bancos/regras)
- ✅ Flexibilidade (regras podem ser ajustadas sem mudar código)
