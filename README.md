```markdown
# WoT Clan Reserves Discord Bot

A Discord bot that monitors and announces World of Tanks clan reserves status. When clan reserves are activated, the bot automatically posts notifications to a specified Discord channel.

## Issues

- The upnp port stuff is just from AI, no guarantees if it works. Just change callback url to localhost if running on the machine where you authenticating from. Also its plain http..

## Features

- 🔄 Real-time monitoring of clan reserves (checks every 5 minutes)
- 🌍 Timezone-aware notifications (configurable, defaults to Europe/Helsinki)
- 🔐 Secure OAuth2 authentication with Wargaming API
- 💾 Persistent state tracking (prevents duplicate notifications on restart)
- 👤 Admin notifications for:
  - Authentication status
  - Token expiration warnings
  - Bot permission issues

## Prerequisites

- Docker and Docker Compose
- Discord Bot Token
- Wargaming Developer Application ID
- World of Tanks clan ID
- Discord channel ID where notifications will be posted
- Discord user ID for admin notifications

## Configuration

Create a `.env` file in the project root with the following variables:

```env
DISCORD_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id
WG_APPLICATION_ID=your_wargaming_app_id
WG_CLAN_ID=your_clan_id
ADMIN_USER_ID=your_discord_user_id
TZ=Europe/Helsinki
OAUTH_PORT=42000
```

### Getting the Required IDs

1. **Discord Bot Token**:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application
   - Go to the "Bot" section
   - Create a bot and copy its token

2. **Wargaming Application ID**:
   - Visit [Wargaming Developer Portal](https://developers.wargaming.net/)
   - Create a new application
   - Set application type to "Web"
   - Add `http://your_ip:42000/callback` to allowed redirect URIs

3. **Discord Channel ID**:
   - Enable Developer Mode in Discord (User Settings → App Settings → Advanced)
   - Right-click the target channel and select "Copy ID"

4. **Admin User ID**:
   - Right-click your username (with Developer Mode enabled)
   - Select "Copy ID"

5. **Clan ID**:
   - Can be found in your clan's profile URL on the World of Tanks portal

## Installation & Running

1. Clone the repository:
```bash
git clone https://github.com/hongell/wot_clanreservebot.git
cd wot-reserves-bot
```

2. Create and configure the `.env` file as described above

3. Build and start the bot:
```bash
docker compose up --build
```

4. For background running:
```bash
docker compose up -d
```

## Bot Permissions

The bot requires the following Discord permissions:
- Read Messages/View Channels
- Send Messages
- Send Messages in Threads
- Read Message History

Use this invite link format (replace CLIENT_ID):
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877910016&scope=bot
```

## Authentication Flow

1. On first run, the bot will send a DM to the admin with an authentication URL
2. Visit the URL and authorize with your Wargaming account
3. Authentication is valid for approximately 2 weeks
4. Bot will notify admin when re-authentication is needed

## Message Format

When reserves are activated, the bot posts messages in this format:
```
BONARIT ON PÄÄLLÄ, NYT KAIKKI PELAAMAAN:

Reserve Name (Level X)
• Bonus multiplier for Battle Type
• Active until: YYYY-MM-DD HH:MM:SS
```

## Maintenance

- Logs can be viewed with:
```bash
docker compose logs -f
```

- Stop the bot:
```bash
docker compose down
```

## Troubleshooting

1. **Bot not showing in server**: Ensure proper permissions and valid invite link
2. **No messages**: Check channel ID and bot permissions
3. **Authentication issues**: Verify Wargaming Application settings and redirect URI
4. **Port issues**: Ensure port 42000 is accessible or configure a different port

## Files

- `bot.py`: Main bot code
- `docker-compose.yml`: Docker configuration
- `/data`: Directory for persistent storage
  - `wg_tokens.json`: Authentication tokens
  - `reserves_state.json`: Reserve tracking state

## Contributing

Feel free to open issues or submit pull requests for improvements.

## License

MIT
```

