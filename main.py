import discord
from discord.ext import commands
import asyncio
import aiohttp
import json
import os

# ==========================================
# CONFIGURAÇÕES
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN: exit(1)

if not os.path.exists("data"): os.makedirs("data")
CONFIG_FILE = "data/config.json"

def load_config():
    default_config = {
        "user_token": None, "rpc_active": False,
        "rpc_state": {
            "name": "Nexzy Store", "application_id": "1525126100034785400",
            "details": "A navegar...", "state": "Modo Furtivo",
            "large_image": "", "large_text": "Loja Oficial",
            "small_image": "", "small_text": "Online"
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f: return json.load(f)
        except: return default_config
    return default_config

def save_config(data):
    with open(CONFIG_FILE, "w") as f: json.dump(data, f, indent=4)

config = load_config()
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

# ==========================================
# GATEWAY
# ==========================================
async def send_heartbeat(ws, interval):
    while not ws.closed:
        await asyncio.sleep(interval)
        try: await ws.send_json({"op": 1, "d": None})
        except: break

async def user_gateway():
    while config.get("rpc_active", False):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect('wss://gateway.discord.gg/?v=10&encoding=json') as ws:
                    state = config["rpc_state"]
                    payload = {
                        "op": 2, "d": {
                            "token": config["user_token"], "capabilities": 16381,
                            "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
                            "presence": {
                                "status": "online", "since": 0,
                                "activities": [{
                                    "name": state["name"], "type": 0, "application_id": state["application_id"],
                                    "details": state["details"], "state": state["state"],
                                    "assets": {"large_image": state["large_image"], "large_text": state["large_text"], 
                                               "small_image": state["small_image"], "small_text": state["small_text"]}
                                }]
                            }
                        }
                    }
                    await ws.send_json(payload)
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if data['op'] == 10:
                                bot.loop.create_task(send_heartbeat(ws, data['d']['heartbeat_interval'] / 1000))
        except: await asyncio.sleep(5)

# ==========================================
# UI E MODAIS
# ==========================================
class TokenModal(discord.ui.Modal, title='Configurar Token'):
    token = discord.ui.TextInput(label='Token da sua conta', style=discord.TextStyle.short)
    async def on_submit(self, interaction):
        config["user_token"] = self.token.value
        save_config(config)
        await interaction.response.send_message("✅ Token salvo!", ephemeral=True)

class RPCImageModal(discord.ui.Modal, title='Configurar Imagens (Assets)'):
    large_img = discord.ui.TextInput(label='Nome do Asset Grande', placeholder='ex: teste', default=config["rpc_state"]["large_image"])
    async def on_submit(self, interaction):
        config["rpc_state"]["large_image"] = self.large_img.value
        save_config(config)
        await interaction.response.send_message("✅ Asset atualizado!", ephemeral=True)

class PanelView(discord.ui.View):
    @discord.ui.button(label="1. Token", style=discord.ButtonStyle.primary)
    async def btn_token(self, interaction, button): await interaction.response.send_modal(TokenModal())
    @discord.ui.button(label="3. Imagens (Nomes)", style=discord.ButtonStyle.secondary)
    async def btn_img(self, interaction, button): await interaction.response.send_modal(RPCImageModal())
    @discord.ui.button(label="Ligar RPC", style=discord.ButtonStyle.success)
    async def btn_start(self, interaction, button):
        config["rpc_active"] = True; save_config(config); bot.loop.create_task(user_gateway()); await interaction.response.send_message("✅ Ligado!", ephemeral=True)

@bot.tree.command(name="painel")
async def painel(interaction): await interaction.response.send_message("Painel CustomRP", view=PanelView())

bot.run(BOT_TOKEN)
