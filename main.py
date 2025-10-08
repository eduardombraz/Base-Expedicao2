import asyncio  
import os  
import shutil  
import tempfile  
from datetime import datetime  
from pathlib import Path  
  
import pandas as pd  
from google.oauth2.service_account import Credentials  
import gspread  
from playwright.async_api import async_playwright  
  
  
# ==============================  
# Configuração de Segurança (usar .env)  
# ==============================  
from dotenv import load_dotenv  
  
load_dotenv()  # Carrega variáveis de ambiente do .env  
  
SHOPEE_USER = os.getenv("Ops115950")  
SHOPEE_PASS = os.getenv("@Shopee123")  
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit?gid=734921183"  
SHEET_WORKSHEET_NAME = "Base Ended"  
GOOGLE_CREDENTIALS_FILE = "hxh.json"  # Arquivo JSON de serviço do Google  
  
# ==============================  
# Funções auxiliares  
# ==============================  
  
def rename_downloaded_file(download_dir: Path, download_path: Path) -> Path | None:  
    """Renomeia o arquivo baixado para PROD-HH.csv"""  
    try:  
        current_hour = datetime.now().strftime("%H")  
        new_file_name = f"PROD-{current_hour}.csv"  
        new_file_path = download_dir / new_file_name  
  
        # Remove arquivo antigo, se existir  
        if new_file_path.exists():  
            new_file_path.unlink()  
  
        # Espera o arquivo estar completo (segurança)  
        for _ in range(10):  
            if download_path.exists():  
                break  
            asyncio.get_event_loop().run_in_executor(None, lambda: None)  # Simula espera  
            import time  
            time.sleep(0.3)  
  
        # Move o arquivo  
        shutil.move(str(download_path), str(new_file_path))  
        print(f"✅ Arquivo renomeado para: {new_file_path}")  
        return new_file_path  
    except Exception as e:  
        print(f"❌ Erro ao renomear o arquivo: {e}")  
        return None  
  
  
def update_packing_google_sheets(csv_file_path: Path) -> bool:  
    """Atualiza a planilha Google com os dados do CSV"""  
    try:  
        if not csv_file_path.exists():  
            print(f"❌ Arquivo {csv_file_path} não encontrado.")  
            return False  
  
        scope = [  
            "https://www.googleapis.com/auth/spreadsheets",  
            "https://www.googleapis.com/auth/drive"  
        ]  
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scope)  
        client = gspread.authorize(creds)  
  
        sheet = client.open_by_url(SHOPEE_USER)  
        worksheet = sheet.worksheet(SHEET_WORKSHEET_NAME)  
  
        df = pd.read_csv(csv_file_path).fillna("")  
  
        # Limpa e atualiza  
        worksheet.clear()  
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())  
  
        print(f"✅ Dados enviados com sucesso para '{SHEET_WORKSHEET_NAME}'")  
        return True  
  
    except Exception as e:  
        print(f"❌ Erro ao atualizar Google Sheets: {e}")  
        return False  
  
  
# ==============================  
# Fluxo principal Playwright  
# ==============================  
async def main():  
    # Usa um diretório temporário seguro  
    download_dir = Path(tempfile.mkdtemp(prefix="shopee_export_"))  
    print(f"📁 Diretório de download temporário criado: {download_dir}")  
  
    async with async_playwright() as p:  
        browser = await p.chromium.launch(  
            headless=False,  
            args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"]  
        )  
        context = await browser.new_context(accept_downloads=True)  
        page = await context.new_page()  
  
        try:  
            # LOGIN  
            print("🌐 Acessando SPX Shopee...")  
            await page.goto("https://spx.shopee.com.br/")  
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)  
  
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill(SHOPEE_USER)  
            await page.locator('xpath=//*[@placeholder="Senha"]').fill(SHOPEE_PASS)  
            await page.locator(  
                'xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button'  
            ).click()  
            await page.wait_for_timeout(8000)  
  
            # Fecha popup, se aparecer  
            try:  
                await page.locator('.ssc-dialog-close').click(timeout=5000)  
            except:  
                print("⚠️ Nenhum pop-up encontrado. Pressionando Escape.")  
                await page.keyboard.press("Escape")  
  
            # NAVEGAÇÃO E DOWNLOAD 1: Exportar Trip  
            print("📋 Navegando para exportação de Trip...")  
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")  
            await page.wait_for_timeout(5000)  
  
            # Clica no botão de exportar  
            await page.locator(  
                'xpath=/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[4]/span[1]'  
            ).click()  
            await page.wait_for_timeout(5000)  
  
            # Espera o download com timeout real  
            print("📤 Iniciando download de 'Exportar'...")  
            async with page.expect_download(timeout=8000):  # 2 minutos  
                await page.get_by_role("button", name="Exportar").nth(0).click()  
  
            download = await page.wait_for_download(timeout=120000)  
            download_path = download_dir / download.suggested_filename  
            await download.save_as(download_path)  
  
            # Renomeia o arquivo  
            new_file_path = rename_downloaded_file(download_dir, download_path)  
            if not new_file_path:  
                print("❌ Falha ao renomear o arquivo. Encerrando.")  
                return  
  
            # NAVEGAÇÃO E DOWNLOAD 2: Export Task Center  
            print("📥 Baixando arquivo do Task Center...")  
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")  
            await page.wait_for_timeout(5000)  
  
            async with page.expect_download(timeout=12000):  
                await page.get_by_role("button", name="Baixar").nth(0).click()  
  
            download2 = await page.wait_for_download(timeout=120000)  
            download_path2 = download_dir / download2.suggested_filename  
            await download2.save_as(download_path2)  
  
            # Renomeia o segundo arquivo (opcional, ou pode usar o mesmo nome)  
            new_file_path2 = rename_downloaded_file(download_dir, download_path2)  
            if not new_file_path2:  
                print("❌ Falha ao renomear o segundo arquivo. Continuando...")  
  
            # Atualiza Google Sheets com o primeiro arquivo (ou o mais recente)  
            print("🔄 Atualizando Google Sheets...")  
            success = update_packing_google_sheets(new_file_path or new_file_path2)  
            if success:  
                print("🎉 Processo concluído com sucesso!")  
            else:  
                print("⚠️ Falha ao atualizar a planilha.")  
  
        except Exception as e:  
            print(f"❌ Erro crítico durante o processo: {e}")  
        finally:  
            await browser.close()  
            # Limpa o diretório temporário (opcional: pode manter para debug)  
            try:  
                shutil.rmtree(download_dir)  
                print(f"🗑️ Diretório temporário removido: {download_dir}")  
            except Exception as e:  
                print(f"⚠️ Não foi possível remover o diretório temporário: {e}")  
  
  
# ==============================  
# Execução principal  
# ==============================  
if __name__ == "__main__":  
    # Verifica se as variáveis de ambiente estão definidas  
    if not SHOPEE_USER or not SHOPEE_PASS:  
        print("❌ Erro: SHOPEE_USER ou SHOPEE_PASS não definidos no .env")  
        exit(1)  
  
    if not Path(GOOGLE_CREDENTIALS_FILE).exists():  
        print(f"❌ Erro: Arquivo de credenciais do Google ({GOOGLE_CREDENTIALS_FILE}) não encontrado.")  
        exit(1)  
  
    asyncio.run(main())  
