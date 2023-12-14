import discord
import re
import sqlite3
import sys
from datetime import datetime
sys.path.append("./utils")
import tools


class YesNoView(discord.ui.View):
    # A simple view with two buttons, Yes and No. Choosing one will disable both bottoms.
    # Buttons disappear after 10 minutes.
    # Currently used for:
    #  - Option to advertise new character after adding to database
    #  - Confirmation of playlist deletion
    def __init__(self, ctx):
        super().__init__(timeout=600)
        self.value = None
        self.user = None
        self.ctx = ctx

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.blurple)
    async def yes(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        self.user = interaction.user
        for x in self.children:
            x.disabled = True
        self.stop()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="No", style=discord.ButtonStyle.grey)
    async def no(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        self.user = interaction.user
        for x in self.children:
            x.disabled = True
        self.stop()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        await self.ctx.interaction.edit_original_response(view=None)


class CustomButton(discord.ui.Button):
    def __init__(self,
                 label: str = None,
                 url: str = None,
                 style: discord.ButtonStyle = discord.ButtonStyle.blurple,
                 disabled: bool = False):
        super().__init__(label=label, url=url, style=style, disabled=disabled)


class OpenCardPack(discord.ui.View):
    def __init__(self, ctx, bot, num_packs, series, series_text):
        super().__init__(timeout=600)
        self.num_packs = num_packs
        self.ctx = ctx
        self.bot = bot
        self.series = series
        self.series_text = series_text
        self.add_buttons()

    def add_buttons(self):
        for i, series in enumerate(self.series):
            self.add_item(OpenCardPackButton(self.ctx, self.bot, series, label=f"{self.series_text[i].split('(')[0]} ({self.num_packs} packs)"))

    async def on_timeout(self):
        await self.ctx.interaction.edit_original_response(view=None)


class OpenCardPackButton(discord.ui.Button):
    def __init__(self,
                 ctx, bot, series,
                 label: str = None,
                 style: discord.ButtonStyle = discord.ButtonStyle.blurple,
                 disabled: bool = False):
        self.ctx = ctx
        self.bot = bot
        self.series = series
        super().__init__(label=label, style=style, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        if self.ctx.author.id == interaction.user.id:
            await interaction.response.defer()
            connection = sqlite3.connect(self.bot.game_database)
            cursor = connection.cursor()
            (self.view.num_packs,) = cursor.execute("SELECT packs FROM players WHERE player_id = ?;",
                                                    (self.ctx.author.id,)).fetchone()
            connection.close()
            if self.view.num_packs > 0:
                image, embed, view_dropdown = await self.bot.get_cog("Game").open_card_pack(self.ctx, series=self.series)
                self.view.num_packs -= 1
                for i, x in enumerate(self.view.children):
                    x.label = f"Open {self.view.series_text[i]} ({self.view.num_packs} packs)"
                    if self.view.num_packs < 1:
                        x.disabled = True
                await interaction.edit_original_response(view=self.view)
                view_dropdown.message = await interaction.followup.send(file=image, embed=embed, view=view_dropdown)
            else:
                await interaction.followup.send("Whoops! You don't have any available packs.")
        else:
            await interaction.response.send_message("Can't open other members' card packs.", ephemeral=True)
        print(f"{datetime.now()}: /cards open (button) called by {interaction.user.display_name}")


class CardsDropdown(discord.ui.Select):
    def __init__(self, cards, series, sqlite_database):
        self.cards = cards
        self.series = {cards[i]: series[i] for i in range(len(cards))}
        self.sqlite_database = sqlite_database

        options = [discord.SelectOption(label=f"{card}") for card in self.cards]

        super().__init__(placeholder="Choose a card for a closer look",
                         min_values=0,
                         max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        card_id = re.search(r"-#(\d+|MH\d+|XH\d+)", self.values[0]).group(1)
        series = self.series[self.values[0]]
        connection = sqlite3.connect(self.sqlite_database)
        cursor = connection.cursor()
        (image_path, series, rarity) = cursor.execute("SELECT image_path, series, rarity FROM cards WHERE card_id = ? AND series = ?;", (card_id, series)).fetchone()
        (num_cards,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE card_id = ? AND series = ?;", (card_id, series)).fetchone()
        (num_cards_players,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE card_id = ? AND player_id = ? AND series = ?;", (card_id, interaction.user.id, series)).fetchone()
        (series_text,) = cursor.execute("SELECT prettify FROM sets WHERE series = ?;", (series,)).fetchone()
        connection.close()

        embed, image = tools.trading_card_embed_standard(series, image_path, rarity, num_cards, series_text)
        embed.set_footer(text=f"{interaction.user.display_name} owns {num_cards_players} of this card.")

        await interaction.response.edit_message(embed=embed, file=image)


class CardsDropdownView(discord.ui.View):
    def __init__(self, cards, series, sqlite_database):
        self.cards = cards
        self.series = series
        self.sqlite_database = sqlite_database

        super().__init__(CardsDropdown(self.cards, self.series, self.sqlite_database), disable_on_timeout=True, timeout=600)

    async def on_timeout(self):
        for x in self.children:
            x.disabled = True
            x.placeholder = "Menu disabled after 10 minutes."
        try:
            await self.message.edit(view=self)
        except AttributeError:
            pass


class CardsTradeView(discord.ui.View):
    def __init__(self, ctx, allowed):
        super().__init__(timeout=600)
        self.value = None
        self.user = None
        self.ctx = ctx
        self.allowed = allowed

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.blurple)
    async def yes(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user != self.allowed:
            await interaction.response.send_message(f"Only {self.allowed.display_name} can respond to this trade.", ephemeral=True)
        else:
            self.value = True
            self.user = interaction.user
            button.label = "Traded!"
            for x in self.children:
                x.disabled = True
            self.stop()
            await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def no(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user not in [self.allowed, self.ctx.author]:
            await interaction.response.send_message(f"Only {self.allowed.display_name} or {self.ctx.author.display_name} can cancel this trade.", ephemeral=True)
        else:
            self.value = False
            self.user = interaction.user
            button.label = "Trade Cancelled"
            for x in self.children:
                x.disabled = True
            self.stop()
            await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        await self.ctx.interaction.edit_original_response(view=None)
