import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import aiohttp
import json
import os

# ==========================================
# CONFIGURAÇÕES INICIAIS
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ ERRO: Falta a variável de ambiente (BOT_TOKEN).")
    exit(1)

if not os.path.exists("data"):
    os.makedirs("data")

CONFIG_FILE = "data/config.json"

def load_config():
    default_config = {
        "owner_id": None, "user_token": None, "rpc_active": False,
        "rpc_state": {
            "name": "Nexzy Store", "application_id": "1525126100034785400",
            "details": "A navegar...", "state": "Modo Furtivo",
            "large_image": "", "large_text": "Loja Oficial",
            "small_image": "", "small_text": "Online"
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if "rpc_state" not in data: data["rpc_state"] = default_config["rpc_state"]
                else:
                    for key in default_config["rpc_state"]:
                        if key not in data["rpc_state"]: data["rpc_state"][key] = default_config["rpc_state"][key]
                return data
        except json.JSONDecodeError: return default_config
    return default_config

def save_config(data):
    with open(CONFIG_FILE, "w") as f: json.dump(data, f, indent=4)

config = load_config()
gateway_task = None
gateway_ws = None

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# FUNÇÃO DE CONVERSÃO COM DEBUG
# ==========================================
async def converte_link_discord(token, app_id, url):
    if not url or not url.startswith("http"): return url
    
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": token, "Content-Type": "application/json"}
        payload = {"urls": [url]}
        url_api = f"https://discord.com/api/v9/oauth2/applications/{app_id}/external-assets"
        
        try:
            async with session.post(url_api, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Retorna o mp:external/..
                    return data[0].get("external_asset_path", url)
                else:
                    error_text = await resp.text()
                    print(f"❌ DEBUG API: Status {resp.status} | Resposta: {error_text}")
                    return url
        except Exception as e:
            print(f"❌ DEBUG ERRO: {e}")
            return url

# ==========================================
# GATEWAY
# ==========================================
def get_presence_payload():
    state = config["rpc_state"]
    assets = {}
    if state["large_image"]:
        assets["large_image"] = state["large_image"]
        assets["large_text"] = state["large_text"]
    if state["small_image"]:
        assets["small_image"] = state["small_image"]
        assets["small_text"] = state["small_text"]
    return {
        "status": "online", "since": 0,
        "activities": [{"name": state["name"], "type": 0, "application_id": state["application_id"],
                        "details": state["details"], "state": state["state"], "assets": assets if assets else None}],
        "afk": False
    }

async def send_heartbeat(ws, interval):
    while not ws.closed:
        await asyncio.sleep(interval)
        try: await ws.send_json({"op": 1, "d": None})
        except: break

async def user_gateway():
    global gateway_ws
    while config.get("rpc_active", False):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect('wss://gateway.discord.gg/?v=10&encoding=json') as ws:
                    gateway_ws = ws
                    payload = {"op": 2, "d": {"token": config["user_token"], "capabilities": 16381,
                                            "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
                                            "presence": get_presence_payload()}}
                    await ws.send_json(payload)
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if data['op'] == 10:
                                bot.loop.create_task(send_heartbeat(ws, data['d']['heartbeat_interval'] / 1000))
        except: await asyncio.sleep(5)

def restart_gateway():
    global gateway_task, gateway_ws
    if gateway_ws and not gateway_ws.closed: bot.loop.create_task(gateway_ws.close())
    if gateway_task: gateway_task.cancel()
    if config.get("rpc_active") and config.get("user_token"): gateway_task = bot.loop.create_task(user_gateway())

# ==========================================
# UI E MODAIS
# ==========================================
class TokenModal(discord.ui.Modal, title='Configurar Token'):
    token_input = discord.ui.TextInput(label='Token da sua conta do Discord', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        config["user_token"] = self.token_input.value
        save_config(config)
        await interaction.response.send_message("✅ Token salvo!", ephemeral=True)
        if config["rpc_active"]: restart_gateway()

class RPCTextModal(discord.ui.Modal, title='Configurar Textos'):
    name = discord.ui.TextInput(label='Nome', default=config["rpc_state"]["name"])
    details = discord.ui.TextInput(label='Detalhes', default=config["rpc_state"]["details"])
    state = discord.ui.TextInput(label='Estado', default=config["rpc_state"]["state"])
    async def on_submit(self, interaction: discord.Interaction):
        config["rpc_state"].update({"name": self.name.value, "details": self.details.value, "state": self.state.value})
        save_config(config)
        await interaction.response.send_message("✅ Textos salvos!", ephemeral=True)
        if config["rpc_active"]: restart_gateway()

class RPCImageModal(discord.ui.Modal, title='Configurar Imagens'):
    app_id = discord.ui.TextInput(label='Client ID', default=config["rpc_state"]["application_id"])
    large_img = discord.ui.TextInput(label='Link Imagem Grande', default=config["rpc_state"]["large_image"], required=False, style=discord.TextStyle.paragraph)
    small_img = discord.ui.TextInput(label='Link Imagem Pequena', default=config["rpc_state"]["small_image"], required=False, style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # O "Hacker Method" aqui:
        large = await converte_link_discord(config["user_token"], self.app_id.value, self.large_img.value)
        small = await converte_link_discord(config["user_token"], self.app_id.value, self.small_img.value)
        config["rpc_state"].update({"application_id": self.app_id.value, "large_image": large, "small_image": small})
        save_config(config)
        await interaction.followup.send("✅ Imagens processadas! Se falhar, veja os logs no Portainer.", ephemeral=True)
        if config["rpc_active"]: restart_gateway()

class PanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def check_owner(self, interaction):
        if not config["owner_id"]: config["owner_id"] = interaction.user.id; save_config(config); return True
        return interaction.user.id == config["owner_id"]

    @discord.ui.button(label="1. Token", style=discord.ButtonStyle.primary, emoji="🔑")
    async def btn_token(self, interaction, button): await interaction.response.send_modal(TokenModal())
    @discord.ui.button(label="2. Textos", style=discord.ButtonStyle.secondary, emoji="📝")
    async def btn_text(self, interaction, button): await interaction.response.send_modal(RPCTextModal())
    @discord.ui.button(label="3. Imagens", style=discord.ButtonStyle.secondary, emoji="🖼️")
    async def btn_img(self, interaction, button): await interaction.response.send_modal(RPCImageModal())
    @discord.ui.button(label="Ligar", style=discord.ButtonStyle.success, emoji="▶️")
    async def btn_start(self, interaction, button):
        config["rpc_active"] = True; save_config(config); restart_gateway(); await interaction.response.send_message("✅ Ligado!", ephemeral=True)
    @discord.ui.button(label="Desligar", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def btn_stop(self, interaction, button):
        config["rpc_active"] = False; save_config(config); await interaction.response.send_message("🛑 Desligado!", ephemeral=True)

@bot.event
async def on_ready():
    print(f"🤖 Online como: {bot.user}")
    await bot.tree.sync()
    if config.get("rpc_active") and config.get("user_token"): restart_gateway()

@bot.tree.command(name="painel", description="Abre o painel")
async def painel(interaction: discord.Interaction):
    await interaction.response.send_message("☁️ Painel CustomRP", view=PanelView())

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
    
