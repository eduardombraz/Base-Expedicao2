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
import logging  
  
# Configuração de logs  
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  
  
# Carrega variáveis de ambiente  
from dotenv import load_dotenv  
  
load_dotenv()  
  
# Configurações  
SHOPEE_USER = os.getenv("SHOPEE_USER")  
SHOPEE_PASS = os.getenv("SHOPEE_PASS")  
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit?gid=734921183"  
SHEET_WORKSHEET_NAME = "Base Ended"  
GOOGLE_CREDENTIALS_FILE = "hxh.json"  
  
# Verifica se as credenciais estão carregadas  
if not SHOPEE_USER or not SHOPEE_PASS:  
    logger.error("❌ SHOPEE_USER ou SHOPEE_PASS não definidos no .env")  
    exit(1)  
  
if not Path(GOOGLE_CREDENTIALS_FILE).exists():  
    logger.error(f"❌ Arquivo de credenciais {GOOGLE_CREDENTIALS_FILE} não encontrado.")  
    exit(1)  
  
  
def rename_downloaded_file(download_dir: Path, download_path: Path) -> Path | None:  
    """Renomeia o arquivo baixado para PROD-HH.csv"""  
    try:  
        current_hour = datetime.now().strftime("%H")  
        new_file_name = f"PROD-{current_hour}.csv"  
        new_file_path = download_dir / new_file_name  
  
        if new_file_path.exists():  
            new_file_path.unlink()  
  
        # Espera o arquivo estar completo  
        import time  
        for _ in range(10):  
            if download_path.exists():  
                break  
            time.sleep(0.3)  
  
        shutil.move(str(download_path), str(new_file_path))  
        logger.info(f"✅ Arquivo renomeado para: {new_file_path}")  
        return new_file_path  
    except Exception as e:  
        logger.error(f"❌ Erro ao renomear o arquivo: {e}")  
        return None  
  
  
def update_packing_google_sheets(csv_file_path: Path) -> bool:  
    """Atualiza a planilha Google com os dados do CSV"""  
    try:  
        if not csv_file_path.exists():  
            logger.error(f"❌ Arquivo {csv_file_path} não encontrado.")  
            return False  
  
        scope = [  
            "https://www.googleapis.com/auth/spreadsheets",  
            "https://www.googleapis.com/auth/drive"  
        ]  
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scope)  
        client = gspread.authorize(creds)  
  
        sheet = client.open_by_url(GOOGLE_SHEET_URL)  
        worksheet = sheet.worksheet(SHEET_WORKSHEET_NAME)  
  
        df = pd.read_csv(csv_file_path).fillna("")  
  
        worksheet.clear()  
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())  
  
        logger.info(f"✅ Dados enviados com sucesso para '{SHEET_WORKSHEET_NAME}'")  
        return True  
  
    except Exception as e:  
        logger.error(f"❌ Erro ao atualizar Google Sheets: {e}")  
        return False  
  
  
async def main():  
    download_dir = Path(tempfile.mkdtemp(prefix="shopee_export_"))  
    logger.info(f"📁 Diretório de download temporário criado: {download_dir}")  
  
    async with async_playwright() as p:  
        browser = await p.chromium.launch(  
            headless=False,  
            args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"]  
        )  
        context = await browser.new_context(accept_downloads=True)  
        page = await context.new_page()  
  
        try:  
            # LOGIN  
            logger.info("🌐 Acessando SPX Shopee...")  
            await page.goto("https://spx.shopee.com.br/")  
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)  
  
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill(SHOPEE_USER)  
            await page.locator('xpath=//*[@placeholder="Senha"]').fill(SHOPEE_PASS)  
            await page.locator(  
                'xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button'  
            ).click()  
            await page.wait_for_timeout(8000)  
  
            try:  
                await page.locator('.ssc-dialog-close').click(timeout=5000)  
            except:  
                logger.info("⚠️ Nenhum pop-up encontrado. Pressionando Escape.")  
                await page.keyboard.press("Escape")  
  
            # NAVEGAÇÃO E DOWNLOAD 1: Exportar Trip  
            logger.info("📋 Navegando para exportação de Trip...")  
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")  
            await page.wait_for_timeout(5000)  
  
            # Localiza o botão "Exportar"  
            export_button = page.get_by_role("button", name="Exportar").nth(0)  
            await export_button.wait_for(timeout=10000)  
  
            # Verifica se o botão está habilitado  
            if await export_button.is_disabled():  
                logger.error("❌ Botão 'Exportar' está desativado. Verifique os filtros ou dados.")  
                return  
  
            # Clica no botão  
            logger.info("📤 Clicando no botão 'Exportar'...")  
            await export_button.click()  
            await page.wait_for_timeout(5000)  # Espera 5s para o download iniciar  
  
            # Tenta capturar o download com timeout  
            try:  
                logger.info("📥 Esperando download iniciar (120s)...")  
                async with page.expect_download(timeout=120000):  
                    await export_button.click()  # Clica novamente para garantir  
                download = await page.wait_for_download(timeout=120000)  
            except Exception as e:  
                logger.error(f"❌ Falha ao esperar download: {e}")  
                logger.info("⚠️ Tentando verificar se há downloads pendentes...")  
                pending_downloads = context.downloads()  
                if pending_downloads:  
                    logger.info(f"📦 {len(pending_downloads)} download(s) pendente(s) encontrado(s).")  
                else:  
                    logger.warning("🚫 Nenhum download foi iniciado. Verifique o SPX.")  
                return  
  
            # Salva o arquivo  
            download_path = download_dir / download.suggested_filename  
            await download.save_as(download_path)  
  
            # Renomeia  
            new_file_path = rename_downloaded_file(download_dir, download_path)  
            if not new_file_path:  
                logger.error("❌ Falha ao renomear o arquivo. Encerrando.")  
                return  
  
            # DOWNLOAD 2: Task Center  
            logger.info("📥 Baixando arquivo do Task Center...")  
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")  
            await page.wait_for_timeout(5000)  
  
            task_button = page.get_by_role("button", name="Baixar").nth(0)  
            await task_button.wait_for(timeout=10000)  
  
            if await task_button.is_disabled():  
                logger.warning("⚠️ Botão 'Baixar' está desativado no Task Center.")  
            else:  
                await task_button.click()  
                await page.wait_for_timeout(5000)  
  
                try:  
                    async with page.expect_download(timeout=120000):  
                        await task_button.click()  
                    download2 = await page.wait_for_download(timeout=120000)  
                    download_path2 = download_dir / download2.suggested_filename  
                    await download2.save_as(download_path2)  
  
                    new_file_path2 = rename_downloaded_file(download_dir, download_path2)  
                    if not new_file_path2:  
                        logger.warning("⚠️ Falha ao renomear o segundo arquivo. Continuando...")  
                except Exception as e:  
                    logger.error(f"❌ Falha no download do Task Center: {e}")  
  
            # Atualiza Google Sheets  
            logger.info("🔄 Atualizando Google Sheets...")  
            success = update_packing_google_sheets(new_file_path or new_file_path2)  
            if success:  
                logger.info("🎉 Processo concluído com sucesso!")  
            else:  
                logger.error("❌ Falha ao atualizar a planilha.")  
  
        except Exception as e:  
            logger.error(f"❌ Erro crítico durante o processo: {e}")  
        finally:  
            await browser.close()  
            try:  
                shutil.rmtree(download_dir)  
                logger.info(f"🗑️ Diretório temporário removido: {download_dir}")  
            except Exception as e:  
                logger.warning(f"⚠️ Não foi possível remover o diretório temporário: {e}")  
  
  
if __name__ == "__main__":  
    asyncio.run(main()
