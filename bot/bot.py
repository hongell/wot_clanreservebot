import os
import json
import time
import requests
import discord
from discord.ext import tasks
import logging
from aiohttp import web
import asyncio
import secrets
from pathlib import Path
import upnpclient
import socket
import datetime
import pytz

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
WG_APPLICATION_ID = os.getenv("WG_APPLICATION_ID")
WG_CLAN_ID = os.getenv("WG_CLAN_ID")
OAUTH_PORT = int(os.getenv("OAUTH_PORT", "42000"))
TIME_ZONE = os.getenv("TZ", "Europe/Helsinki")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))

# OAuth2 Configuration
TOKEN_FILE = "/app/data/wg_tokens.json"
RESERVES_STATE_FILE = "/app/data/reserves_state.json"

def setup_upnp():
    try:
        devices = upnpclient.discover()
        if not devices:
            logger.warning("No UPnP devices found")
            return None

        device = devices[0]
        
        # Get the external IP address
        external_ip = None
        for service in device.services:
            if 'WANIPConnection' in service.service_type:
                external_ip = service.GetExternalIPAddress()
                break
        
        if not external_ip:
            logger.warning("Could not get external IP from UPnP")
            return None
            
        logger.info(f"External IP: {external_ip}")
        
        # Try to add port mapping
        try:
            for service in device.services:
                if 'WANIPConnection' in service.service_type:
                    service.AddPortMapping(
                        NewRemoteHost='',
                        NewExternalPort=OAUTH_PORT,
                        NewProtocol='TCP',
                        NewInternalPort=OAUTH_PORT,
                        NewInternalClient=get_local_ip(),
                        NewEnabled='1',
                        NewPortMappingDescription='WG OAuth Server',
                        NewLeaseDuration=0
                    )
                    logger.info(f"Successfully mapped port {OAUTH_PORT}")
                    break
        except Exception as e:
            logger.error(f"Failed to map port: {e}")
            return None
            
        return external_ip
    except Exception as e:
        logger.error(f"UPnP setup failed: {e}")
        return None

def get_local_ip():
    """Get local IP address"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))  # doesn't actually connect
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    return local_ip

def get_public_ip_fallback():
    """Fallback method to get public IP if UPnP fails"""
    try:
        response = requests.get('https://api.ipify.org')
        return response.text
    except Exception as e:
        logger.error(f"Failed to get public IP: {e}")
        return None

class WargamingAuth:
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.state = None
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        self.load_tokens()

    def load_tokens(self):
        try:
            if Path(TOKEN_FILE).exists():
                with open(TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token')
                    self.expires_at = data.get('expires_at')
                    logger.info("Loaded existing tokens from file")
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")

    def save_tokens(self):
        try:
            with open(TOKEN_FILE, 'w') as f:
                json.dump({
                    'access_token': self.access_token,
                    'refresh_token': self.refresh_token,
                    'expires_at': self.expires_at
                }, f)
                logger.info("Saved tokens to file")
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")

    async def get_valid_token(self):
        current_time = time.time()
        
        if self.access_token and self.expires_at and current_time < self.expires_at - 300:
            return self.access_token

        if self.refresh_token:
            try:
                await self.refresh_access_token()
                return self.access_token
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")

        return None

    async def refresh_access_token(self):
        url = "https://api.worldoftanks.eu/wot/auth/prolongate/"
        params = {
            "application_id": WG_APPLICATION_ID,
            "refresh_token": self.refresh_token
        }
        
        response = requests.post(url, params=params)
        data = response.json()
        
        if data.get("status") == "ok":
            self.access_token = data["data"]["access_token"]
            self.refresh_token = data["data"]["refresh_token"]
            self.expires_at = time.time() + data["data"]["expires_at"]
            self.save_tokens()
        else:
            raise Exception(f"Token refresh failed: {data}")

class DiscordBot:
    def __init__(self):
        self.auth = WargamingAuth()
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.guilds = True
        self.client = discord.Client(intents=intents)
        
        self.last_active_reserves = self.load_reserves_state()
        self.web_app = web.Application()
        self.setup_discord_events()
        self.setup_web_routes()
        self.oauth_state = None
        
        # Setup public IP and port forwarding
        self.public_ip = setup_upnp()
        if not self.public_ip:
            self.public_ip = get_public_ip_fallback()
            logger.warning("UPnP failed, using fallback IP detection")
        
        if self.public_ip:
            self.redirect_uri = f"http://{self.public_ip}:{OAUTH_PORT}/callback"
            logger.info(f"OAuth redirect URI: {self.redirect_uri}")
        else:
            logger.error("Failed to determine public IP")
            raise Exception("Could not determine public IP address")

    def load_reserves_state(self):
        """Load previously announced reserves from file"""
        try:
            if Path(RESERVES_STATE_FILE).exists():
                with open(RESERVES_STATE_FILE, 'r') as f:
                    data = json.load(f)
                    return set(data.get('announced_reserves', []))
            return set()
        except Exception as e:
            logger.error(f"Error loading reserves state: {e}")
            return set()

    def save_reserves_state(self):
        """Save announced reserves to file"""
        try:
            os.makedirs(os.path.dirname(RESERVES_STATE_FILE), exist_ok=True)
            with open(RESERVES_STATE_FILE, 'w') as f:
                json.dump({
                    'announced_reserves': list(self.last_active_reserves)
                }, f)
            logger.info("Saved reserves state to file")
        except Exception as e:
            logger.error(f"Error saving reserves state: {e}")

    def cleanup_expired_reserves(self, current_time):
        """Remove expired reserves from the state"""
        expired = {
            reserve_id for reserve_id in self.last_active_reserves
            if int(reserve_id.split('_')[1]) < current_time - 7200  # 2 hours buffer after expiration
        }
        if expired:
            self.last_active_reserves -= expired
            self.save_reserves_state()
            logger.info(f"Cleaned up {len(expired)} expired reserves from state")

    async def send_admin_message(self, message):
        """Send a message to the admin user"""
        try:
            admin_user = await self.client.fetch_user(ADMIN_USER_ID)
            if admin_user:
                await admin_user.send(message)
                logger.info(f"Sent admin message to {admin_user.name}")
        except Exception as e:
            logger.error(f"Failed to send admin message: {e}")

    def setup_discord_events(self):
        @self.client.event
        async def on_ready():
            logger.info(f'Logged in as {self.client.user}')
            # Debug info
            for guild in self.client.guilds:
                logger.info(f'Bot is in guild: {guild.name} (id: {guild.id})')
                channel = self.client.get_channel(DISCORD_CHANNEL_ID)
                if channel:
                    logger.info(f'Found channel: {channel.name} in guild: {guild.name}')
                    # Test permissions
                    permissions = channel.permissions_for(guild.me)
                    logger.info(f'Bot permissions in channel:')
                    logger.info(f'- Can view channel: {permissions.view_channel}')
                    logger.info(f'- Can send messages: {permissions.send_messages}')
                    logger.info(f'- Can send messages in threads: {permissions.send_messages_in_threads}')
                else:
                    logger.info(f'Could not find channel with ID {DISCORD_CHANNEL_ID} in guild {guild.name}')
            
            self.fetch_and_post_reserves.start()

    def setup_web_routes(self):
        self.web_app.router.add_get('/callback', self.handle_oauth_callback)
        self.web_app.router.add_get('/callback{tail:.*}', self.handle_oauth_callback)

    async def start_oauth_server(self):
        runner = web.AppRunner(self.web_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', OAUTH_PORT)
        await site.start()
        logger.info(f"OAuth callback server started on {self.redirect_uri}")

    async def start_oauth_flow(self):
        auth_params = {
            "application_id": WG_APPLICATION_ID,
            "redirect_uri": self.redirect_uri,
            "display": "page",
            "nofollow": "0",
            "expires_at": "1736027938",
            "response_type": "code token"
        }
        
        auth_url = "https://api.worldoftanks.eu/wot/auth/login/"
        auth_query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in auth_params.items())
        full_auth_url = f"{auth_url}?{auth_query}"
        
        logger.info(f"Please visit this URL to authorize: {full_auth_url}")
        return full_auth_url

    async def handle_oauth_callback(self, request):
        logger.info(f"Full callback params: {dict(request.query)}")
        
        status = request.query.get('status')
        access_token = request.query.get('access_token')
        refresh_token = request.query.get('refresh_token')
        account_id = request.query.get('account_id')
        nickname = request.query.get('nickname')
        expires_at = request.query.get('expires_at')

        if status != 'ok' or not access_token:
            logger.error("Invalid callback response")
            return web.Response(text="Authorization failed", status=400)

        try:
            self.auth.access_token = access_token
            self.auth.refresh_token = refresh_token
            self.auth.expires_at = int(expires_at) if expires_at else (time.time() + 86400)
            self.auth.save_tokens()
            
            logger.info(f"Saved tokens: access={access_token}, refresh={refresh_token}, expires={expires_at}")
            
            channel = self.client.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                await self.send_admin_message(f"✅ Successfully authorized bot for WoT account: {nickname}")
                await self.fetch_and_post_reserves()
            
            return web.Response(text=f"Authorization successful for {nickname}! You can close this window.")
            
        except Exception as e:
            logger.error(f"Error processing callback: {e}")
            return web.Response(text="Error processing authorization", status=500)

    @tasks.loop(minutes=5)
    async def fetch_and_post_reserves(self):
        try:
            # Check token expiration
            if self.auth.expires_at:
                time_until_expiry = self.auth.expires_at - time.time()
                # If token expires in less than 24 hours
                if time_until_expiry < 86400:  # 24 hours in seconds
                    await self.send_admin_message(f"⚠️ WoT auth token expires in {int(time_until_expiry/3600)} hours. Click to reauthorize: {await self.start_oauth_flow()}")
            
            access_token = await self.auth.get_valid_token()
            if not access_token:
                await self.send_admin_message(f"🔑 Bot needs reauthorization. Click to authorize: {await self.start_oauth_flow()}")
                return

            # Clean up expired reserves
            self.cleanup_expired_reserves(int(time.time()))
            
            url = "https://api.worldoftanks.eu/wot/stronghold/clanreserves/info/"
            params = {
                "application_id": WG_APPLICATION_ID,
                "access_token": access_token,
                "clan_id": WG_CLAN_ID
            }

            response = requests.get(url, params=params)
            data = response.json()

            if response.status_code == 200 and "data" in data:
                reserves = data["data"]
                current_active = set()
                newly_activated = []
                
                for reserve in reserves:
                    name = reserve['name']
                    stock_info = reserve['in_stock'][0]
                    status = stock_info['status']
                    
                    if status == 'active':
                        reserve_id = f"{name}_{stock_info['activated_at']}"
                        current_active.add(reserve_id)
                        
                        if reserve_id not in self.last_active_reserves:
                            tz = pytz.timezone(TIME_ZONE)
                            active_till_dt = datetime.datetime.fromtimestamp(stock_info['active_till'])
                            active_till_local = active_till_dt.astimezone(tz)
                            active_till = active_till_local.strftime('%Y-%m-%d %H:%M:%S')
                            
                            bonus_text = []
                            for bonus in stock_info['bonus_values']:
                                bonus_text.append(f"{bonus['value']}x for {bonus['battle_type']}")
                            
                            reserve_info = f"**{name}** (Level {stock_info['level']})\n" \
                                         f"• {', '.join(bonus_text)}\n" \
                                         f"• Active until: {active_till}"
                            newly_activated.append(reserve_info)

                # Update tracking set if there are changes
                if current_active != self.last_active_reserves:
                    self.last_active_reserves = current_active
                    self.save_reserves_state()

                if newly_activated:
                    message = "**BONARIT ON PÄÄLLÄ, NYT KAIKKI PELAAMAAN:**\n\n"
                    message += "\n\n".join(newly_activated)

                    channel = self.client.get_channel(DISCORD_CHANNEL_ID)
                    if channel:
                        await channel.send(message)
                        
        except Exception as e:
            logger.error(f"Error: {str(e)}", exc_info=True)

async def main():
    bot = DiscordBot()
    await bot.start_oauth_server()
    await bot.client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())