from discord.commands import slash_command, Option, SlashCommandGroup
from discord.ext.commands import Cog
from discord.ext import commands, pages
import discord
from discord import Embed
from dateutil import parser
from collections import Counter
from datetime import datetime
from glob import glob
from io import BytesIO
import sqlite3
from random import choices
import re
from PIL import Image
from math import floor
import numpy as np

import sys
sys.path.append("./utils")
import views
import tools


def add_cards_to_db(cursor, series, card_directories, thumbnail_directories):
    # Add card and card information to database
    # series, card_directories, and thumbnail_directories are lists
    for i in range(len(series)):
        pattern = rf"{series[i].split('X-Men')[0].replace('-', '_')}X-Men_#(\d+|XH\d+|)_" if "X-Men" in series[i] else rf"{series[i].replace('-', '_')}_#(\d+|MH\d+)_"
        all_images = sorted(glob(f"{card_directories[i]}/*"))
        card_ids = [re.search(pattern, name).group(1) for name in all_images]
        thumbnail_images = sorted(glob(f"{thumbnail_directories[i]}/*"))

        input_list = [
            (card_ids[n], series[i], all_images[n].split("/")[-1], thumbnail_images[n].split("/")[-1]) for n
            in range(len(all_images))]

        cursor.executemany("INSERT OR REPLACE INTO cards (card_id, series, image_path, thumbnail_path) "
                           "VALUES (?, ?, ?, ?);", input_list)

        print(f"Added {len(all_images)} cards to database.")


def merge_thumbnail_images(images):
    # Create 12-pack card preview
    assert len(images) == 12, f"must have 12 images: {len(images)}"
    im = np.array([ [None, None, None, None],
                    [None, None, None, None],
                    [None, None, None, None] ])
    widths = np.zeros((3, 4))
    heights = np.zeros((3, 4))
    n = 0
    for i in range(len(im)):  # row
        for j in range(len(im[i])):  # column
            image = Image.open(images[n])
            im[i][j] = image
            widths[i][j] = image.size[0]
            heights[i][j] = image.size[1]
            n += 1

    max_width = int(max([sum(widths[i, :]) for i in range(len(im))]))
    max_height = int(sum([max(heights[i, :]) for i in range(len(im))]))

    image = Image.new("RGBA", (max_width, max_height))
    y = 0
    for i in range(len(im)):
        x = 0
        if i > 0:
            y += int(max(heights[i]))
        for j in range(len(im[i])):
            image.paste(im[i][j], (x, y))
            x += im[i][j].size[0]

    return image


class Game(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game_database = None
        self.thumbnail_directories = None
        self.card_directories = None

        # Names of available sets, matches 'series' column in 'sets' table
        # {series: {"prettify": human readable name, "shorthand": unique ID}}
        self.available_sets = {"1990-Impel-Marvel-Universe": {"prettify": "Marvel Universe (1990)", "shorthand": "MU"},
                               "1991-Impel-Marvel-Universe-II": {"prettify": "Marvel Universe II (1991)", "shorthand": "MU2"},
                               "1992-Impel-X-Men": {"prettify": "X-Men (1992)", "shorthand": "XM"}}
        self.card_series = [series for series in list(self.available_sets.keys())]
        # Directory of thumbnail images
        self.thumbnail_directories = [f"./data/cards/{series}/thumbnail" for series in self.card_series]
        # Directory of merged images (full sized front and back)
        self.card_directories = [f"./data/cards/{series}/merged" for series in self.card_series]

        self.rarity = {1: 0.70, 2: 0.2, 3: 0.08, 4: 0.012, 5: 0.008}
        self.rarity_symbols = {1: "🔹", 2: "🔹", 3: "🔹", 4: "🔸", 5: "♦️️"}
        self.rarity_weights = {}  # Dictionary for card weights {series: {rarity: rarity_prob/num_cards}}

        self.pack_cost = 500  # Cost of one pack
        self.message_reward = 25  # Reward per message sent
        self.post_reward = 250  # Reward per post written

        self.bub = "💰"  # Emoji

        self.freebie_blurbs = ["A stranger in a black trenchcoat hurries past you in a crowded street. When he accidentally bumps your shoulder, something falls out of his pocket and flutters to the ground.",
                               "A seemingly abandoned wallet catches your eye. It's old and worn and sadly empty, except for...",
                               "A stranger passes you a newspaper and mutters, \"I'm not much of a baseball fan but I never miss a Yankees game.\" He leaves. When you turn to the sports section, something falls out.",
                               "A girl asks you for directions. \"Where is the road to happiness?\" Seeing you struggle to answer, she nods sagely and hands you a card. \"Here. For your journey.\"",
                               "A barefooted woman in ragged clothes is dancing in the street, cackling madly. \"It's gone! I'm free! I'm finally FREE!\" As you watch her, something lands ominously on your shoulder.",
                               "You're finishing up a mediocre lunch at a mediocre diner when the waitress brings you your bill. You take out your wallet, but instead of your credit card, you find only...",
                               "You're walking along the beach when you notice something washed up on the shore. You fish it out and find a sopping wet...",
                               "You're sitting alone on a park bench when the wind takes pity on you and brings you a friend. It's...",
                               "You put on your favourite cassette but it's not playing right. You pop it out of the player and find something somehow stuck to the other side.",
                               "You're at a shop browsing used vinyls when you notice something sticking out of one of the sleeves. You slip it into your pocket.",
                               "The doorbell rings. You open the door and see a man in a white shirt and blue tie. Smiling, he holds up a strange-looking card. \"Hello, do you have time to talk about our Lord and Saviour...\"",
                               "You wake up off the side of the highway with no memory of how you got there. You're uninjured, but there's something stuck to your forehead. You pull it off and find...",
                               "A raccoon approaches you and lays something at your feet. It stares at you with its black, soulless eyes for what feels like an eternity, and then scampers away. You pick up its offering.",
                               "You see something sticking out of a pile of dog poop. Like the mad maverick you are, you fish it out and find a smelly...",
                               "You help a sweet old lady cross the street. With a thanks and a smile, she reaches into her purse and hands you a Werther's Original and...",
                               "At the pub, you strike up a conversation with a businessman about his sweet new moneymaking venture (not a pyramid scheme, he swears). He hands you his card, but instead of a business card, it's...",
                               "You head into your favourite dive bar and order your usual. The bartender hands you your drink, using this as a coaster...",
                               "The postman hands you a letter with your name on it but no return address. When you open the envelope, you find nothing inside except...",
                               "While at the library, a dusty old book inexplicably catches your eye. It's about curses. As you flip through its yellowing pages, something falls out.",
                               "You're fresh out of change at the arcade after losing 20 straight rounds of Tekken. To soften the blow of your humiliating defeats, your six-year-old opponent hands you...",
                               '"Hey! Hey you!" A strange man beckons you. When you approach, he shoves something into your hand. "It\'s the key to everything!" he screams as he runs off. You look down at your hand.']

        self.player_draws = {}  # Dictionary for freebie cooldown {player_id: last_drawn_time}

    def choose_random_card(self, cursor, num=1, series=None):
        # Function to randomly select cards
        # Used for getting freebies and opening packs
        if not series:  # If series not specified, choose one randomly
            series = choices(self.card_series)[0]
        # Retrieve all available cards
        card_info = cursor.execute("SELECT card_id, rarity FROM cards WHERE series = ?;", (series,)).fetchall()
        card_ids = [r[0] for r in card_info]
        weights = [self.rarity_weights[series][int(r[1])] for r in card_info]
        return choices(card_ids, weights=weights, k=num), series

    cards = SlashCommandGroup("cards", "Collect and trade vintage Marvel cards!")

    @cards.command(description="Help with trading cards.", name="help")
    async def help_commands(self, ctx,
                            visibility: Option(str, "Make Blackbird's reply private (visible to you only) or public. Default is private.",
                                               default="Private", choices=["Private", "Public"])):
        if visibility.lower() == "public":
            ephemeral = False
        else:
            ephemeral = True
        await ctx.defer(ephemeral=ephemeral)
        description = "Relive the nostalgia of trading cards! " \
                      "Collect, compare, and trade vintage Marvel cards with anyone on the server. " \
                      "Here's how to play."
        embed = Embed(title="Marvel Trading Cards!", description=f"{description}")
        embed.add_field(name=f"Earning Bub Bucks {self.bub}",
                        value=f"Chat on Discord ({self.message_reward}{self.bub} per message)")
        embed.add_field(name="Commands", value=f"**/cards buy**: Buy a 12-card pack for {self.pack_cost}{self.bub}\n"
                                               "**/cards freebie**: Find a free card (available once an hour)\n"
                                               "**/cards help**: Get this message\n"
                                               "**/cards inventory**: Check your inventory and card collection\n"
                                               "**/cards open**: Open a card pack\n"
                                               "**/cards search**: Get information on a card\n"
                                               "**/cards trade**: Trade cards with each other")
        image = discord.File(f"./data/cards/1990-Impel-Marvel-Universe/1990-Impel-Marvel-Universe-Trading-Cards-all.png", filename="card-pack.png")
        embed.set_image(url="attachment://card-pack.png")
        await ctx.respond(embed=embed, file=image, ephemeral=ephemeral)
        print(f"{datetime.now()}: /cards help called by {ctx.author.display_name}")

    @cards.command(description="Find a free card! Available once every hour.", name="freebie")
    async def open_free_card(self, ctx):
        await ctx.defer()
        # Check if player has drawn a card within the last hour
        try:
            date_time = parser.parse(self.player_draws[ctx.author.id])
            time_elapsed = (datetime.now()-date_time).total_seconds()
        except KeyError:
            time_elapsed = 9000  # If player not in dictionary, automatically make larger than 3600 seconds
        if time_elapsed >= 3600:
            connection = sqlite3.connect(self.game_database)
            cursor = connection.cursor()
            # Return randomly selected card, where chosen_card, chosen_series are both lists of length 1
            chosen_card, chosen_series = self.choose_random_card(cursor, num=1)
            # Retrieve card information
            (image_path, rarity, series_text) = cursor.execute("SELECT cards.image_path, cards.rarity, sets.prettify FROM cards JOIN sets ON (cards.series = sets.series) WHERE cards.card_id = ? AND sets.series = ?;", (chosen_card[0], chosen_series)).fetchone()
            # Retrieve number of this card that player owned before drawing
            (num_cards_player,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE player_id = ? AND card_id = ? AND series = ?", (ctx.author.id, chosen_card[0], chosen_series)).fetchone()
            # Retrieve number of this card owned by all players in the guild
            num_cards = 0
            for member in ctx.guild.members:
                (count,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE card_id = ? AND series = ? AND player_id = ?;", (chosen_card[0], chosen_series, member.id)).fetchone()
                num_cards += count

            date_time = datetime.now()  # Used to record into sqlite database and cooldown
            cursor.execute("INSERT INTO collection (player_id, card_id, series, date_time) "
                           "VALUES (?, ?, ?, ?);", (ctx.author.id, chosen_card[0], chosen_series, date_time))
            connection.commit()
            connection.close()

            embed, image = tools.trading_card_embed_standard(chosen_series, image_path, rarity, num_cards + 1, series_text)
            embed.set_author(name=choices(self.freebie_blurbs)[0])
            if num_cards_player == 0:
                embed.title = f"🆕 {embed.title}"
            embed.set_footer(text=f"You own {num_cards_player + 1} of this card.")

            # Record drawing time for cooldown
            self.player_draws[ctx.author.id] = date_time.strftime("%Y-%m-%d %H:%M:%S")

            await ctx.respond(file=image, embed=embed)
        else:  # If last free card was drawn < 1 hour ago
            time_left = 3600 - time_elapsed
            if time_left < 60:
                await ctx.respond(f"You search and you search and you find... nothing. Try again in {round(time_left)} seconds.")
            else:
                await ctx.respond(f"You search and you search and you find... nothing. Try again in {round(time_left/60)} minutes.")
        print(f"{datetime.now()}: /cards freebie called by {ctx.author.display_name}")

    async def buy_cards(self, connection, cursor, member_id, num_packs=1):
        try:
            (points, packs) = cursor.execute("SELECT points, packs FROM players WHERE player_id = ?;", (member_id,)).fetchone()
        except TypeError: # Add player if not in database
            cursor.execute("INSERT INTO players (player_id, points, packs) VALUES (?, ?, ?);", (member_id, self.pack_cost, 0))
            connection.commit()
            (points, packs) = cursor.execute("SELECT points, packs FROM players WHERE player_id = ?;", (member_id,)).fetchone()
        if points >= self.pack_cost*num_packs:
            points -= self.pack_cost*num_packs
            cursor.execute("UPDATE players SET points = ?, packs = ? WHERE player_id = ?",
                           (points, packs + num_packs, member_id))
            connection.commit()
            embed = Embed(title="You bought a card pack!" if num_packs == 1 else f"You bought {num_packs} card packs!", description="Hope it's a good one!",
                          colour=discord.Colour.gold())
            image = discord.File(
                f"./data/cards/1990-Impel-Marvel-Universe/1990-Impel-Marvel-Universe-Trading-Cards-{choices(['blue', 'red', 'yellow'])[0]}.png",
                filename="card-pack.png")
            embed.add_field(name=f"Remaining Bub Bucks", value=f"{points}{self.bub}")
            embed.add_field(name="Card Packs in Inventory", value=f"{packs + num_packs}")
            embed.set_image(url="attachment://card-pack.png")
            return embed, image, points
        else:
            return None, None, points

    @cards.command(description="See your inventory.", name="inventory")
    async def get_inventory(self, ctx):
        await ctx.defer()
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()
        try:
            (points, packs) = cursor.execute("SELECT points, packs FROM players WHERE player_id = ?;", (ctx.author.id,)).fetchone()
        except TypeError:  # Add player if not in database
            cursor.execute("INSERT INTO players (player_id, points, packs) VALUES (?, ?, ?);", (ctx.author.id, self.pack_cost, 0))
            connection.commit()
            (points, packs) = cursor.execute("SELECT points, packs FROM players WHERE player_id = ?;", (ctx.author.id,)).fetchone()
        (num_cards,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE player_id = ?;", (ctx.author.id,)).fetchone()
        (num_traded,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE player_id = ? AND trade IS NOT NULL;", (ctx.author.id,)).fetchone()
        rows = cursor.execute("SELECT DISTINCT cards.thumbnail_path, cards.series, cards.rarity, cards.card_id, sets.shorthand FROM cards "
                              "JOIN collection ON (cards.card_id = collection.card_id AND cards.series = collection.series) "
                              "JOIN sets ON (cards.series = sets.series) "
                              "WHERE collection.player_id = ? "
                              "ORDER BY cards.series, LENGTH(cards.card_id), cards.card_id;", (ctx.author.id,)).fetchall()
        if len(rows) > 0:
            card_titles = []
            page_text = []
            text = ""
            num_index = 0
            dropdown_options = []
            series = []
            series_options = []
            options = []
            for row in rows:
                (num_owned,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE player_id = ? AND card_id = ? AND series = ?", (ctx.author.id, row[3], row[1])).fetchone()
                pattern = rf"{row[1].split('X-Men')[0].replace('-', '_')}X-Men_#(\d+|XH\d+|)_(.+?)_thumbnail.jpg" if "X-Men" in row[1] else rf"{row[1].replace('-', '_')}_#(\d+|MH\d+)_(.+?)_thumbnail.jpg"
                regex_result = re.search(pattern, row[0])
                title = f"{row[2]}{self.rarity_symbols[row[2]]} {row[4]}-#{regex_result.group(1)}: {regex_result.group(2).replace('_', ' ')} ({num_owned})"
                card_titles.append(title)
                if num_index < 20:
                    text += f"{title}\n"
                    options.append(f"{regex_result.group(2).replace('_', ' ')} ({row[4]}-#{regex_result.group(1)})")
                    series_options.append(row[1])
                    num_index += 1
                else:
                    page_text.append(text)
                    dropdown_options.append(options)
                    series.append(series_options)
                    text = f"{title}\n"
                    num_index = 0
                    options = [f"{regex_result.group(2).replace('_', ' ')} (#{regex_result.group(1)}, {row[1].split('-')[0]})"]
                    series_options = [row[1]]
            page_text.append(text)
            dropdown_options.append(options)
            series.append(series_options)

            all_pages = []
            for p, page in enumerate(page_text):
                embed = Embed(title=f"{ctx.author.display_name}'s Inventory", description="", colour=ctx.author.colour)
                embed.add_field(name="Bub Bucks", value=f"{points}{self.bub}")
                embed.add_field(name="Unopened Card Packs", value=f"{packs}")
                embed.add_field(name="Cards in Collection", value=f"{num_cards}")
                embed.add_field(name="Unique Cards", value=f"{len(rows)}")
                embed.add_field(name="Cards Obtained From Trades", value=f"{num_traded}")
                embed.add_field(name="Card Collection (Rarity, Set, Name, # Owned)", value=f"{page}", inline=False)
                all_pages.append(pages.Page(embeds=[embed], custom_view=views.CardsDropdownView(dropdown_options[p], series[p], self.game_database)))

            paginator = pages.Paginator(pages=all_pages, disable_on_timeout=True, timeout=600)
            await paginator.respond(ctx.interaction, ephemeral=False)
        else:
            embed = Embed(title=f"{ctx.author.display_name}'s Inventory", description="", colour=ctx.author.colour)
            embed.add_field(name="Bub Bucks", value=f"{points}{self.bub}")
            embed.add_field(name="Unopened Card Packs", value=f"{packs}")
            embed.add_field(name="Cards in Collection", value=f"{num_cards}")
            embed.add_field(name="Unique Cards", value=f"{len(rows)}")
            embed.add_field(name="Card Collection (Rarity, Name)", value=f"0 cards")
            await ctx.respond(embed=embed)
        print(f"{datetime.now()}: /cards inventory called by {ctx.author.display_name}")

    @cards.command(description="Open a card pack!", name="open")
    async def open_purchased_pack(self, ctx):
        await ctx.defer()
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()
        packs = cursor.execute("SELECT packs FROM players WHERE player_id = ?;", (ctx.author.id,)).fetchone()
        if packs:
            num_packs = packs[0]
            series_texts = [s for (s,) in cursor.execute("SELECT prettify FROM sets;").fetchall()]
            if num_packs > 0:
                embed = Embed(title=f"You have {num_packs} card pack(s).", description="Choose a set to open.", colour=ctx.author.colour)
                card_series_text = '\n'.join([s for s in series_texts])
                embed.add_field(name="Available Sets", value=f"{card_series_text}")
                image = discord.File(f"./data/cards/1990-Impel-Marvel-Universe/1990-Impel-Marvel-Universe-Trading-Cards-all.png", filename="card-pack.png")
                embed.set_image(url="attachment://card-pack.png")
                view = views.OpenCardPack(ctx, self.bot, num_packs, self.card_series, series_texts)
                await ctx.respond(embed=embed, view=view, file=image)
        else:
            (points,) = cursor.execute("SELECT points FROM players WHERE player_id = ?;", (ctx.author.id,)).fetchone()
            await ctx.respond(f"You don't have any card packs; you have enough bub bucks to buy {floor(points/self.pack_cost)}. "
                              f"Type **/cards buy** to purchase one.")
        connection.close()
        print(f"{datetime.now()}: /cards open called by {ctx.author.display_name}")

    async def list_num_packs_to_buy(self, ctx: discord.AutocompleteContext):
        num = ["1", "5", "10", "max"]
        return [c for c in num if ctx.value.lower() in c.lower()]

    @cards.command(description="Buy a card pack!", name="buy")
    async def buy_card_pack(self, ctx,
                            number: Option(str, "Number of packs to buy.",
                                           default="1", autocomplete=list_num_packs_to_buy, required=True)):
        await ctx.defer()
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()
        if number == "max":
            (total_points,) = cursor.execute("SELECT points FROM players WHERE player_id = ?;", (ctx.author.id,)).fetchone()
            number = floor(total_points/self.pack_cost)
        embed, image, points = await self.buy_cards(connection, cursor, ctx.author.id, int(number))
        (num_packs,) = cursor.execute("SELECT packs FROM players WHERE player_id = ?;", (ctx.author.id,)).fetchone()
        series_text = [s for (s,) in cursor.execute("SELECT prettify FROM sets;").fetchall()]
        connection.close()
        if embed:
            view = views.OpenCardPack(ctx, self.bot, num_packs, self.card_series, series_text)
            await ctx.respond(file=image, embed=embed, view=view)
        else:
            await ctx.respond(f"Card packs cost {self.pack_cost}{self.bub} each; you currently have {points}{self.bub}. To earn bub bucks, chat on Discord or post on the site.")
        print(f"{datetime.now()}: /cards buy called by {ctx.author.display_name}")

    async def open_card_pack(self, ctx, series=None):
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()

        cards, _ = self.choose_random_card(cursor, num=12, series=series)
        thumbnail_paths = []
        image_series = []
        for card in cards:
            (thumbnail, series) = cursor.execute("SELECT thumbnail_path, series FROM cards WHERE card_id = ? AND series = ?;", (card, series)).fetchone()
            thumbnail_paths.append(thumbnail)
            image_series.append(series)

        merged_image = merge_thumbnail_images([f"./data/cards/{image_series[i]}/thumbnail/{thumbnail_paths[i]}" for i in range(len(thumbnail_paths))])

        embed_open = Embed(title="You opened a card pack! 🎉", description="", colour=discord.Colour.blurple())
        with BytesIO() as image_binary:
            merged_image.save(image_binary, 'PNG')
            image_binary.seek(0)
            image_open = discord.File(fp=image_binary, filename="card-open.png")
        embed_open.set_image(url="attachment://card-open.png")

        card_titles = []
        card_series = []
        date_time = datetime.now()
        for n in range(len(thumbnail_paths)):
            if "X-Men" in image_series[n]:
                pattern = rf"{image_series[n].split('X-Men')[0].replace('-', '_')}X-Men_#(\d+|XH\d+|)_(.+?)_thumbnail.jpg"
            else:
                pattern = rf"{image_series[n].replace('-', '_')}_#(\d+|MH\d+)_(.+?)_thumbnail.jpg"
            regex_result = re.search(pattern, thumbnail_paths[n])
            (card_count,) = cursor.execute("SELECT COUNT (*) FROM collection WHERE player_id = ? AND card_id = ? AND series = ?;", (ctx.author.id, cards[n], image_series[n])).fetchone()
            (set_code,) = cursor.execute("SELECT shorthand FROM sets WHERE series = ?;", (image_series[n],)).fetchone()
            card_series.append(image_series[n])
            if card_count > 0:
                card_titles.append(f"{regex_result.group(2).replace('_', ' ')} ({set_code}-#{regex_result.group(1)})")
            else:
                card_titles.append(f"🆕 {regex_result.group(2).replace('_', ' ')} ({set_code}-#{regex_result.group(1)})")
            cursor.execute("INSERT INTO collection (player_id, card_id, series, date_time) "
                           "VALUES (?, ?, ?, ?);", (ctx.author.id, cards[n], image_series[n], date_time))

        (packs,) = cursor.execute("SELECT packs FROM players WHERE player_id = ?;", (ctx.author.id,)).fetchone()
        cursor.execute("UPDATE players SET packs = ? WHERE player_id = ?;", (packs - 1, ctx.author.id))
        connection.commit()
        connection.close()

        set_card_titles = []
        set_card_series = []
        embed_open.add_field(name=f"Cards Gained", value=f"{', '.join(card_titles)}")
        for i in range(len(card_titles)):
            if card_titles[i] not in set_card_titles:
                set_card_titles.append(card_titles[i])
                set_card_series.append(card_series[i])
        view_dropdown = views.CardsDropdownView(set_card_titles, set_card_series, self.game_database)
        return image_open, embed_open, view_dropdown

    async def list_all_cards(self, ctx: discord.AutocompleteContext):
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()
        pattern = rf"_#(\d+|MH\d+|XH\d+)_(.+?).(png|gif)"
        (series,) = cursor.execute("SELECT series FROM sets WHERE prettify = ?;", (ctx.options['series'],)).fetchone()
        cards = []
        for (image_path,) in cursor.execute("SELECT image_path FROM cards WHERE series = ? ORDER BY LENGTH(card_id), card_id;", (series,)).fetchall():
            regex_result = re.search(pattern, image_path)
            cards.append(f"#{regex_result.group(1)}: {regex_result.group(2).replace('_', ' ')}")
        connection.close()
        return [c for c in cards if ctx.value.lower() in c.lower()]

    async def get_all_series(self, ctx: discord.AutocompleteContext):
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()
        series = [s for (s,) in cursor.execute("SELECT prettify FROM sets;").fetchall()]
        connection.close()
        return [s for s in sorted(series) if ctx.value.lower() in s.lower()]

    @cards.command(description="Look up a card.", name="search")
    async def search_cards(self, ctx,
                           series: Option(str, "Trading card series.", required=True, autocomplete=get_all_series),
                           card: Option(str, "Card name.", required=True, autocomplete=list_all_cards)):
        await ctx.defer()
        card_id = re.search(rf"#(\d+|MH\d+|XH\d+):", card).group(1)
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()
        (series,) = cursor.execute("SELECT series FROM sets WHERE prettify = ?;", (series,)).fetchone()
        result = cursor.execute("SELECT image_path, series, rarity FROM cards WHERE card_id = ? AND series = ?;", (card_id, series)).fetchall()
        (series_text,) = cursor.execute("SELECT prettify FROM sets WHERE series = ?;", (series,)).fetchone()
        # Retrieve number of this card owned by all players in the guild
        num_cards = 0
        owned_by = []
        for member in ctx.guild.members:
            (count,) = cursor.execute("SELECT COUNT(*) FROM collection WHERE card_id = ? AND series = ? AND player_id = ?;", (card_id, series, member.id)).fetchone()
            if count > 0:
                num_cards += count
                owned_by.append(member.id)
        connection.close()
        embed, image = tools.trading_card_embed_standard(result[0][1], result[0][0], result[0][2], num_cards, series_text)
        if len(owned_by) > 0:
            counter = Counter(owned_by)
            value = '\n'.join([f"<@{p}> ({counter[p]})" for p in counter.keys()])
            embed.add_field(name="Owned by", value=f"{value}")
        else:
            embed.add_field(name="Owned by", value="No one")
        await ctx.respond(file=image, embed=embed)
        print(f"{datetime.now()}: /cards search called by {ctx.author.display_name}")

    def setup_trade(self, cursor, card_id_list, member_id, series):
        counter = Counter(card_id_list)
        counter_all = {}
        rowids = []
        cards_dict = {}
        for card in card_id_list:
            rows = cursor.execute("SELECT cards.card_id, cards.image_path, collection.rowid FROM cards "
                                  "JOIN collection ON (cards.card_id = collection.card_id AND cards.series = collection.series) "
                                  "WHERE collection.player_id = ? AND collection.card_id = ? AND collection.series = ?;", (member_id, card, series)).fetchall()
            counter_all[card] = len(rows)
            num = 0
            for row in rows:
                if num < counter[card]:
                    cards_dict[row[0]] = row[1]
                    rowids.append(row[2])
                    num += 1
                else:
                    break
        card_names = []
        if len(rowids) > 0:
            pattern = rf"_#(\d+|MH\d+|XH\d+)_(.+?).(png|gif)"
            for card_id in cards_dict.keys():
                regex_result = re.search(pattern, cards_dict[card_id])
                card_names.append(
                    f"Card #{regex_result.group(1)}: {regex_result.group(2).replace('_', ' ')} ({counter_all[card_id]} owned)")
            return [card_names, rowids]
        else:
            return None

    async def get_all_series(self, ctx: discord.AutocompleteContext):
        connection = sqlite3.connect(self.game_database)
        cursor = connection.cursor()
        series = [s for (s,) in cursor.execute("SELECT DISTINCT series FROM cards;").fetchall()]
        connection.close()
        return [s for s in sorted(series) if ctx.value.lower() in s.lower()]

    @cards.command(description="Trade cards with another member!", name="trade")
    async def trade_cards(self, ctx,
                          member: Option(discord.Member, "Member to trade with.", required=True),
                          your_cards: Option(str, "The cards you will trade. Enter card numbers, comma-separated, e.g. '1, 100, MH4'.", required=True),
                          your_series: Option(str, "The series your cards are from.", required=True, autocomplete=get_all_series),
                          member_cards: Option(str, "The cards you will receive. Enter card numbers, comma-separated, e.g. '4, MH2, 39'.", required=True),
                          member_series: Option(str, "The series the member's cards are from.", required=True, autocomplete=get_all_series)):
        if ctx.author == member:
            await ctx.respond("You can't trade with yourself.")
        elif member.bot:
            await ctx.respond("Bots can't trade cards.")
        else:
            # Parse arguments and turn into lists
            cards_give = [c.replace("#", "").strip() for c in your_cards.split(',')]
            cards_take = [c.replace("#", "").strip() for c in member_cards.split(',')]

            connection = sqlite3.connect(self.game_database)
            cursor = connection.cursor()

            parameters_give = self.setup_trade(cursor, cards_give, ctx.author.id, your_series)
            parameters_take = self.setup_trade(cursor, cards_take, member.id, member_series)

            if parameters_give and parameters_take:
                cards_give_string = '\n'.join(parameters_give[0])
                cards_take_string = '\n'.join(parameters_take[0])
                embed = Embed(title=f"{ctx.author.display_name} wants to trade!", description="", colour=ctx.author.colour)
                embed.add_field(name=f"{ctx.author.display_name} will trade...", value=f"{cards_give_string}")
                embed.add_field(name=f"... for {member.display_name}'s...", value=f"{cards_take_string}")
                view = views.CardsTradeView(ctx, allowed=member)
                await ctx.respond(f"{member.mention}, do you accept the trade?", embed=embed, view=view)
                await view.wait()
                if view.value:
                    for rowid in parameters_take[1]:
                        cursor.execute("UPDATE collection SET player_id = ?, trade = ? WHERE rowid = ?;", (ctx.author.id, member.id, rowid))
                    for rowid in parameters_give[1]:
                        cursor.execute("UPDATE collection SET player_id = ?, trade = ? WHERE rowid = ?;", (member.id, ctx.author.id, rowid))
                    connection.commit()
            else:
                await ctx.respond(f"Sorry, I don't recognise the listed cards: **{your_cards}** and **{member_cards}**. Please check the card numbers and try again.")
            connection.close()
        print(f"{datetime.now()}: /cards trade called by {ctx.author.display_name}")

    @Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            connection = sqlite3.connect(self.game_database)
            cursor = connection.cursor()
            try:
                (current_points,) = cursor.execute("SELECT points FROM players WHERE player_id = ?;", (message.author.id,)).fetchone()
            except TypeError:  # Add player if not in database
                cursor.execute("INSERT INTO players (player_id, points, packs) VALUES (?, ?, ?);", (message.author.id, self.pack_cost, 0))
                connection.commit()
                (current_points,) = cursor.execute("SELECT points FROM players WHERE player_id = ?;", (message.author.id,)).fetchone()
            cursor.execute("UPDATE players SET points = ? WHERE player_id = ?;", (current_points+self.message_reward, message.author.id))
            connection.commit()
            connection.close()

    @Cog.listener()
    async def on_member_join(self, member):
        if not member.bot:
            connection = sqlite3.connect(self.game_database)
            cursor = connection.cursor()
            member_is_registered = cursor.execute("SELECT * FROM players WHERE player_id = ?;", (member.id,)).fetchone()
            if not member_is_registered:  # If member is new, add them to database
                cursor.execute("INSERT INTO players (player_id, points, packs) VALUES (?, ?, ?);", (member.id, 500, 0))
            connection.commit()
            connection.close()

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.game_database = self.bot.game_database

            # Create database and populate with cards if it doesn't already exist
            connection = sqlite3.connect(self.game_database)
            cursor = connection.cursor()
            try:  # Add additional series if they don't exist
                series = [s for (s,) in cursor.execute("SELECT DISTINCT series FROM cards;").fetchall()]
                for s in range(len(self.card_series)):
                    if self.card_series[s] not in series:
                        add_cards_to_db(cursor, [self.card_series[s]], [self.card_directories[s]], [self.thumbnail_directories[s]])
                        connection.commit()
                    # Weight card draws by number of cards in each rarity and the probability of that rarity
                    rarity = [int(r) for (r,) in cursor.execute("SELECT rarity FROM cards WHERE series = ?;", (self.card_series[s],)).fetchall()]
                    counter = Counter(rarity)
                    self.rarity_weights[self.card_series[s]] = {r: self.rarity[r] / counter[r] for r in self.rarity.keys()}
                connection.close()
            except sqlite3.OperationalError:
                print("No database found!")

            self.bot.cogs_ready.ready_up('game')


def setup(bot):
    bot.add_cog(Game(bot))
