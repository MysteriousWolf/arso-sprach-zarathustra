import argparse
import functools
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import discord
import yaml
from discord import app_commands
from rich.markup import escape

import arso as arso_module
from arso import ARSO, TRIESTE, geocode_location, within_slovenia
from banner import BOT_VERSION as _BOT_VERSION
from banner import GIT_COMMIT as _GIT_COMMIT
from banner import print_banner as _print_banner
from utils.ColorUtils import (
    ARSO_NEON,
    ARSO_PRIMARY,
    ColorUtils,
    color_to_discord,
)
from utils.log import (
    fmt_channel_link,
    fmt_cmd,
    fmt_fail,
    fmt_guild_link,
    fmt_id,
    fmt_ok,
    fmt_timing,
    fmt_user_link,
    fmt_warn,
    get_logger,
    setup_logging,
)
from utils.scheduler import create_scheduler, log_next_runs

logger = get_logger("bot")

_REPO = "https://github.com/MysteriousWolf/arso-sprach-zarathustra"
_COLOR_ARSO = discord.Color.from_rgb(*ARSO_PRIMARY)
_COLOR_ARSO_NEON = discord.Color.from_rgb(*ARSO_NEON)
_COLOR_EMBED = _COLOR_ARSO


def _last_scheduled_time(hour: int, now: datetime) -> datetime:
    slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return slot if now >= slot else slot - timedelta(days=1)


def log_command(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        user = fmt_user_link(interaction.user.name, interaction.user.id)
        if interaction.guild:
            guild_str = fmt_guild_link(
                interaction.guild.name, interaction.guild.id
            )
            ch = interaction.channel
            if isinstance(ch, discord.abc.GuildChannel):
                ch_link = fmt_channel_link(
                    ch.name, ch.id, interaction.guild.id
                )
                location = f"{ch_link} > {guild_str}"
            else:
                location = guild_str
        else:
            location = "DM"
        logger.info(f"{fmt_cmd(func.__name__)} by {user} @ {location}")
        t0 = time.monotonic()
        try:
            result = await func(interaction, *args, **kwargs)
            elapsed = f"{time.monotonic() - t0:.2f}"
            logger.info(
                f"{fmt_cmd(func.__name__)} {fmt_ok()} {fmt_timing(elapsed)}"
            )
            return result
        except Exception:
            elapsed = f"{time.monotonic() - t0:.2f}"
            logger.exception(
                f"{fmt_cmd(func.__name__)} failed {fmt_timing(elapsed)}"
            )
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
        self.cu = ColorUtils()
        self._connected_once = False
        self._last_fired: dict[str, datetime] = {}
        self.start_time = datetime.now()

        try:
            logger.info(f"reading config {escape(config_file)}")
            with open(config_file, "r+") as stream:
                try:
                    loaded = yaml.safe_load(stream)
                    if not isinstance(loaded, dict):
                        sys.exit("Config file is empty or invalid.")
                    self.config = loaded
                except yaml.YAMLError as exc:
                    sys.exit(
                        "An error occurred when trying to parse"
                        f" the config file: {exc}"
                    )
            self.dedup_channels()
        except FileNotFoundError:
            logger.warning("config not found, creating template")
            self.config = {
                "token": "[insert your Discord bot token here]",
                "channels": [],
                "polna_napoved_ob": "18",
                "povzetek_napovedi_ob": "6",
                "dark_mode": True,
            }
            self.store_config()
            sys.exit("Please fill out the config file.")

        self.arso = ARSO(
            self.temp_dir, dark_mode=self.config.get("dark_mode", True)
        )
        self._register_commands()

    async def setup_hook(self) -> None:
        self.scheduler = create_scheduler(self)
        self.scheduler.start()
        logger.info("cron tasks started")
        log_next_runs(self.scheduler)

    def _register_commands(self) -> None:
        @self.event
        async def on_message(message: discord.Message) -> None:
            if self.user and message.author.id == self.user.id:
                return

        @self.tree.command()
        @log_command
        async def vreme(interaction: discord.Interaction) -> None:
            """Izpiše napoved za današnji dan"""
            await interaction.response.defer()
            await interaction.followup.send(**self.generate_forecast_panel())

        @self.tree.command()
        @log_command
        async def obeti(interaction: discord.Interaction) -> None:
            """Izpiše obete"""
            await interaction.response.defer()
            await interaction.followup.send(**self.generate_obeti_panel())

        @self.tree.command()
        @log_command
        async def padavine(
            interaction: discord.Interaction,
            lokacija: str | None = None,
        ) -> None:
            """Izpiše padavine or something"""
            await interaction.response.defer()
            await interaction.followup.send(
                **self.generate_precipitation_panel(lokacija)
            )

        @self.tree.command()
        @log_command
        async def dnevno_vreme(interaction: discord.Interaction) -> None:
            """Doda trenutni kanal za dnevna sporočila"""
            await interaction.response.send_message(
                self.add_channel(interaction.channel_id)
            )

        @self.tree.command()
        @log_command
        async def nednevno_vreme(interaction: discord.Interaction) -> None:
            """Odstrani trenutni kanal za dnevna sporočila"""
            await interaction.response.send_message(
                self.remove_channel(interaction.channel_id)
            )

        @self.tree.command()
        @log_command
        async def version(interaction: discord.Interaction) -> None:
            """Prikaže trenutno verzijo bota"""
            assert self.user is not None
            uptime = datetime.now() - self.start_time
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)

            commit_str = ""
            if _GIT_COMMIT:
                short = _GIT_COMMIT[:7]
                commit_str = f" ([`{short}`]({_REPO}/commit/{_GIT_COMMIT}))"

            ts = int(self.start_time.timestamp())
            msg = (
                f"## [{self.user.name}]({_REPO})"
                f" v{_BOT_VERSION}{commit_str}\n"
                "Neuradni Discord bot za ARSO vremensko napoved"
                " *razvil [MysteriousWolf](https://github.com/MysteriousWolf)*\n"
                f"**Obratuje: **{hours}h {minutes}m {seconds}s"
                f" (od <t:{ts}:f>)"
            )
            await interaction.response.send_message(msg, suppress_embeds=True)

    def generate_forecast_panel(self, paragraphs=-1):
        fc = self.arso.get_forecast(paragraphs)

        tble = self.arso.get_morn_even_table()
        file = discord.File(tble, filename="morn_tabela.png")

        embed = discord.Embed(
            color=color_to_discord(self.cu.get_current_color()),
            title=fc["title"],
        )
        embed.add_field(
            name="Tekstovna napoved", value=fc["body"], inline=True
        )
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
        embed.add_field(
            name="Tekstovna napoved", value=fc["body"], inline=True
        )
        embed.set_footer(text="ARSO").timestamp = fc["timestamp"]
        embed.set_author(name=fc["author"], url=arso_module.HOME_URL)
        embed.set_thumbnail(url=arso_module.THUMBNAIL_URL)
        embed.set_image(url="attachment://napoved_tabela.png")

        return {"file": file, "embed": embed}

    def generate_precipitation_panel(self, lokacija: str | None = None):
        marker: tuple[float, float] | None = None
        trieste_fallback = False
        if lokacija is not None:
            coords = geocode_location(lokacija)
            if coords is not None and not within_slovenia(*coords):
                coords = TRIESTE
                trieste_fallback = True
            marker = coords
        gif = self.arso.get_percipitation_gif(marker, trieste_fallback)
        filename = datetime.now().strftime("%Y%m%d-%H%M-si0-rm-anim.gif")
        file = discord.File(gif, filename=filename)

        embed = discord.Embed(
            color=color_to_discord(self.cu.get_current_color()),
            title="Radarska slika padavin",
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
        count = f"[bot.count]{len(channels)}[/bot.count]"
        logger.info(f"{cron} starting, {count} channel(s)")
        t0 = time.monotonic()
        ok = fail = 0
        for ch in channels:
            chnl = self.get_channel(ch)
            if not isinstance(chnl, discord.abc.Messageable):
                logger.warning(
                    f"{cron} channel {fmt_id(ch)} not found or not messageable"
                )
                fail += 1
                continue
            try:
                await chnl.send(**panel_fn())
                ok += 1
            except Exception:
                logger.exception(f"{cron} channel {fmt_id(ch)} send failed")
                fail += 1
        elapsed = f"{time.monotonic() - t0:.2f}"
        if ok == 0:
            logger.error(
                f"{cron} {fmt_fail()} {fmt_timing(elapsed)}"
                f", [bot.fail]fail={fail}[/bot.fail]"
            )
        elif fail:
            logger.warning(
                f"{cron} {fmt_warn()} {fmt_timing(elapsed)}"
                f", [bot.ok]ok={ok}[/bot.ok] [bot.fail]fail={fail}[/bot.fail]"
            )
        else:
            logger.info(f"{cron} {fmt_ok()} {fmt_timing(elapsed)}")

    def _check_and_claim(self, job_id: str, hour: int) -> bool:
        now = datetime.now()
        slot = _last_scheduled_time(hour, now)
        last = self._last_fired.get(job_id)
        if last is not None and last >= slot:
            return False
        self._last_fired[job_id] = now
        return True

    async def _guarded_broadcast(
        self, job_id: str, config_key: str, panel_fn
    ) -> None:
        if not self._check_and_claim(job_id, int(self.config[config_key])):
            logger.debug(
                f"[bot.cron]cron.{job_id}[/bot.cron] slot already claimed"
            )
            return
        await self._broadcast(job_id, panel_fn)

    async def _catch_up_missed_sends(self) -> None:
        now = datetime.now()
        for job_id, hour, fn in (
            (
                "send_weather",
                int(self.config["polna_napoved_ob"]),
                self.send_weather,
            ),
            (
                "send_recap",
                int(self.config["povzetek_napovedi_ob"]),
                self.send_recap,
            ),
        ):
            slot = _last_scheduled_time(hour, now)
            last = self._last_fired.get(job_id)
            if slot < self.start_time:
                logger.debug(
                    f"[bot.cron]cron.{job_id}[/bot.cron] skipping catch-up"
                    f" (slot {slot.strftime('%H:%M')} predates startup"
                    f" {self.start_time.strftime('%H:%M')})"
                )
                continue
            if now >= slot and (last is None or last < slot):
                missed_at = slot.strftime("%H:%M")
                ago_s = int((now - slot).total_seconds())
                ago_m, ago_s = divmod(ago_s, 60)
                ago_str = (
                    f"{ago_m}m {ago_s}s ago" if ago_m else f"{ago_s}s ago"
                )
                reason = (
                    f"scheduled {missed_at}, missed — was offline"
                    if last is None
                    else f"scheduled {missed_at}, last sent at {last.strftime('%H:%M')}"
                )
                logger.info(
                    f"[bot.cron]cron.{job_id}[/bot.cron] catching up"
                    f" ({reason}, {ago_str})"
                )
                await fn()

    async def send_weather(self):
        await self._guarded_broadcast(
            "send_weather", "polna_napoved_ob", self.generate_forecast_panel
        )

    async def send_recap(self):
        await self._guarded_broadcast(
            "send_recap",
            "povzetek_napovedi_ob",
            lambda: self.generate_forecast_panel(paragraphs=1),
        )

    def dedup_channels(self):
        channels = self.config.get("channels") or []
        unique = set(channels)
        if len(unique) < len(channels):
            n = f"[bot.count]{len(channels) - len(unique)}[/bot.count]"
            logger.info(f"removed {n} duplicate channel(s) from config")
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
        total = f"[bot.count]{len(self.config['channels'])}[/bot.count]"
        logger.info(f"channel {fmt_id(channel_id)} added - {total} total")
        return "Avtomatsko pošiljanje prognoze omogočeno v tem kanalu"

    def remove_channel(self, channel_id):
        if channel_id not in self.config["channels"]:
            logger.info(f"channel {fmt_id(channel_id)} not subscribed")
            return (
                "Ta kanal še nima omogočenega avtomatskega pošiljanja prognoze"
            )
        self.config["channels"].remove(channel_id)
        self.store_config()
        remaining = f"[bot.count]{len(self.config['channels'])}[/bot.count]"
        logger.info(
            f"channel {fmt_id(channel_id)} removed - {remaining} remaining"
        )
        return "Avtomatsko pošiljanje prognoze odstranjeno"

    async def on_ready(self) -> None:
        assert self.user is not None
        if not self._connected_once:
            self.start_time = datetime.now()

        logger.info(
            f"logged on as {fmt_user_link(self.user.name, self.user.id)}"
        )

        for server in self.guilds:
            self.tree.copy_global_to(guild=server)
            await self.tree.sync(guild=server)

        cmds = self.tree.get_commands()
        if not self._connected_once:
            if self.guilds:
                guild_lines = "\n[dim]-[/dim] ".join(
                    fmt_guild_link(g.name, g.id) for g in self.guilds
                )
                logger.info(
                    f"present in ([bot.count]{len(self.guilds)}[/bot.count]):"
                    f"\n[dim]-[/dim] {guild_lines}"
                )
            else:
                logger.info("present in: none")
            cmd_lines = "\n[dim]-[/dim] ".join(
                f"{fmt_cmd(c.name)}: "
                + (
                    c.description
                    if isinstance(c, app_commands.Command)
                    else "(context menu)"
                )
                for c in cmds
            )
            logger.info(
                f"commands synced ([bot.count]{len(cmds)}[/bot.count]):"
                f"\n[dim]-[/dim] {cmd_lines}"
            )

        self._log_cron_channels()

        if self._connected_once:
            await self._catch_up_missed_sends()
        self._connected_once = True

    async def on_resumed(self) -> None:
        cmds = self.tree.get_commands()
        logger.info(
            f"session resumed — "
            f"[bot.count]{len(self.guilds)}[/bot.count] guild(s), "
            f"[bot.count]{len(cmds)}[/bot.count] command(s)"
        )
        await self._catch_up_missed_sends()

    def _log_cron_channels(self) -> None:
        channels = self.config["channels"]
        if not channels:
            logger.warning("cron has no channels configured")
            return
        ch_parts = []
        for ch_id in channels:
            ch = self.get_channel(ch_id)
            if isinstance(ch, discord.abc.GuildChannel):
                ch_parts.append(fmt_channel_link(ch.name, ch_id, ch.guild.id))
            else:
                ch_parts.append(fmt_id(ch_id))
        logger.info(f"cron registered for: {', '.join(ch_parts)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    _print_banner()
    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    _repo_root = Path(__file__).parent
    if (_repo_root / "pyproject.toml").exists():
        config_dir = _repo_root  # dev: keep config next to the repo
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        config_dir = xdg / "arso-sprach-zarathustra"
        config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"

    disc_intents = discord.Intents.default()
    disc_intents.message_content = True
    client = ARSOClient(intents=disc_intents, config_file=str(config_file))
    client.run(client.config["token"], log_handler=None)


if __name__ == "__main__":
    main()
