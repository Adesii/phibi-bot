import os
from dotenv import load_dotenv

load_dotenv()
from utils.args import args
from utils.phibi import Phibi
from utils.discord import DiscordBot
from webui import start_ui
from threading import Thread

phibi_main = Phibi(init_config_file=args.config)

# For Discord Bot #TODO: Uncomment this once we want to use Discord Bot
discord_bot = DiscordBot(phibi_main)
discord_thread = Thread(target=discord_bot.run, args=[os.getenv("DISCORD_BOT_TOKEN")])
discord_thread.start()

# For Web UI
web_thread = Thread(target=start_ui, args=[phibi_main])
web_thread.start()

# Keep running this main thread while others threads are active
discord_thread.join()  # TODO: Uncomment this once we want to use Discord Bot
web_thread.join()
