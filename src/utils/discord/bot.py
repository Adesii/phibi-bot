"""
Discord Bot Main Class to interface with Discord
"""

import time
import datetime
import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.observer import ObserverClient
from utils.logging import create_sys_logger
from .commands import add_commands
from .commands.sink import BufferSink

logger = create_sys_logger(id="discord")


class DiscordBot(discord.Client):

    def __init__(self, jaison):
        logger.debug("Activating with all intents...")
        super().__init__(intents=discord.Intents.all())
        self.jaison = jaison
        logger.debug("Reloading command tree...")
        self.tree, self.tree_params = add_commands(
            self, self.jaison.config.discord_server_id
        )

        # For managing response behavior
        self.scheduler = AsyncIOScheduler()
        # self.scheduler.start()
        self.message_waiter = None
        self.vc = None
        self.app_listener = self.JAIsonListener(jaison.broadcast_server, self)
        self.main_user = ""
        self.main_content = ""

    # Handler for bot activation
    async def on_ready(self):
        await self.tree.sync(**self.tree_params)  # re-sync commands once bot is online
        logger.debug(f"Command tree resynced with params: {self.tree_params}")
        logger.info("Discord Bot is ready!")

    # Handler for any new messages
    async def on_message(self, message):
        logger.debug(
            f"Received new message from {message.author.display_name} in #{message.channel.name}"
        )
        # Skip messages from self
        if self.application_id == message.author.id:
            return
        # logger.debug(
        #    f"Received new message from {message.author.display_name} in #{message.channel.name}"
        # )
        if message.channel.name != "containment-chamber":
            if not (
                "<@1331985503423041538>" in message.content
                and message.channel.name == "main-hall"
            ):
                return

        logger.debug(f"Responding to message...")

        # Generate response
        self.main_user = message.author.display_name or message.author.global_name
        self.main_content = message.content
        logger.debug(f"Message by user {self.main_user}: {self.main_content}")
        logger.debug("Caching and waiting...")

        tim = datetime.datetime.now() + datetime.timedelta(seconds=2)
        # print(f"Tim is set to {tim} and current time is:{datetime.datetime.now()}")

        # Send (default if None) message
        self.message_waiter = self.scheduler.add_job(
            self.send_message,
            trigger="date",
            run_date=tim,
            args=[message.channel],
            kwargs={"gen_message": True},
            id="message_wait_response",
            replace_existing=True,
        )
        if not self.scheduler.running:
            self.scheduler.start()
        # self.message_wait_scheduler.wakeup()
        # self.message_wait_scheduler.print_jobs()
        # self.message_wait_scheduler.resume()
        # self.message_waiter.resume()
        # logger.debug(f"Scheduler is {self.message_wait_scheduler.running}")
        ## self.message_wait_scheduler.add
        # await self.send_message(message.channel, None, gen_message=True)
        # logger.debug("Sent message")

    async def send_message(
        self,
        channel: discord.abc.GuildChannel,
        message: str = None,
        gen_message: bool = False,
    ):
        logger.debug(f"Sending message to {channel.name}...")
        if gen_message:
            logger.debug(f"Generating message...")
            await channel.typing()
            logger.debug(f"Generating response...")
            message, _ = self.jaison.get_response_from_text(
                self.main_user,
                self.main_content,
                include_audio=False,
                include_animation=False,
            )

        responses = (
            [msg for msg in message.split("\\n") if len(msg) > 0]
            if message
            else ["..."]
        )
        for response in responses:
            await channel.send(response)

    async def voice_cb(self, sink: BufferSink):
        logger.debug("Running Discord bot's voice callback...")
        global stt
        for user in sink.buf:
            try:
                idx = sink.save_user_to_file(
                    user, self.jaison.config.RESULT_INPUT_SPEECH
                )
            except Exception as err:
                logger.error(
                    f"Failed to save input audio from buffer into {self.jaison.config.RESULT_INPUT_SPEECH}: {err}"
                )
                return

            logger.debug(f"Getting response from input audio...")
            text_result, audio_result = self.jaison.get_response_from_audio(
                user,
                self.jaison.config.RESULT_INPUT_SPEECH,
                time=sink.get_user_time(user),
                include_audio=True,
                include_animation=True,
            )
            logger.debug(f"Got response: {text_result}")

            # Finish before playing audio if no response was generated
            if text_result is None:
                logger.debug(f"Chose to continue listening...")
                return

            # Freshen sink since speech data was committed to history by T2T model on successful response generation
            logger.debug(f"Clearing input audio that has been responded to...")
            sink.freshen(user, idx=idx)

            # Attempt to play audio to channel
            try:
                if audio_result and not self.jaison.response_cancelled:
                    logger.debug(
                        f"Playing audio {audio_result} to Discord channel: {self.vc}"
                    )
                    source = discord.FFmpegPCMAudio(audio_result)
                    self.vc.play(source)
            except Exception as err:
                logger.error(f"Failed to play sound in Discord channel: {err}")

    class JAIsonListener(ObserverClient):
        def __init__(self, server, outer):
            super().__init__(server=server)
            self.outer = outer

        def handle_event(self, event_id: str, payload) -> None:
            print("STOPPING RESPONSE PLAYING")
            if event_id == "request_stop_response":
                if self.outer.vc and self.outer.vc.is_playing():
                    self.outer.vc.pause()
