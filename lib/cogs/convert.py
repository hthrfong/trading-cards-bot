import discord
from discord.ext.commands import Cog
from discord.commands import slash_command, Option, SlashCommandGroup
import re
from datetime import datetime, timedelta, time
import pytz
from dateutil import parser
import dateutil.tz


def convert_temp(value, unit):
    if unit == 'F':
        return round((value - 32) * (5 / 9), 1)
    if unit == 'C':
        return round(value * (9 / 5) + 32, 1)


class Convert(Cog):
    def __init__(self, bot):
        self.bot = bot

        # Temperature
        self.keywords = {"F": ['degrees f', 'deg f', 'deg. f', 'fahrenheit', '°f', 'f\\b'],
                         "C": ['degrees c', 'deg c', 'deg. c', 'celsius', '°c', 'c\\b']}
        self.temperature_pattern = r"([-+]?[.\d]+)\s*(%s)" % ('|'.join(sum(self.keywords.values(), [])))
        self.time_pattern = r"\b\d{1,2}(?::\d{2})?\s*[ap]m\b"

        self.fmt = "%a %b %-d, %Y, %H:%M %Z%z"

        # Timezone
        self.timezones = {"UTC-10 (Hawaii, Tahiti)": "Pacific/Honolulu",
                          "UTC-9 (Alaska)": "America/Anchorage",
                          "UTC-8 (California, Seattle, Vancouver)": "America/Los_Angeles",
                          "UTC-7 (Arizona, Colorado)": "America/Edmonton",
                          "UTC-6 (Chicago, Guatemala, Mexico City, Minnesota, Talokan)": "America/Chicago",
                          "UTC-5 (Detroit, New York, Toronto)": "America/Toronto",
                          "UTC-4 (Barbados, Genosha, Puerto Rico)": "America/Barbados",
                          "UTC-3 (Buenos Aires, Cordoba, Sao Paulo)": "America/Sao_Paulo",
                          "UTC-2 (Greenland)": "America/Nuuk",
                          "UTC (Portugal, United Kingdom)": "Europe/London",
                          "UTC+1 (France, Germany, Netherlands, Poland)": "Europe/Berlin",
                          "UTC+2 (Egypt, Latveria, Israel, Ukraine)": "Europe/Kyiv",
                          "UTC+3 (Kuwait, Moscow, Turkey, Wakanda)": "Europe/Moscow",
                          "UTC+4 (Dubai, Mauritius)": "Indian/Mauritius",
                          "UTC+5 (Maldives)": "Indian/Maldives",
                          "UTC+5:30 (India)": "Asia/Kolkata",
                          "UTC+7 (Jakarta, Thailand, Vietnam)": "Asia/Jakarta",
                          "UTC+8 (Hong Kong, Madripoor, Malaysia, Singapore, Taiwan)": "Asia/Hong_Kong",
                          "UTC+9 (Japan, North Korea, South Korea)": "Asia/Tokyo",
                          "UTC+10 (Melbourne, Sydney)": "Australia/Sydney",
                          "UTC+12 (New Zealand)": "Pacific/Auckland"}

    def possible_timezones(self, tz_offset, common_only=True):
        # pick one of the timezone collections
        if common_only:
            timezones = list(self.timezones.values())
        else:
            timezones = pytz.all_timezones

        # convert the float hours offset to a timedelta
        offset_days, offset_seconds = 0, int(tz_offset * 3600)
        if offset_seconds < 0:
            offset_days = -1
            offset_seconds += 24 * 3600
        desired_delta = timedelta(offset_days, offset_seconds)

        # Loop through the timezones and find any with matching offsets
        null_delta = timedelta(0, 0)
        results = []
        for tz_name in timezones:
            tz = pytz.timezone(tz_name)
            non_dst_offset = getattr(tz, '_transition_info', [[null_delta]])[-1]
            if desired_delta == non_dst_offset[0]:
                results.append(tz_name)

        return results

    time = SlashCommandGroup("time", "Convert or get time in different timezones.")

    async def autocomplete_timezones(self, ctx: discord.AutocompleteContext):
        timezones = [tz for tz in self.timezones.keys()]
        return [tz for tz in timezones if ctx.value.lower() in tz.lower()]

    @time.command(description="Convert date/time.", name="convert")
    async def convert_time(self, ctx,
                           date_time: Option(str, "The date/time to be converted (e.g. 'Jan 1 2021 3pm').", required=True),
                           timezone1: Option(str, "Timezone of date_time (default: UTC). Accounts for daylight savings.",
                                            required=True, autocomplete=autocomplete_timezones, default='UTC'),
                           timezone2: Option(str, "Timezone to convert to (default: current players' timezones). Accounts for daylight savings.",
                                             required=True, autocomplete=autocomplete_timezones, default=None)):
        default_date = datetime.combine(datetime.now(), time(0, tzinfo=dateutil.tz.gettz(self.timezones[timezone1])))
        try:
            datetime_obj = parser.parse(date_time, default=default_date)
            time_converted = [datetime_obj.astimezone(pytz.timezone(self.timezones[timezone2]))]
            output = '\n'.join([f"**{dt.strftime('UTC%z (%Z)')}:** {dt.strftime(self.fmt)}" for dt in time_converted])
            await ctx.respond(f"**{datetime_obj.strftime(self.fmt)}**\n{output}")
        except parser.ParserError:
            await ctx.respond(f"I don't understand this time: '{date_time}'.")
            raise ValueError(f"User inputted invalid time format: {date_time}.")
        print(f"{datetime.now()}: /time convert called by {ctx.author.display_name}")

    @time.command(description="Get the current time of various locations.", name="now")
    async def get_time_now(self, ctx,
                           timezone: Option(str, "Desired timezone (default: current players' timezones). Accounts for daylight savings.",
                                            required=True, autocomplete=autocomplete_timezones, default=None)):
        now_utc = datetime.now(tz=pytz.UTC)
        time_converted = now_utc.astimezone(pytz.timezone(self.timezones[timezone].replace(' ', '_')))
        await ctx.respond(f"**{time_converted.strftime('UTC%z (%Z)')}:** {time_converted.strftime(self.fmt)}")
        print(f"{datetime.now()}: /time now called by {ctx.author.display_name}")

    @Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            if message.guild:
                msg = message.content.lower()
                if not any([m in msg for m in ['http://', 'https://', '.jpg', '.gif', '.png']]):  # Don't search for links or images
                    temperature_matches = re.findall(self.temperature_pattern, message.content.lower())
                    if temperature_matches:
                        msgs = []
                        for match in temperature_matches:
                            temperature = float(match[0])
                            for key, value in self.keywords.items():
                                for val in value:
                                    if match[1] in val:
                                        converted_temperature = convert_temp(temperature, key)
                                        converted_unit = 'F' if key == 'C' else 'C'
                                        msgs.append(f"{temperature}°{key} = {converted_temperature}°{converted_unit}")
                                        break
                        await message.channel.send('\n'.join(msgs))

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up('convert')


def setup(bot):
    bot.add_cog(Convert(bot))
