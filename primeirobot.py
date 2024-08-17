import discord
from discord.ext import commands
import datetime
import os

from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TOKEN')
LOG_CHANNEL = os.getenv('LOG_CHANNEL_ID')

intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

user_times = {}
user_durations = {}
paused_users = {}

async def get_log_channel(guild):
    return guild.get_channel(LOG_CHANNEL)

@bot.event
async def on_voice_state_update(member, before, after):
    log_channel = await get_log_channel(member.guild)
    if log_channel is None:
        print(f'Canal de logs não encontrado no servidor {member.guild.name}')
        return

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    username = str(member)

    if before.channel is None and after.channel is not None:
        if member.id in paused_users:
            paused_time = paused_users.pop(member.id)
            paused_duration = datetime.datetime.now() - paused_time
            user_durations[member.id] += paused_duration
            user_times[member.id] = datetime.datetime.now()
            embed = discord.Embed(
                title="Usuário Retomou",
                description=f'{member.mention} retomou no canal {after.channel}',
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Horário", value=user_times[member.id].strftime("%H:%M:%S %d-%m-%Y"))
            embed.set_thumbnail(url=avatar_url)
            await log_channel.send(embed=embed)
        else:
            user_times[member.id] = datetime.datetime.now()
            user_durations[member.id] = datetime.timedelta()
            embed = discord.Embed(
                title="Usuário Entrou",
                description=f'{member.mention} entrou no canal {after.channel}',
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Horário", value=user_times[member.id].strftime("%H:%M:%S %d-%m-%Y"))
            embed.set_thumbnail(url=avatar_url)
            await log_channel.send(embed=embed)

    elif before.channel is not None and after.channel is None:
        if member.id in user_times:
            if member.id in paused_users:
                paused_users.pop(member.id)
            join_time = user_times.pop(member.id)
            leave_time = datetime.datetime.now()
            duration = leave_time - join_time
            if member.id in user_durations:
                user_durations[member.id] += duration
            else:
                user_durations[member.id] = duration
            minutes, seconds = divmod(user_durations[member.id].total_seconds(), 60)
            embed = discord.Embed(
                title="Usuário Saiu",
                description=f'{member.mention} saiu do canal {before.channel}',
                color=discord.Color.red(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Tempo de Permanência", value=f'{int(minutes)} minutos e {int(seconds)} segundos')
            embed.set_thumbnail(url=avatar_url)
            await log_channel.send(embed=embed)

bot.run(TOKEN)
