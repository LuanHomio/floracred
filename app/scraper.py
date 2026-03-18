import os
import time
import logging

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from app.models import DadosBeneficio, Emprestimo, DadosCliente

logger = logging.getLogger(__name__)

LOGIN_URL = "https://gestao.sistemacorban.com.br/index.php/auth/login"
CORBAN_USER = os.getenv("CORBAN_USER", "")
CORBAN_PASS = os.getenv("CORBAN_PASS", "")


def create_driver() -> uc.Chrome:
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    driver = uc.Chrome(options=options, version_main=None)
    driver.set_page_load_timeout(60)
    return driver


def login(driver: uc.Chrome) -> None:
    logger.info("Acessando pagina de login")
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)

    user_input = wait.until(EC.presence_of_element_located((By.ID, "exten")))
    password_input = wait.until(EC.presence_of_element_located((By.ID, "password")))

    user_input.clear()
    user_input.send_keys(CORBAN_USER)

    password_input.clear()
    password_input.send_keys(CORBAN_PASS)

    login_button = wait.until(EC.element_to_be_clickable((By.ID, "button-sigin")))
    login_button.click()
    logger.info("Login enviado")

    # Alerta de outro usuario logado
    try:
        alert = WebDriverWait(driver, 5).until(EC.alert_is_present())
        alert.accept()
        time.sleep(2)
    except TimeoutException:
        pass

    # Modal NPS
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "modalNpsAtivo"))
        )
        ver_depois = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[@id='modalNpsAtivo']//a[normalize-space()='Ver depois']")
            )
        )
        ver_depois.click()
        time.sleep(1)
    except TimeoutException:
        pass

    time.sleep(3)
    logger.info("Login concluido")


def buscar_por_cpf(driver: uc.Chrome, cpf: str) -> None:
    wait = WebDriverWait(driver, 20)
    search_input = wait.until(
        EC.element_to_be_clickable((By.ID, "dataToReceptivo"))
    )
    search_input.clear()
    search_input.send_keys(cpf)

    buscar_button = wait.until(
        EC.element_to_be_clickable((By.ID, "btnConsultaClienteRapido"))
    )
    buscar_button.click()
    logger.info(f"Busca por CPF enviada")
    time.sleep(3)


def selecionar_primeiro_beneficio(driver: uc.Chrome) -> None:
    wait = WebDriverWait(driver, 20)
    beneficio_button = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button.btn.card--selecionar-beneficio")
        )
    )
    beneficio_button.click()
    logger.info("Primeiro beneficio selecionado")
    time.sleep(3)


def visualizar_dados_cliente(driver: uc.Chrome) -> None:
    wait = WebDriverWait(driver, 20)
    visualizar_button = wait.until(
        EC.element_to_be_clickable((By.ID, "btnOcultar"))
    )
    visualizar_button.click()
    time.sleep(2)


def coletar_dados_beneficio(driver: uc.Chrome) -> DadosBeneficio:
    wait = WebDriverWait(driver, 20)
    dados = DadosBeneficio()

    try:
        idade_input = wait.until(
            EC.presence_of_element_located((By.ID, "idadeCliente"))
        )
        dados.idade = int(idade_input.get_attribute("value"))
    except (TimeoutException, ValueError, TypeError):
        pass

    try:
        nascimento_el = wait.until(
            EC.presence_of_element_located((By.ID, "cliNascimento"))
        )
        dados.nascimento = nascimento_el.text.strip()
    except TimeoutException:
        pass

    try:
        especie_input = wait.until(
            EC.presence_of_element_located((By.ID, "especieNB"))
        )
        especie_texto = especie_input.get_attribute("value")
        if especie_texto:
            dados.codigo_beneficio = especie_texto.split(" - ")[0].strip()
            dados.especie = especie_texto
    except TimeoutException:
        pass

    logger.info(f"Beneficio coletado: idade={dados.idade}, especie={dados.codigo_beneficio}")
    return dados


def coletar_emprestimos(driver: uc.Chrome) -> list[Emprestimo]:
    wait = WebDriverWait(driver, 20)
    emprestimos = []

    try:
        container = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[@id='form-propostas']/div/section/div/div[1]")
            )
        )

        index = 0
        while True:
            try:
                linha = container.find_element(By.ID, f"linha_{index}")
                emp = Emprestimo()

                try:
                    el = linha.find_element(By.ID, f"linhaBanco--taxa_{index}")
                    emp.taxa_juros = float(el.get_attribute("value"))
                except Exception:
                    pass

                try:
                    el = linha.find_element(By.ID, f"linhaBanco--banco_{index}")
                    emp.codigo_banco = el.get_attribute("value")
                except Exception:
                    pass

                try:
                    el = linha.find_element(By.ID, f"linhaBanco--saldoD_{index}")
                    emp.saldo_devedor = float(el.get_attribute("value"))
                except Exception:
                    pass

                try:
                    el = linha.find_element(By.ID, f"linhaBanco--pagas_{index}")
                    emp.parcelas_pagas = int(el.get_attribute("value"))
                except Exception:
                    pass

                try:
                    el = linha.find_element(By.ID, f"valorParcelaEmp_{index}")
                    valor_texto = el.text.strip().replace(".", "").replace(",", ".")
                    emp.valor_parcela = float(valor_texto)
                except Exception:
                    pass

                try:
                    el = linha.find_element(
                        By.CSS_SELECTOR, "span.linha_banco.text--banco"
                    )
                    banco_texto = el.text.strip()
                    if "Banco:" in banco_texto:
                        banco_texto = banco_texto.split("Banco:")[-1].strip()
                    emp.nome_banco = banco_texto
                except Exception:
                    pass

                emprestimos.append(emp)
                index += 1
            except Exception:
                break

    except TimeoutException:
        logger.warning("Container de emprestimos nao encontrado")
    except Exception as e:
        logger.error(f"Erro ao coletar emprestimos: {e}")

    logger.info(f"{len(emprestimos)} emprestimos coletados")
    return emprestimos


def coletar_dados_cliente(cpf: str) -> DadosCliente:
    """Fluxo completo: login -> busca CPF -> coleta dados."""
    driver = None
    try:
        driver = create_driver()
        login(driver)
        buscar_por_cpf(driver, cpf)
        selecionar_primeiro_beneficio(driver)
        visualizar_dados_cliente(driver)

        beneficio = coletar_dados_beneficio(driver)
        time.sleep(2)
        emprestimos = coletar_emprestimos(driver)

        return DadosCliente(
            cpf=cpf,
            beneficio=beneficio,
            emprestimos=emprestimos,
        )
    except Exception as e:
        logger.exception(f"Erro ao coletar dados do CPF")
        return DadosCliente(cpf=cpf, erro=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
