import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

DOWNLOAD_DIR = "/tmp"

==============================
Funções de renomear arquivos
==============================
def rename_downloaded_file(download_dir, download_path):
try:
# nome único para evitar colisão
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
new_file_name = f"PROD-{stamp}.csv"
new_file_path = os.path.join(download_dir, new_file_name)
if os.path.exists(new_file_path):
os.remove(new_file_path)
shutil.move(download_path, new_file_path)
print(f"Arquivo salvo como: {new_file_path}")
return new_file_path
except Exception as e:
print(f"Erro ao renomear o arquivo: {e}")
return None

==============================
Funções de atualização Google Sheets
==============================
def read_csv_robusto(csv_file_path):
# Detecta encoding e tenta diferentes separadores
try:
import chardet
with open(csv_file_path, "rb") as f:
raw = f.read(1000000)
enc = chardet.detect(raw).get("encoding") or "utf-8"
except Exception:
enc = "utf-8"

# ordem de tentativas de encoding  
encodings = [enc, "utf-8", "latin-1", "cp1252"]  
# ordem de separadores comuns  
seps = [",", ";", "\t"]  

last_err = None  
for encoding in encodings:  
    for sep in seps:  
        try:  
            df = pd.read_csv(csv_file_path, encoding=encoding, sep=sep)  
            # heurística simples: se só veio 1 coluna e contém separador, tenta outro  
            if df.shape[1] == 1:  
                continue  
            return df  
        except Exception as e:  
            last_err = e  
            continue  

# última tentativa: ler sem sep (padrão) com o melhor encoding detectado  
try:  
    df = pd.read_csv(csv_file_path, encoding=encodings[0])  
    return df  
except Exception as e:  
    raise RuntimeError(f"Falha ao ler CSV com encodings {encodings} e seps {seps}: {e or last_err}")  
def update_packing_google_sheets(csv_file_path):
try:
if not os.path.exists(csv_file_path):
print(f"Arquivo {csv_file_path} não encontrado.")
return

    df = read_csv_robusto(csv_file_path).fillna("")  

    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]  
    creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)  
    client = gspread.authorize(creds)  
    sheet1 = client.open_by_url(  
        "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit?gid=734921183#gid=734921183"  
    )  
    worksheet1 = sheet1.worksheet("Base Ended")  
    worksheet1.clear()  
    worksheet1.update([df.columns.values.tolist()] + df.values.tolist())  
    print("Arquivo enviado com sucesso para a aba 'Base Ended'.")  
except Exception as e:  
    print(f"Erro durante o processo: {e}")  
==============================
Fluxo principal Playwright
==============================
async def main():
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
async with async_playwright() as p:
browser = await p.chromium.launch(
headless=False,
args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"]
)
context = await browser.new_context(accept_downloads=True)
page = await context.new_page()

    try:  
        # LOGIN  
        await page.goto("https://spx.shopee.com.br/")  
        await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)  
        await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops115950')  
        await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')  
        await page.locator(  
            'xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button'  
        ).click()  
        await page.wait_for_timeout(15000)  
        try:  
            await page.locator('.ssc-dialog-close').click(timeout=5000)  
        except:  
            print("Nenhum pop-up foi encontrado.")  
            await page.keyboard.press("Escape")  

        # NAVEGAÇÃO E DOWNLOAD 1  
        await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")  
        await page.wait_for_timeout(8000)  
        await page.locator('xpath=/html[1]/body[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[4]/span[1]').click()  
        await page.wait_for_timeout(8000)  
        await page.get_by_role("button", name="Exportar").nth(0).click()  
        await page.wait_for_timeout(200000)  

        # Botão de download 1  
        await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")  
        await page.wait_for_timeout(8000)  
        async with page.expect_download() as download_info:  
            await page.get_by_role("button", name="Baixar").nth(0).click()  
        download = await download_info.value  
        download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)  
        await download.save_as(download_path)  
        new_file_path = rename_downloaded_file(DOWNLOAD_DIR, download_path)  

        # Atualizar Google Sheets  
        if new_file_path:  
            update_packing_google_sheets(new_file_path)  

        print("Dados atualizados com sucesso.")  
    except Exception as e:  
        print(f"Erro durante o processo: {e}")  
    finally:  
        await browser.close()  
if name == "main":
asyncio.run(main())
