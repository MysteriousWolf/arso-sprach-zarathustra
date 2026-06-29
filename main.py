import argparse
import functools
import logging
import sys
import tempfile
import time
from datetime import datetime

import discord
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import app_commands
from rich.markup import escape

import arso as arso_module
from arso import ARSO
from banner import BOT_VERSION as _BOT_VERSION
from banner import GIT_COMMIT as _GIT_COMMIT
from banner import print_banner as _print_banner
from utils.ColorUtils import ColorUtils, color_to_discord
from utils.log import fmt_cmd, fmt_entity, fmt_id, fmt_timing, get_logger, setup_logging

logger = get_logger("bot")

_REPO = "https://github.com/MysteriousWolf/arso-sprach-zarathustra"
_COLOR_ARSO = discord.Color.from_rgb(0, 130, 188)
_COLOR_ARSO_NEON = discord.Color.from_rgb(0, 176, 255)
_COLOR_EMBED = _COLOR_ARSO


def log_command(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        user = fmt_entity(interaction.user.name, interaction.user.id)
        guild = (
            fmt_entity(interaction.guild.name, interaction.guild.id) if interaction.guild else "DM"
        )
        logger.info(f"{fmt_cmd(func.__name__)} by {user} @ {guild}")
        t0 = time.monotonic()
        try:
            result = await func(interaction, *args, **kwargs)
            elapsed = f"{time.monotonic() - t0:.2f}"
            logger.info(f"{fmt_cmd(func.__name__)} ok {fmt_timing(elapsed)}")
            return result
        except Exception:
            elapsed = f"{time.monotonic() - t0:.2f}"
            logger.exception(f"{fmt_cmd(func.__name__)} failed {fmt_timing(elapsed)}")
            raise

    return wrapper


class ARSOClient(discord.Client):
    config: dict
    config_file: str
    tree: app_commands.CommandTree
    start_time: datetime

    def __init__(self, *, intents: discord.Intents, config_file="config.yaml"):
        super().__init__(intents=intents)
        self.config_file = config_file
        self.temp_dir = tempfile.gettempdir()
        self.tree = app_commands.CommandTree(self)
        self.arso = ARSO(self.temp_dir)
        self.cu = ColorUtils()

        try:
            logger.info(f"reading config {escape(config_file)}")
            with open(config_file, "r+") as stream:
                try:
                    loaded = yaml.safe_load(stream)
                    if not isinstance(loaded, dict):
                        sys.exit("Config file is empty or invalid.")
                    self.config = loaded
                except yaml.YAMLError as exc:
                    sys.exit(f"An error occurred when trying to parse the config file: {exc}")
            self.dedup_channels()
        except FileNotFoundError:
            logger.warning("config not found, creating template")
            self.config = {
                "token": "[insert your Discord bot token here]",
                "channels": [],
                "polna_napoved_ob": "18",
                "povzetek_napovedi_ob": "6",
            }
            self.store_config()
            sys.exit("Please fill out the config file.")

    async def setup_hook(self):
        """print(self.guilds)
        for server in self.guilds:
            self.tree.copy_global_to(guild=server)
            await self.tree.sync(guild=server)"""
        pass

    def generate_forecast_panel(self, paragraphs=-1):
        fc = self.arso.get_forecast(paragraphs)

        tble = self.arso.get_morn_even_table()
        file = discord.File(tble, filename="morn_tabela.png")

        embed = discord.Embed(
            color=color_to_discord(self.cu.get_current_color()), title=fc["title"]
        )
        embed.add_field(name="Tekstovna napoved", value=fc["body"], inline=True)
        embed.set_footer(text="ARSO").timestamp = fc["timestamp"]
        embed.set_author(name=fc["author"], url=arso_module.HOME_URL)
        embed.set_thumbnail(url=arso_module.THUMBNAIL_URL)
        embed.set_image(url="attachment://morn_tabela.png")

        return {"file": file, "embed": embed}

    def generate_obeti_panel(self):
        fc = self.arso.get_obeti()

        tble = self.arso.get_3day_table()
        file = discord.File(tble, filename="napoved_tabela.png")

        embed = discord.Embed(color=_COLOR_EMBED, title=fc["title"])
        embed.add_field(name="Tekstovna napoved", value=fc["body"], inline=True)
        embed.set_footer(text="ARSO").timestamp = fc["timestamp"]
        embed.set_author(name=fc["author"], url=arso_module.HOME_URL)
        embed.set_thumbnail(url=arso_module.THUMBNAIL_URL)
        embed.set_image(url="attachment://napoved_tabela.png")

        return {"file": file, "embed": embed}

    def generate_precipitation_panel(self):
        gif = self.arso.get_percipitation_gif()
        filename = datetime.now().strftime("%Y%m%d-%H%M-si0-rm-anim.gif")
        file = discord.File(gif, filename=filename)

        embed = discord.Embed(
            color=color_to_discord(self.cu.get_current_color()), title="Radarska slika padavin"
        )
        embed.set_footer(text="ARSO").timestamp = datetime.now()
        embed.set_author(
            name="Vir: Agencija Republike Slovenije za okolje",
            url=arso_module.RADAR_AUTHOR_URL,
        )
        embed.set_thumbnail(url=arso_module.THUMBNAIL_URL)
        embed.set_image(url=f"attachment://{filename}")

        return {"file": file, "embed": embed}

    async def _broadcast(self, job: str, panel_fn):
        channels = self.config["channels"]
        cron = f"[bot.cron]cron.{escape(job)}[/bot.cron]"
        logger.info(f"{cron} starting, [bot.count]{len(channels)}[/bot.count] channel(s)")
        t0 = time.monotonic()
        ok = fail = 0
        for ch in channels:
            chnl = self.get_channel(ch)
            if not isinstance(chnl, discord.abc.Messageable):
                logger.warning(f"{cron} channel {fmt_id(ch)} not found or not messageable")
                fail += 1
                continue
            try:
                await chnl.send(**panel_fn())
                ok += 1
            except Exception:
                logger.exception(f"{cron} channel {fmt_id(ch)} send failed")
                fail += 1
        elapsed = f"{time.monotonic() - t0:.2f}"
        if fail:
            logger.warning(
                f"{cron} done {fmt_timing(elapsed)}, ok={ok} [bot.fail]fail={fail}[/bot.fail]"
            )
        else:
            logger.info(f"{cron} done {fmt_timing(elapsed)}, [bot.ok]ok={ok}[/bot.ok]")

    async def send_weather(self):
        await self._broadcast("send_weather", self.generate_forecast_panel)

    async def send_recap(self):
        await self._broadcast("send_recap", lambda: self.generate_forecast_panel(paragraphs=1))

    def dedup_channels(self):
        channels = self.config.get("channels") or []
        unique = set(channels)
        if len(unique) < len(channels):
            logger.info(
                f"removed [bot.count]{len(channels) - len(unique)}[/bot.count] duplicate channel(s) from config"
            )
            self.config["channels"] = list(unique)
            self.store_config()

    def store_config(self):
        with open(self.config_file, "w+") as stream:
            try:
                yaml.safe_dump(self.config, stream)
            except yaml.YAMLError as exc:
                logger.error(f"failed to write config: {exc}")

    def add_channel(self, channel_id):
        if channel_id in self.config["channels"]:
            logger.info(f"channel {fmt_id(channel_id)} already subscribed")
            return "Za ta kanal je avtomatsko pošiljanje prognoze že omogočeno"
        self.config["channels"].append(channel_id)
        self.store_config()
        logger.info(
            f"channel {fmt_id(channel_id)} added - [bot.count]{len(self.config['channels'])}[/bot.count] total"
        )
        return "Avtomatsko pošiljanje prognoze omogočeno v tem kanalu"

    def remove_channel(self, channel_id):
        if channel_id not in self.config["channels"]:
            logger.info(f"channel {fmt_id(channel_id)} not subscribed")
            return "Ta kanal še nima omogočenega avtomatskega pošiljanja prognoze"
        self.config["channels"].remove(channel_id)
        self.store_config()
        logger.info(
            f"channel {fmt_id(channel_id)} removed - [bot.count]{len(self.config['channels'])}[/bot.count] remaining"
        )
        return "Avtomatsko pošiljanje prognoze odstranjeno"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    _print_banner()
    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    disc_intents = discord.Intents.default()
    disc_intents.message_content = True
    client = ARSOClient(intents=disc_intents)

    scheduler = AsyncIOScheduler()

    @client.event
    async def on_ready():
        assert client.user is not None
        client.start_time = datetime.now()
        logger.info(f"logged on as {fmt_entity(client.user.name, client.user.discriminator)}")

        for server in client.guilds:
            client.tree.copy_global_to(guild=server)
            await client.tree.sync(guild=server)

        logger.info("commands synced")

        # test pošiljanja v kanal
        # scheduler.add_job(client.send_weather, 'interval', seconds=5)

        # polna napoved
        scheduler.add_job(client.send_weather, "cron", hour=client.config["polna_napoved_ob"])

        # kratka napoved - zaenkrat isto
        scheduler.add_job(client.send_recap, "cron", hour=client.config["povzetek_napovedi_ob"])
        scheduler.start()

        logger.info("cron tasks started")

    @client.event
    async def on_message(message):
        if client.user and message.author.id == client.user.id:
            return

    @client.tree.command()
    @log_command
    async def vreme(interaction: discord.Interaction):
        """Izpiše napoved za današnji dan"""
        await interaction.response.defer()
        await interaction.followup.send(**client.generate_forecast_panel())

    @client.tree.command()
    @log_command
    async def obeti(interaction: discord.Interaction):
        """Izpiše obeti"""
        await interaction.response.defer()
        await interaction.followup.send(**client.generate_obeti_panel())

    @client.tree.command()
    @log_command
    async def padavine(interaction: discord.Interaction):
        """Izpiše padavine or something"""
        await interaction.response.defer()
        await interaction.followup.send(**client.generate_precipitation_panel())

    @client.tree.command()
    @log_command
    async def dnevno_vreme(interaction: discord.Interaction):
        """Doda trenutni kanal za dnevna sporočila"""
        await interaction.response.send_message(client.add_channel(interaction.channel_id))

    @client.tree.command()
    @log_command
    async def nednevno_vreme(interaction: discord.Interaction):
        """Odstrani trenutni kanal za dnevna sporočila"""
        await interaction.response.send_message(client.remove_channel(interaction.channel_id))

    @client.tree.command()
    @log_command
    async def version(interaction: discord.Interaction):
        """Prikaže trenutno verzijo bota"""
        assert client.user is not None
        uptime = datetime.now() - client.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        commit_str = ""
        if _GIT_COMMIT:
            short = _GIT_COMMIT[:7]
            commit_str = f" ([`{short}`]({_REPO}/commit/{_GIT_COMMIT}))"

        msg = (
            f"## [{client.user.name}]({_REPO}) v{_BOT_VERSION}{commit_str}\n"
            f"Unofficial ARSO Discord weather bot *by [MysteriousWolf](https://github.com/MysteriousWolf)*\n"
            f"**Uptime:** {hours}h {minutes}m {seconds}s (since <t:{int(client.start_time.timestamp())}:f>)"
        )
        await interaction.response.send_message(msg, suppress_embeds=True)

    client.run(client.config["token"], log_handler=None)
