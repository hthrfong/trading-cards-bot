# trading-cards-bot
Discord bot with Marvel trading cards game

- Written with PyCord, a Python API wrapper for Discord (https://docs.pycord.dev/en/stable/)
- Utilizes slash commands: on Discord, type '/' to get a list of available commands
  - `/cards help`: Returns a list of trading card-related commands
  - `/cards freebie`: Get a 'free' random card
  - `/cards buy`: Buy a 12-card pack
  - `/cards open`: Open a card pack
  - `/cards inventory`: Check your card collection
  - `/cards search`: Search for a card
  - `/cards trade`: Trade cards with another member
  - There is also the capability to convert timezones via `/time convert`

## Installing and running
- Instructions to add bot to server: https://discordpy.readthedocs.io/en/stable/discord.html
  - Make sure to turn on intents
- In the git repo directory, create a file named `.env` with the following:

```BOT_TOKEN=PASTETOKENHERE```

- To run the bot from terminal, do `python launch.py`
