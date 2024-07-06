import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.messages = True

# 봇 토큰을 입력하세요
TOKEN = 'YOUR_BOT_TOKEN_HERE'

bot = commands.Bot(command_prefix='!', intents=intents)

# 청소할 채널의 ID 목록을 입력하세요
clean_channel_ids = [123456789012345678, 987654321098765432]  # 삭제하고 싶은 채널의 ID 목록 (정수형으로 입력)

# 제외할 단어 목록을 입력하세요
excluded_words = ['완료', '충족', '도달']

@bot.event
async def on_ready():
    print('봇이 준비되었습니다.')
    if not delete_old_messages.is_running():
        delete_old_messages.start()  # 주기적 작업 시작
        print('메시지 삭제 작업이 시작되었습니다.')

@tasks.loop(minutes=30, reconnect=True)
async def delete_old_messages():
    print('메시지 삭제 작업이 실행됩니다.')

    now = datetime.now(timezone.utc)
    thirty_minutes_ago = now - timedelta(minutes=30)  # 30분 전

    for channel_id in clean_channel_ids:
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f'채널을 찾을 수 없습니다: {channel_id}')
            continue

        deleted_message_count = 0  

        async for message in channel.history(limit=None, before=thirty_minutes_ago):
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
        print(f'{channel_id} 채널에서 {deleted_message_count}개의 메시지가 삭제되었습니다.')

bot.run(TOKEN)
