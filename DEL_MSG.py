import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
import sys

intents = discord.Intents.default()
intents.messages = True

# 봇 토큰을 입력하세요
TOKEN = '생성한 봇의 토큰 아이디'

bot = commands.Bot(command_prefix='!', intents=intents)

# 청소할 채널의 ID를 입력하세요
clean_channel_id = 삭제하고싶은 채널의 ID

@bot.event
async def on_ready():
    print('봇이 준비되었습니다.')
    delete_old_messages.start()

@tasks.loop(hours=24)  # 24시간마다 실행
async def delete_old_messages():
    print('오래된 메시지 삭제 작업을 시작합니다.')

    channel = bot.get_channel(clean_channel_id)

    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)

    deleted_message_count = 0  

    async for message in channel.history(limit=None, before=one_day_ago):
        time_difference = now - message.created_at

        # 1일(86400초)이 지난 메시지인 경우 삭제합니다.
        if time_difference.total_seconds() >= 86400:
            await message.delete()
            deleted_message_count += 1  
            print(f'{message.author.display_name} 님의 메시지를 삭제했습니다.')

            # 메시지 삭제 후 1초 대기하여 rate limit 회피
            await asyncio.sleep(1)

    await channel.send(f'{deleted_message_count}개의 메시지를 삭제했습니다.')

@delete_old_messages.before_loop
async def before_delete_old_messages():
    await bot.wait_until_ready()

bot.run(TOKEN)
