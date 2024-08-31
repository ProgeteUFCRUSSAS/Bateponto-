import discord
from discord.ext import commands
import os
import asyncpg
import logging
import datetime
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv('TOKEN')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

user_times = {}
paused_users = {}
LOG_CHANNEL_NAME = "logs"  # Nome do canal de logs
HISTORY_CHANNEL_NAME = "historico-pontos"  # Nome do canal de histórico de pontos

async def create_tables(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_times (
            user_id BIGINT,
            username VARCHAR(255),
            join_date DATE,
            last_join_time TIME,
            leave_date DATE,
            last_leave_time TIME,
            total_duration INTERVAL DEFAULT '00:00:00'
        );
    """)
    logger.info("Tabela user_times criada com sucesso")

async def connect_to_db():
    try:
        bot.pg_con = await asyncpg.connect(
            user='usuario',
            password='senha',
            database='bot_banco',
            host='localhost'
        )
        await create_tables(bot.pg_con)
        return bot.pg_con
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    await connect_to_db()  # Cria a conexão com o banco de dados ao iniciar o bot
    print('Conectado ao banco de dados PostgreSQL')

async def get_log_channel(guild):
    # Tenta encontrar o canal de logs
    log_channel = discord.utils.get(guild.channels, name=LOG_CHANNEL_NAME)
    if log_channel is None:
        # Cria o canal de logs se não existir
        log_channel = await guild.create_text_channel(LOG_CHANNEL_NAME)
    return log_channel

async def get_history_channel(guild):
    # Tenta encontrar o canal de histórico de pontos
    history_channel = discord.utils.get(guild.channels, name=HISTORY_CHANNEL_NAME)
    if history_channel is None:
        # Cria o canal de histórico de pontos se não existir
        history_channel = await guild.create_text_channel(HISTORY_CHANNEL_NAME)
    return history_channel

@bot.event
async def on_voice_state_update(member, before, after):
    log_channel = await get_log_channel(member.guild)
    if log_channel is None:
        print(f'Canal de logs não encontrado no servidor {member.guild.name}')
        return

    username = str(member)
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url

    if before.channel is None and after.channel is not None:
        join_time = datetime.datetime.now().replace(microsecond=0)
        if member.id in paused_users:
            paused_time = paused_users.pop(member.id)
            paused_duration = join_time - paused_time
            await update_user_duration(member.id, paused_duration, join_time)
            user_times[member.id] = join_time
            embed = discord.Embed(
                title="Usuário Retomou",
                description=f'{member.mention} retomou no canal {after.channel}',
                color=discord.Color.green(),
                timestamp=join_time
            )
            embed.add_field(name="Horário", value=join_time.strftime("%H:%M:%S %d-%m-%Y"))
            embed.set_thumbnail(url=avatar_url)
            await log_channel.send(embed=embed)
        else:
            user_times[member.id] = join_time
            await insert_new_user(member.id, username, join_time)
            embed = discord.Embed(
                title="Usuário Entrou",
                description=f'{member.mention} entrou no canal {after.channel}',
                color=discord.Color.blue(),
                timestamp=join_time
            )
            embed.add_field(name="Horário", value=join_time.strftime("%H:%M:%S %d-%m-%Y"))
            embed.set_thumbnail(url=avatar_url)
            await log_channel.send(embed=embed)

    elif before.channel is not None and after.channel is None:
        if member.id in user_times:
            if member.id in paused_users:
                paused_users.pop(member.id)
            join_time = user_times.pop(member.id).replace(microsecond=0)
            leave_time = datetime.datetime.now().replace(microsecond=0)
            duration = leave_time - join_time
            await update_user_duration(member.id, duration, leave_time)
            total_duration = await get_user_duration(member.id)
            total_duration = total_duration - datetime.timedelta(microseconds=total_duration.microseconds)  # Remove milissegundos
            minutes, seconds = divmod(total_duration.total_seconds(), 60)
            embed = discord.Embed(
                title="Usuário Saiu",
                description=f'{member.mention} saiu do canal {before.channel}',
                color=discord.Color.red(),
                timestamp=leave_time
            )
            embed.add_field(name="Tempo de Permanência", value=f'{int(minutes)} minutos e {int(seconds)} segundos')
            embed.add_field(name="Horário de Entrada", value=join_time.strftime("%H:%M:%S %d-%m-%Y"))
            embed.add_field(name="Horário de Saída", value=leave_time.strftime("%H:%M:%S %d-%m-%Y"))
            embed.set_thumbnail(url=avatar_url)
            await log_channel.send(embed=embed)

async def insert_new_user(user_id, username, join_time):
    join_time_only = join_time.time()  # Extrai apenas o horário
    join_date = join_time.date()

    # Verifique se já existe um registro para este usuário no dia atual
    existing_record = await bot.pg_con.fetchrow("""
        SELECT user_id FROM user_times WHERE user_id = $1 AND join_date = $2
    """, user_id, join_date)

    if existing_record:
        # Se já existe um registro, apenas atualize o horário de entrada
        await bot.pg_con.execute("""
            UPDATE user_times
            SET last_join_time = $1
            WHERE user_id = $2 AND join_date = $3
        """, join_time_only, user_id, join_date)
    else:
        # Se não existe, insira um novo registro
        await bot.pg_con.execute("""
            INSERT INTO user_times (user_id, username, join_date, last_join_time, total_duration)
            VALUES ($1, $2, $3, $4, $5)
        """, user_id, username, join_date, join_time_only, datetime.timedelta())

async def update_user_duration(user_id, duration, leave_time):
    leave_time_only = leave_time.time()  # Extrai apenas o horário
    leave_date = leave_time.date()

    # Atualize o registro existente no dia atual
    await bot.pg_con.execute("""
        UPDATE user_times
        SET total_duration = total_duration + $1, last_leave_time = $2, leave_date = $3
        WHERE user_id = $4 AND join_date = $5
    """, duration, leave_time_only, leave_date, user_id, leave_date)


async def get_user_duration(user_id):
    # Recupera a duração total do tempo de permanência do usuário no banco de dados
    row = await bot.pg_con.fetchrow("SELECT total_duration FROM user_times WHERE user_id = $1", user_id)
    return row['total_duration'] if row else datetime.timedelta()

async def get_user_history(user_id, start_date=None, end_date=None):
    # Recupera o histórico de um usuário no banco de dados com filtro opcional por data
    query = """
        SELECT join_date, last_join_time, leave_date, last_leave_time, total_duration
        FROM user_times
        WHERE user_id = $1
    """
    if start_date and end_date:
        query += " AND join_date BETWEEN $2 AND $3"
        rows = await bot.pg_con.fetch(query, user_id, start_date, end_date)
    else:
        rows = await bot.pg_con.fetch(query, user_id)
    
    return rows

@bot.command(name='historico')
async def historico(ctx, periodo: str, member: discord.Member = None):
    if member is None:
        member = ctx.author  # Se nenhum membro for especificado, usa o autor do comando

    today = datetime.date.today()
    
    if periodo.lower() == 'semanal':
        start_date = today - datetime.timedelta(days=today.weekday())  # Início da semana (segunda-feira)
        end_date = start_date + datetime.timedelta(days=6)  # Fim da semana (domingo)
    elif periodo.lower() == 'mensal':
        start_date = today.replace(day=1)  # Primeiro dia do mês
        end_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)  # Último dia do mês
    else:
        await ctx.send(f"Período inválido. Use 'semanal' ou 'mensal'.")
        return

    user_history = await get_user_history(member.id, start_date, end_date)

    if not user_history:
        await ctx.send(f'Nenhum histórico encontrado para {member.mention} no período especificado.')
        return

    embed = discord.Embed(
        title=f'Histórico de Atividades de {member.display_name} ({periodo.capitalize()})',
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

    for record in user_history:
        join_date = record['join_date'].strftime("%d-%m-%Y") if record['join_date'] else "N/A"
        join_time = record['last_join_time'].strftime("%H:%M:%S") if record['last_join_time'] else "N/A"
        leave_date = record['leave_date'].strftime("%d-%m-%Y") if record['leave_date'] else "N/A"
        leave_time = record['last_leave_time'].strftime("%H:%M:%S") if record['last_leave_time'] else "N/A"
        total_duration = str(record['total_duration']) if record['total_duration'] else "00:00:00"

        # Organiza as informações em um campo único, com separadores visuais
        field_value = (
            f"**📅 Data de Entrada:** {join_date}\n"
            f"**⏰ Horário de Entrada:** {join_time}\n"
            f"**📅 Data de Saída:** {leave_date}\n"
            f"**⏰ Horário de Saída:** {leave_time}\n"
            f"**⏳ Duração:** {total_duration}\n"
            "────────────"
        )

        embed.add_field(
            name=f'Atividade em {join_date}',
            value=field_value,
            inline=False
        )

    history_channel = await get_history_channel(ctx.guild)  # Obtém o canal de histórico de pontos
    await history_channel.send(embed=embed)  # Envia o histórico para o canal de histórico de pontos

bot.run(TOKEN)