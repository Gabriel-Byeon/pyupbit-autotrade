import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import asyncio

intents = discord.Intents.default()
intents.messages = True

# 봇 토큰을 입력하세요
TOKEN = '생성한 봇의 토큰 아이디'

bot = commands.Bot(command_prefix='!', intents=intents)

# 청소할 채널의 ID를 입력하세요
clean_channel_id = 삭제하고싶은_채널의_ID

# 제외할 단어 목록을 입력하세요
excluded_words = ['완료']

@bot.event
async def on_ready():
    print('봇이 준비되었습니다.')

    channel = bot.get_channel(clean_channel_id)

    now = datetime.now(timezone.utc)

    two_weeks_ago = now - timedelta(days=14)

    deleted_message_count = 0  

    async for message in channel.history(limit=None, after=two_weeks_ago):

        time_difference = now - message.created_at

        # 특정 단어를 포함한 메시지인지 확인합니다.
        if any(word in message.content for word in excluded_words):
            continue

        # 10초가 지난 메시지인 경우 삭제합니다.
        if time_difference.total_seconds() >= 10:
            await message.delete()
            deleted_message_count += 1  
            print(f'{message.author.display_name} 님의 메시지를 삭제했습니다.')

    await channel.send(f'{deleted_message_count}개의 메시지를 삭제했습니다.')

    # 봇을 종료하지 않고 계속 실행되도록 합니다.
    # await bot.close()
    # await asyncio.sleep(1)
    # await bot.loop.shutdown_asyncgens()
    # bot.loop.stop()
    # sys.exit()

bot.run(TOKEN)
