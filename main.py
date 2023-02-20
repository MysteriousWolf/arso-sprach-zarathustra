import sys
import tempfile
import time
from datetime import datetime

import discord
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import client, app_commands

from arso import ARSO
from utils.ColorUtils import ColorUtils, color_to_discord

arso_color = discord.Color.from_rgb(0, 130, 188)
arso_neon = discord.Color.from_rgb(0, 176, 255)
embed_color = arso_color


class ARSOClient(discord.Client):
    config = None
    config_file = None

    def __init__(self, *, intents: discord.Intents, config_file="config.yaml"):
        super().__init__(intents=intents)
        self.config_file = config_file
        self.temp_dir = tempfile.gettempdir()
        self.tree = app_commands.CommandTree(self)
        self.arso = ARSO(self.temp_dir, 'https://meteo.arso.gov.si/uploads/probase/www/fproduct/text/sl')
        self.cu = ColorUtils()

        try:
            print(f"Reading the config file. ({config_file})")
            with open(config_file, "r+") as stream:
                try:
                    self.config = yaml.safe_load(stream)
                except yaml.YAMLError as exc:
                    print(f"An error occurred when trying to parse the config file: {exc}")
        except FileNotFoundError:
            print(f"Config not found, creating a config template. Please fill in the missing values.")
            self.config = {"token": "[insert your Discord bot token here]", "channels": [], "polna_napoved_ob": "18",
                           "povzetek_napovedi_ob": "6"}
            self.store_config()
            sys.exit("Please fill out the config file.")

    async def setup_hook(self):
        """print(self.guilds)
        for server in self.guilds:
            self.tree.copy_global_to(guild=server)
            await self.tree.sync(guild=server)"""
        pass

    def generate_forecast_panel(self):
        fc = self.arso.get_forecast()

        tble = self.arso.get_morn_even_table()
        file = discord.File(tble, filename="morn_tabela.png")

        embed = discord.Embed(color=color_to_discord(self.cu.get_current_color()), title=fc["title"])
        embed.add_field(name='Tekstovna napoved', value=fc["body"], inline=True)
        embed.set_footer(text='ARSO').timestamp = fc["timestamp"]
        embed.set_author(name=fc["author"], url="https://meteo.arso.gov.si/")
        embed.set_thumbnail(url="https://pbs.twimg.com/profile_images/798099496139915264/cSjEl4nm_400x400.jpg")
        embed.set_image(url="attachment://morn_tabela.png")

        return {
            "file": file,
            "embed": embed
        }

    def generate_obeti_panel(self):
        fc = self.arso.get_obeti()

        tble = self.arso.get_3day_table()
        file = discord.File(tble, filename="napoved_tabela.png")

        embed = discord.Embed(color=embed_color, title=fc["title"])
        embed.add_field(name='Tekstovna napoved', value=fc["body"], inline=True)
        embed.set_footer(text='ARSO').timestamp = fc["timestamp"]
        embed.set_author(name=fc["author"], url="https://meteo.arso.gov.si/")
        embed.set_thumbnail(url="https://pbs.twimg.com/profile_images/798099496139915264/cSjEl4nm_400x400.jpg")
        embed.set_image(url="attachment://napoved_tabela.png")

        return {
            "file": file,
            "embed": embed
        }

    def generate_precipitation_panel(self):
        embed = discord.Embed(color=color_to_discord(self.cu.get_current_color()), title="Radarska slika padavin")
        embed.set_footer(text='ARSO').timestamp = datetime.now()
        embed.set_author(name="Vir: Agencija Republike Slovenije za okolje",
                         url="https://meteo.arso.gov.si/met/sl/weather/observ/radar/")
        embed.set_thumbnail(url="https://pbs.twimg.com/profile_images/798099496139915264/cSjEl4nm_400x400.jpg")
        embed.set_image(
            url=f"https://meteo.arso.gov.si/uploads/probase/www/observ/radar/si0-rm-anim.gif?time={time.time()}")

        return {
            "embed": embed
        }

    async def send_recap(self):
        print("Sending the daily recap!")
        self.generate_forecast_panel()
        for ch in self.config["channels"]:
            chnl = self.get_channel(ch)
            await chnl.send(**client.generate_forecast_panel())

    def store_config(self):
        with open(self.config_file, "w+") as stream:
            try:
                yaml.safe_dump(self.config, stream)
            except yaml.YAMLError as exc:
                print(f"An error occurred when trying to create a fresh config file: {exc}")

    def add_channel(self, channel_id):
        self.config["channels"].append(channel_id)
        self.store_config()
        return "Avtomatsko pošiljanje posodobitev omogočeno v tem kanalu."

    def remove_channel(self, channel_id):
        self.config["channels"].remove(channel_id)
        self.store_config()
        return "Avtomatsko pošiljanje posodobitev odstranjeno."


if __name__ == '__main__':
    disc_intents = discord.Intents.default()
    disc_intents.message_content = True
    client = ARSOClient(intents=disc_intents)

    scheduler = AsyncIOScheduler()


    @client.event
    async def on_ready():
        print(f'Logged on as {client.user}!')

        for server in client.guilds:
            client.tree.copy_global_to(guild=server)
            await client.tree.sync(guild=server)

        print(f'Synced new commands')

        # test pošiljanja v kanal
        # scheduler.add_job(client.send_recap, 'interval', seconds=5)

        # polna napoved
        scheduler.add_job(client.send_recap, 'cron', hour=client.config["polna_napoved_ob"])

        # kratka napoved - zaenkrat isto
        scheduler.add_job(client.send_recap, 'cron', hour=client.config["povzetek_napovedi_ob"])
        scheduler.start()

        print(f'Started cron tasks')


    @client.event
    async def on_message(message):
        if message.author.id == client.user.id:
            return
        # await client.send_recap()
        # print(f'Message from {message.author}: {message.content}')


    @client.tree.command()
    async def vreme(interaction: discord.Interaction):
        """Izpiše napoved za današnji dan"""
        await interaction.response.send_message(**client.generate_forecast_panel())


    @client.tree.command()
    async def obeti(interaction: discord.Interaction):
        """Izpiše obeti"""
        await interaction.response.send_message(**client.generate_obeti_panel())


    @client.tree.command()
    async def padavine(interaction: discord.Interaction):
        """Izpiše padavine or something"""
        await interaction.response.send_message(**client.generate_precipitation_panel())


    @client.tree.command()
    async def dnevno_vreme(interaction: discord.Interaction):
        """Doda trenutni kanal za dnevna sporočila"""
        await interaction.response.send_message(client.add_channel(interaction.channel_id))


    @client.tree.command()
    async def nednevno_vreme(interaction: discord.Interaction):
        """Odstrani trenutni kanal za dnevna sporočila"""
        await interaction.response.send_message(client.remove_channel(interaction.channel_id))


    client.run(client.config["token"])
