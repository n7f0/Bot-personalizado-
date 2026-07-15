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
        "owner_id": None,
        "user_token": None,
        "rpc_active": False,
        "rpc_state": {
            "name": "Nexzy Store",
            "application_id": "1525126100034785400",
            "details": "A navegar...",
            "state": "Modo Furtivo",
            "large_image": "", # Deixamos vazio por padrão para você colar o link
            "large_text": "Loja Oficial",
            "small_image": "",
            "small_text": "Online"
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if "rpc_state" not in data:
                    data["rpc_state"] = default_config["rpc_state"]
                else:
                    for key in default_config["rpc_state"]:
                        if key not in data["rpc_state"]:
                            data["rpc_state"][key] = default_config["rpc_state"][key]
                return data
        except json.JSONDecodeError:
            return default_config
    return default_config

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

config = load_config()
gateway_task = None
gateway_ws = None

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# FUNÇÕES DO GATEWAY (O MOTOR DO CUSTOM RP)
# ==========================================
def get_presence_payload():
    state = config["rpc_state"]
    
    # Prepara os assets apenas se tiver link
    assets = {}
    if state["large_image"]:
        assets["large_image"] = state["large_image"]
        assets["large_text"] = state["large_text"]
    if state["small_image"]:
        assets["small_image"] = state["small_image"]
        assets["small_text"] = state["small_text"]

    return {
        "status": "online",
        "since": 0,
        "activities": [{
            "name": state["name"], 
            "type": 0, 
            "application_id": state["application_id"],
            "details": state["details"],
            "state": state["state"],
            "assets": assets if assets else None
        }],
        "afk": False
    }

async def send_heartbeat(ws, interval):
    while not ws.closed:
        await asyncio.sleep(interval)
        try:
            await ws.send_json({"op": 1, "d": None})
        except:
            break

async def user_gateway():
    global gateway_ws
    while config.get("rpc_active", False):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect('wss://gateway.discord.gg/?v=10&encoding=json') as ws:
                    gateway_ws = ws
                    identify_payload = {
                        "op": 2,
                        "d": {
                            "token": config["user_token"],
                            "capabilities": 16381,
                            "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
                            "presence": get_presence_payload()
                        }
                    }
                    await ws.send_json(identify_payload)
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if data['op'] == 10:
                                interval = data['d']['heartbeat_interval'] / 1000
                                bot.loop.create_task(send_heartbeat(ws, interval))
        except Exception as e:
            await asyncio.sleep(5)

def restart_gateway():
    global gateway_task, gateway_ws
    if gateway_ws and not gateway_ws.closed:
        bot.loop.create_task(gateway_ws.close())
    if gateway_task:
        gateway_task.cancel()
    
    if config.get("rpc_active") and config.get("user_token"):
        gateway_task = bot.loop.create_task(user_gateway())

# ==========================================
# INTERFACE UI (CAIXAS DE TEXTO IGUAIS AO CUSTOMRP)
# ==========================================
class TokenModal(discord.ui.Modal, title='Configurar Token Pessoal'):
    token_input = discord.ui.TextInput(
        label='Token da sua conta do Discord',
        style=discord.TextStyle.short,
        required=True
    )
    async def on_submit(self, interaction: discord.Interaction):
        config["user_token"] = self.token_input.value
        save_config(config)
        await interaction.response.send_message("✅ Token guardado com sucesso!", ephemeral=True)
        if config["rpc_active"]: restart_gateway()

class RPCTextModal(discord.ui.Modal, title='Configurar Textos'):
    name = discord.ui.TextInput(label='Nome Principal (Ex: Nexzy Store)', default=config["rpc_state"]["name"])
    details = discord.ui.TextInput(label='Detalhes (Primeira linha)', default=config["rpc_state"]["details"])
    state = discord.ui.TextInput(label='Estado (Segunda linha)', default=config["rpc_state"]["state"])

    async def on_submit(self, interaction: discord.Interaction):
        config["rpc_state"]["name"] = self.name.value
        config["rpc_state"]["details"] = self.details.value
        config["rpc_state"]["state"] = self.state.value
        save_config(config)
        await interaction.response.send_message("✅ Textos configurados!", ephemeral=True)
        if config["rpc_active"]: restart_gateway()

class RPCImageModal(discord.ui.Modal, title='Configurar Imagens (Links)'):
    app_id = discord.ui.TextInput(label='Client ID', default=config["rpc_state"]["application_id"])
    
    large_img = discord.ui.TextInput(
        label='Link da Imagem Grande', 
        style=discord.TextStyle.short,
        placeholder='https://...', 
        default=config["rpc_state"]["large_image"],
        required=False
    )
    
    small_img = discord.ui.TextInput(
        label='Link da Imagem Pequena', 
        style=discord.TextStyle.short,
        placeholder='https://...', 
        default=config["rpc_state"]["small_image"],
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        config["rpc_state"]["application_id"] = self.app_id.value
        config["rpc_state"]["large_image"] = self.large_img.value
        config["rpc_state"]["small_image"] = self.small_img.value
        save_config(config)
        await interaction.response.send_message("✅ Links de imagem salvos! O Discord vai carregar agora.", ephemeral=True)
        if config["rpc_active"]: restart_gateway()

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def check_owner(self, interaction: discord.Interaction):
        if not config["owner_id"]:
            config["owner_id"] = interaction.user.id
            save_config(config)
            return True
        if interaction.user.id != config["owner_id"]:
            await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="1. Token", style=discord.ButtonStyle.primary, emoji="🔑", row=0)
    async def btn_token(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_owner(interaction):
            await interaction.response.send_modal(TokenModal())

    @discord.ui.button(label="2. Textos", style=discord.ButtonStyle.secondary, emoji="📝", row=0)
    async def btn_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_owner(interaction):
            await interaction.response.send_modal(RPCTextModal())

    @discord.ui.button(label="3. Imagens (Links)", style=discord.ButtonStyle.secondary, emoji="🖼️", row=0)
    async def btn_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_owner(interaction):
            await interaction.response.send_modal(RPCImageModal())

    @discord.ui.button(label="Ligar RPC", style=discord.ButtonStyle.success, emoji="▶️", row=1)
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_owner(interaction):
            if not config.get("user_token"):
                return await interaction.response.send_message("❌ Configure o Token primeiro!", ephemeral=True)
            config["rpc_active"] = True
            save_config(config)
            restart_gateway()
            await interaction.response.send_message("✅ Rich Presence Ligado!", ephemeral=True)

    @discord.ui.button(label="Desligar", style=discord.ButtonStyle.danger, emoji="⏹️", row=1)
    async def btn_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_owner(interaction):
            config["rpc_active"] = False
            save_config(config)
            if gateway_ws and not gateway_ws.closed:
                await gateway_ws.close()
            await interaction.response.send_message("🛑 Rich Presence Desligado!", ephemeral=True)

# ==========================================
# EVENTOS E COMANDOS
# ==========================================
@bot.event
async def on_ready():
    print(f"🤖 CustomRP Cloud online como: {bot.user}")
    await bot.tree.sync()
    if config.get("rpc_active") and config.get("user_token"):
        restart_gateway()

@bot.tree.command(name="painel", description="Abre o painel estilo CustomRP.")
async def painel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="☁️ CustomRP na Nuvem (Portainer)",
        description="Seu próprio CustomRP rodando 24 horas por dia.\n\n"
                    "**Como usar as imagens:**\n"
                    "1. Envie a foto num chat do Discord.\n"
                    "2. Clique em 'Copiar link da imagem' (`https://cdn.discordapp...`).\n"
                    "3. Clique em **3. Imagens (Links)** e cole o link lá!",
        color=discord.Color.brand_green()
    )
    await interaction.response.send_message(embed=embed, view=PanelView())

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
