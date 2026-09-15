import asyncio
import os

import discord
from discord.ext import commands

from cogfiles.copypastas import Copypastas
from cogfiles.alerts import EventAlerts
from cogfiles.streampause import StreamPause
from cogfiles.reminders import Reminders
from cogfiles.announcements import Announcements
from cogfiles.music import Music
from cogfiles.web_scrapers import WebScrapers
from cogfiles.polling import Polling
from cogfiles.birthdays import Birthdays
from cogfiles.image_editing import ImageEditing
from cogfiles.admin import Admin
from cogfiles.reaction_roles import ReactionRoles
from cogfiles.triple_triad import TripleTriad

def main():
    token = os.getenv("TOKEN")
    stream_name = os.getenv("CURRENT_STREAM_NAME")
    command_prefix = os.getenv("PREFIX", default="!")
    
    activity = discord.Game(name=stream_name)
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix=command_prefix, activity=activity, intents=intents, enable_debug_events=True)

    cogs = Copypastas(bot), EventAlerts(bot), StreamPause(bot), Reminders(bot), Announcements(bot), \
        Music(bot), WebScrapers(bot), Polling(bot), Birthdays(bot), ImageEditing(bot), Admin(bot), \
        ReactionRoles(bot), TripleTriad(bot)
    for cog in cogs:
        asyncio.run(bot.add_cog(cog))

    bot.run(token)

if __name__ == "__main__":
    main()