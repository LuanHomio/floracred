from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time

LOGIN_URL = "https://gestao.sistemacorban.com.br/index.php/auth/login"
USERNAME = "flora@25599"
PASSWORD = "Verao@26"


def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    return driver


def login(driver):
    print("Acessando página de login")
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)

    user_input = wait.until(EC.presence_of_element_located((By.ID, "exten")))
    password_input = wait.until(EC.presence_of_element_located((By.ID, "password")))

    user_input.clear()
    user_input.send_keys(USERNAME)
    print("Login preenchido")

    password_input.clear()
    password_input.send_keys(PASSWORD)
    print("Senha preenchida")

    login_button = wait.until(
        EC.element_to_be_clickable((By.ID, "button-sigin"))
    )
    login_button.click()
    print("Clicou em entrar")

    try:
        print("Verificando se tem outro usuário logado")
        alert = WebDriverWait(driver, 5).until(EC.alert_is_present())
        print("Alerta encontrado, aceitando")
        alert.accept()
        time.sleep(2)
    except TimeoutException:
        print("Não há outro usuário logado")

    try:
        print("Verificando modal inicial")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "modalNpsAtivo"))
        )
        print("Modal inicial encontrado")
        ver_depois = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[@id='modalNpsAtivo']//a[normalize-space()='Ver depois']")
            )
        )
        print("Clicando em Ver depois")
        ver_depois.click()
        time.sleep(1)
    except TimeoutException:
        print("Modal inicial não encontrado")

    time.sleep(5)


def buscar_por_cpf(driver, cpf):
    print("Preenchendo CPF de busca")
    wait = WebDriverWait(driver, 20)
    search_input = wait.until(
        EC.element_to_be_clickable((By.ID, "dataToReceptivo"))
    )
    search_input.clear()
    search_input.send_keys(cpf)
    print("CPF preenchido")


def clicar_buscar(driver):
    print("Clicando no botão Buscar")
    wait = WebDriverWait(driver, 20)
    buscar_button = wait.until(
        EC.element_to_be_clickable((By.ID, "btnConsultaClienteRapido"))
    )
    buscar_button.click()
    print("Botão Buscar clicado")


def selecionar_primeiro_beneficio(driver):
    print("Aguardando benefícios aparecerem")
    wait = WebDriverWait(driver, 20)
    beneficio_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.card--selecionar-beneficio"))
    )
    print("Benefício encontrado, clicando no primeiro")
    beneficio_button.click()
    print("Primeiro benefício selecionado")


def visualizar_dados_cliente(driver):
    print("Clicando no botão para visualizar dados")
    wait = WebDriverWait(driver, 20)
    visualizar_button = wait.until(
        EC.element_to_be_clickable((By.ID, "btnOcultar"))
    )
    visualizar_button.click()
    print("Dados do cliente visualizados")
    time.sleep(2)


def coletar_dados_beneficio(driver):
    print("Coletando dados do benefício")
    wait = WebDriverWait(driver, 20)
    
    dados = {}
    
    try:
        idade_input = wait.until(
            EC.presence_of_element_located((By.ID, "idadeCliente"))
        )
        idade = int(idade_input.get_attribute("value"))
        dados["idade"] = idade
        print(f"Idade coletada: {idade} anos")
        
        nascimento_element = wait.until(
            EC.presence_of_element_located((By.ID, "cliNascimento"))
        )
        dados["nascimento"] = nascimento_element.text.strip()
    except (TimeoutException, ValueError) as e:
        print(f"Não foi possível coletar a idade: {e}")
    
    try:
        especie_input = wait.until(
            EC.presence_of_element_located((By.ID, "especieNB"))
        )
        especie_texto = especie_input.get_attribute("value")
        if especie_texto:
            codigo_beneficio = especie_texto.split(" - ")[0].strip()
            dados["codigo_beneficio"] = codigo_beneficio
            dados["especie"] = especie_texto
            print(f"Código do benefício coletado: {codigo_beneficio}")
    except TimeoutException as e:
        print(f"Não foi possível coletar o código do benefício: {e}")
    
    return dados


def coletar_emprestimos_consignados(driver):
    print("Coletando empréstimos consignados")
    wait = WebDriverWait(driver, 20)
    
    emprestimos = []
    
    try:
        container_emprestimos = wait.until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='form-propostas']/div/section/div/div[1]"))
        )
        print("Container de empréstimos encontrado")
        
        index = 0
        while True:
            try:
                linha_id = f"linha_{index}"
                linha_element = container_emprestimos.find_element(By.ID, linha_id)
                
                emprestimo = {}
                
                try:
                    taxa_input = linha_element.find_element(By.ID, f"linhaBanco--taxa_{index}")
                    emprestimo["taxa_juros"] = float(taxa_input.get_attribute("value"))
                except:
                    pass
                
                try:
                    banco_input = linha_element.find_element(By.ID, f"linhaBanco--banco_{index}")
                    emprestimo["codigo_banco"] = banco_input.get_attribute("value")
                except:
                    pass
                
                try:
                    saldo_input = linha_element.find_element(By.ID, f"linhaBanco--saldoD_{index}")
                    emprestimo["saldo_devedor"] = float(saldo_input.get_attribute("value"))
                except:
                    pass
                
                try:
                    pagas_input = linha_element.find_element(By.ID, f"linhaBanco--pagas_{index}")
                    emprestimo["parcelas_pagas"] = int(pagas_input.get_attribute("value"))
                except:
                    pass
                
                try:
                    parcela_span = linha_element.find_element(By.ID, f"valorParcelaEmp_{index}")
                    valor_texto = parcela_span.text.strip().replace(".", "").replace(",", ".")
                    emprestimo["valor_parcela"] = float(valor_texto)
                except:
                    pass
                
                try:
                    banco_span = linha_element.find_element(By.CSS_SELECTOR, "span.linha_banco.text--banco")
                    banco_texto = banco_span.text.strip()
                    if "Banco:" in banco_texto:
                        banco_texto = banco_texto.split("Banco:")[-1].strip()
                    emprestimo["nome_banco"] = banco_texto
                except:
                    pass
                
                emprestimos.append(emprestimo)
                print(f"Empréstimo {index} coletado")
                index += 1
                
            except:
                break
        
        print(f"Total de {len(emprestimos)} empréstimos coletados")
        
    except TimeoutException:
        print("Container de empréstimos não encontrado")
    except Exception as e:
        print(f"Erro ao coletar empréstimos: {e}")
    
    return emprestimos


def main():
    cpf = input("Digite o CPF do cliente: ").strip()
    driver = create_driver()
    try:
        login(driver)
        if cpf:
            buscar_por_cpf(driver, cpf)
            clicar_buscar(driver)
            time.sleep(3)
            selecionar_primeiro_beneficio(driver)
            time.sleep(3)
            visualizar_dados_cliente(driver)
            dados_beneficio = coletar_dados_beneficio(driver)
            print(f"Dados do benefício coletados: {dados_beneficio}")
            time.sleep(2)
            emprestimos = coletar_emprestimos_consignados(driver)
            print(f"Empréstimos coletados: {emprestimos}")
            print("Aguardando 30 segundos para visualização...")
            time.sleep(30)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

