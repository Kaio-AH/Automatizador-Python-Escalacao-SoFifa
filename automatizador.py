import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import pandas as pd
import re
import typer

app = typer.Typer()  # Inicializa Typer CLI

# ======= Funções de formação e seleção ======= #
def formacao_para_posicoes(formation_str):
    mapping = {
        '4-3-3': ['GK','CB','CB','LB','RB','CM','CM','CM','LW','ST','RW'],
        '4-4-2': ['GK','CB','CB','LB','RB','LM','RM','CM','CM','ST','ST'],
        '3-4-3': ['GK','CB','CB','CB','LM','RM','CM','CM','LW','ST','RW'],
        '3-5-2': ['GK','CB','CB','CB','LM','RM','CM','CM','CAM','ST','ST'],
        '4-2-3-1': ['GK','CB','CB','LB','RB','CDM','CDM','LM','RM','CAM','ST'],
        '5-3-2': ['GK','CB','CB','CB','LWB','RWB','CM','CM','CM','ST','ST'],
        '2-5-2-1': ['GK', 'CB', 'CB', 'LM', 'RM', 'CM', 'CM', 'CM', 'CAM', 'CAM', 'ST'],
        '4-2-4': ['GK', 'CB', 'CB', 'LB', 'RB', 'CM', 'CM', 'LW', 'RW', 'ST', 'ST'],
        '5-4-1': ['GK', 'CB', 'CB', 'CB', 'RB', 'LB', 'CM', 'CM', 'LM', 'RM', 'ST'],
        '4-4-2 (fechado)': ['GK', 'CB', 'CB', 'LB', 'RB', 'CM', 'CM', 'CAM', 'CAM', 'ST', 'ST'],
        '4-3-1-2': ['GK', 'CB', 'CB', 'LB', 'RB', 'CDM', 'CM', 'CM', 'CAM', 'ST', 'ST']
    }
    return mapping.get(formation_str, [])

def selecionar_por_posicao(df, posicoes):
    escalação = []
    df_copy = df.copy()
    df_copy['PosList'] = df_copy['Pos'].astype(str).str.split(',')

    for pos in posicoes:
        candidatos = df_copy[df_copy['PosList'].apply(lambda lst: isinstance(lst, list) and pos in lst)]
        if not candidatos.empty:
            melhor = candidatos.sort_values(by='OVR', ascending=False).iloc[0]
            escalação.append((pos, melhor['Name'], melhor['OVR'], melhor['Age']))
            df_copy = df_copy.drop(melhor.name)
        else:
            escalação.append((pos, "Não encontrado", 0, 0))
    return escalação

# ======= Função principal ======= #
async def montar_melhor_escalação(clube_url, formacao):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        try:
            await page.goto(clube_url, timeout=60000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass

            try:
                await page.click("text=Accept", timeout=4000)
            except:
                pass

            for _ in range(3):
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(1200)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            linhas_jogadores = soup.find_all("tr")
            jogadores = []

            pos_validas = ['GK','CB','LB','RB','LWB','RWB','CDM','CM','CAM','LM','RM','LW','RW','CF','ST']
            token_re = re.compile(r'(GK|CB|LB|RB|LWB|RWB|CDM|CM|CAM|LM|RM|LW|RW|CF|ST)')

            for linha in linhas_jogadores:
                try:
                    link = linha.find("a", href=re.compile(r"/player/\d+"))
                    if not link:
                        continue
                    nome = link.get_text(strip=True)
                    name_td = link.find_parent("td")
                    if not name_td:
                        continue
                    spans = name_td.find_all("span")
                    posicoes = [s.get_text(strip=True) for s in spans if s.get_text(strip=True) in pos_validas]
                    if not posicoes:
                        txt = name_td.get_text(separator=' ', strip=True)
                        txt_norm = re.sub(r'\s+', ' ', txt)
                        nome_norm = re.sub(r'\s+', ' ', nome)
                        resto = txt_norm[len(nome_norm):].strip() if txt_norm.startswith(nome_norm) else txt_norm
                        posicoes = token_re.findall(resto)
                    if not posicoes:
                        continue
                    idade = next((int(td.get_text(strip=True)) for td in linha.find_all("td") if td.get_text(strip=True).isdigit() and 15 <= int(td.get_text(strip=True)) <= 45), None)
                    if idade is None:
                        continue
                    ovr = next((int(td.get_text(strip=True)) for td in linha.find_all("td") if td.get_text(strip=True).isdigit() and 40 <= int(td.get_text(strip=True)) <= 99 and int(td.get_text(strip=True)) != idade), None)
                    if ovr is None:
                        continue
                    jogadores.append({"Name": nome, "Pos": ",".join(posicoes), "OVR": ovr, "Age": idade})
                except:
                    continue

            if not jogadores:
                print("Nenhum jogador foi encontrado.")
                await browser.close()
                return []

            df = pd.DataFrame(jogadores)
            posicoes = formacao_para_posicoes(formacao)
            escalação = selecionar_por_posicao(df, posicoes)

            await browser.close()
            return escalação

        except Exception as e:
            print(f"Erro durante execução: {e}")
            await browser.close()
            return []

# ======= CLI com Typer ======= #
@app.command()
def main(clube: str = typer.Option(..., help="URL do clube no sofifa.com"),
         formacao: str = typer.Option(..., help="Formação desejada, ex: '4-3-1-2'")):

    print(f"Buscando jogadores do clube: {clube}")
    print(f"Formação desejada: {formacao}")
    print("-" * 50)

    escalação = asyncio.run(montar_melhor_escalação(clube, formacao))

    if escalação:
        print(f"\nMelhor escalação para {formacao}:")
        print("-" * 50)
        for pos, nome, ovr, idade in escalação:
            if ovr > 0:
                print(f"{pos:4}: {nome:25} (OVR {ovr:2}, {idade:2} anos)")
            else:
                print(f"{pos:4}: {nome:25}")
        ovrs_validos = [ovr for pos, nome, ovr, idade in escalação if ovr > 0]
        if ovrs_validos:
            media_ovr = sum(ovrs_validos) / len(ovrs_validos)
            print(f"\nMédia OVR do time: {media_ovr:.1f}")
    else:
        print("Não foi possível montar a escalação.")

if __name__ == "__main__":
    app()
