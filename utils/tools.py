import discord
import re


def get_key_from_value(d, val):
    return [k for k, v in d.items() if v == val]


def trading_card_embed_standard(series, image_path, rarity_rank, num_cards, series_text):
    # Creates standard template for viewing trading card
    rarity = {1: "🔹 (Common)", 2: "🔹🔹 (Uncommon)", 3: "🔹🔹🔹 (Rare)", 4: "🔸🔸🔸🔸 (Epic)", 5: "♦️♦️♦️♦️♦️ (Legendary!)"}

    if ".gif" in image_path:
        image_type = "gif"
    else:
        image_type = "png"
    image = discord.File(f"./data/cards/{series}/merged/{image_path}", filename=f"card.{image_type}")
    pattern = rf"_#(\d+|MH\d+|XH\d+)_(.+?).{image_type}"
    regex_result = re.search(pattern, image_path)

    if rarity_rank <= 3:
        colour = discord.Colour.blue()
    elif rarity_rank == 4:
        colour = discord.Colour.orange()
    else:
        colour = discord.Colour.red()

    embed = discord.Embed(title=f"Card #{regex_result.group(1)}: {regex_result.group(2).replace('_', ' ')}",
                          colour=colour)
    embed.add_field(name=f"Set", value=f"{series_text}", inline=False)
    embed.add_field(name=f"Rarity: {rarity[rarity_rank]}",
                    value=f"There {'is' if num_cards == 1 else 'are'} currently {num_cards} of this card in circulation.")
    embed.set_image(url=f"attachment://card.{image_type}")

    return embed, image
