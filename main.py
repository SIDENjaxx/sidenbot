import asyncio
import random
import os
import heapq
import sys
from datetime import datetime, timezone, timedelta
import traceback
import aiohttp
import xml.etree.ElementTree as ET
import requests
from discord.ext import commands,tasks
import discord
from collections import defaultdict
import matplotlib.pyplot as plt
from googletrans import Translator, LANGUAGES
from cachetools import TTLCache
from gtts import gTTS
from pydub import AudioSegment
from operator import itemgetter
from bs4 import BeautifulSoup
import json
from discord import Embed
import qrcode
from PIL import Image
from io import BytesIO
from googleapiclient.discovery import build
import dotenv
from server import server_thread


bot = commands.Bot(command_prefix = ("!"), intents=discord.Intents.all())
bot.remove_command("help")
ID_ROLE_MEMBER = 1141974521142849557
feedback_data = {}  # フィードバックデータを保存するための辞書
translator = Translator()


# 運営ロールをチェックするカスタムチェック関数
def is_admin(ctx):
    # もしメッセージを送信したメンバーが運営ロールを持っている場合はTrueを返します
    return any(role.name == 'staff' for role in ctx.author.roles)


@bot.hybrid_command(name="poll")
@commands.check(is_admin)
async def poll(ctx, question, year: int, month: int, day: int, hours: int, minutes: int, option1, option2, option3=None, option4=None, option5=None, option6=None, option7=None, option8=None, option9=None, option10=None):
    """指定した時間まで投票を行うコマンド(運営のみ)"""
    options = [option1, option2, option3, option4, option5, option6, option7, option8, option9, option10]
    options = [x for x in options if x is not None]
    if len(options) < 2:
        await ctx.send("オプションは2つ以上必要です。")
        return
    if len(options) > 10:
        await ctx.send("オプションは10個までしかサポートされていません。")
        return

    # 指定した日時をdatetimeオブジェクトに変換
    timeout_datetime = datetime(year, month, day, hours, minutes)

    # 現在日時を取得
    current_datetime = datetime.now()

    # タイムアウトまでの秒数を計算
    timeout_seconds = (timeout_datetime - current_datetime).total_seconds()

    reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

    # 投票オプションとリアクションを対応付ける辞書を作成
    poll_options = {reactions[i]: option for i, option in enumerate(options) if i < len(reactions)}

    embed = discord.Embed(title="投票", description=question, color=0x00ff00)
    for reaction, option in poll_options.items():
        embed.add_field(name=f"{reaction} {option}", value="\u200b", inline=True)

    message = await ctx.send(embed=embed)

    for reaction in poll_options.keys():
        await message.add_reaction(reaction)

    # 投票結果の集計
    poll_results = defaultdict(int)
    voted_users = set()  # すでに投票したユーザーをトラッキングするセット

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in poll_options.keys() and user.id not in voted_users

    while True:
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=timeout_seconds, check=check)
        except asyncio.TimeoutError:
            break
        else:
            selected_option = poll_options[str(reaction.emoji)]
            poll_results[selected_option] += 1
            voted_users.add(user.id)

        # リアルタイムでの投票結果表示
        result_embed = discord.Embed(title="投票進行中", description=question, color=0x00ff00)
        for reaction, option in poll_options.items():
            result_embed.add_field(name=f"{reaction} {option}", value=f"票数: {poll_results[option]}", inline=True)
        await message.edit(embed=result_embed)

    # 最終的な投票結果とグラフ表示
    plt.rcParams['font.family'] = 'Yu Gothic'  # 日本語をサポートしたフォントに設定
    plt.bar(poll_results.keys(), poll_results.values())
    plt.xlabel('選択肢')
    plt.ylabel('得票数', rotation=0)
    plt.title('投票結果')
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig('poll_results.png')

    # Embedメッセージに画像と投票結果を挿入
    result_embed = discord.Embed(title="投票結果", description="投票が終了しました。", color=0x00ff00)
    result_embed.set_image(url="attachment://poll_results.png")  # 画像を添付

    # 投票結果をフィールドとして追加
    result_description = ""
    for option, count in poll_results.items():
        result_description += f"{option}: {count}票\n"
    result_embed.add_field(name="投票結果", value=result_description, inline=True)

    await ctx.send(embed=result_embed, file=discord.File('poll_results.png'))

    # グラフ画像の削除
    plt.close()
    os.remove('poll_results.png')

# もし運営ロールを持っていないメンバーがコマンドを実行した場合にメッセージを送信
@poll.error
async def poll_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("このコマンドを実行する権限がありません。運営ロールが必要です。")


@bot.hybrid_command(name="embed")
async def embed(ctx, title: str, description: str, color: discord.Color = discord.Color.blue(), author_name: str = None, author_icon_url: str = None, footer_text: str = None):
    """embedメッセージを作成するコマンド"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon_url)
    if footer_text:
        embed.set_footer(text=footer_text)

    await ctx.send(embed=embed)


@bot.hybrid_command(name="feedback")
async def feedback(ctx, *, message):
    """フィードバックを送信するコマンド"""
    # DMチャンネル以外では送信不可
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("このコマンドはDMでのみ利用可能です。")
        return

    # フィードバックを受け付けるチャンネルIDを指定
    feedback_channel_id = 1195276017087033366

    # フィードバックを送信するチャンネルを取得
    feedback_channel = bot.get_channel(feedback_channel_id)

    if feedback_channel:
        # Embedを作成してフィードバックを送信する
        embed = discord.Embed(
            title="フィードバック",
            description=message,
            color=0x3498db  # Embedの色を指定 (ここでは青)
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
        embed.set_footer(text=f"{ctx.author.display_name}からの意見", icon_url=ctx.author.display_avatar)
        # フィードバックデータにメッセージIDと送信者を保存
        feedback_id = ctx.message.id
        feedback_data[feedback_id] = {
            "author_id": ctx.author.id,
            "channel_id": ctx.channel.id
        }
        # EmbedにフィードバックIDを表示
        embed.add_field(name="フィードバックID", value=feedback_id, inline=True)

        # フィードバックを送信
        feedback_msg = await feedback_channel.send(embed=embed)
        await ctx.send("フィードバックが送信されました。ありがとうございます！")

        # フィードバックメッセージにリアクションをつける（返信用）
        await feedback_msg.add_reaction("📬")
    else:
        await ctx.send("フィードバックの送信先が見つかりませんでした。")

@bot.hybrid_command(name="reply")
@commands.check(is_admin)
async def reply(ctx, feedback_id, *, response):
    """フィードバックに対する返信が出来るコマンド (運営のみ)"""
    # フィードバックデータから送信者とチャンネルを取得
    feedback_info = feedback_data.get(int(feedback_id))
    if feedback_info:
        # フィードバックを送信したユーザーにメッセージを送信
        user = await bot.fetch_user(feedback_info["author_id"])
        try:
            channel = await user.create_dm()
        except discord.Forbidden:
            await ctx.send("ユーザーにDMを送信する権限がありません。")
            return

        # Embedを作成して返信を送信
        embed = discord.Embed(
            title="あなたのフィードバックへの返信",
            description=response,
            color=0x00ff00  # Embedの色を指定 (ここでは緑)
        )
        embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar)
        await channel.send(embed=embed)
        await ctx.send("返信が送信されました。")
    else:
        await ctx.send("指定されたフィードバックが見つかりませんでした。")

@reply.error
async def reply_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("このコマンドを実行する権限がありません。運営ロールが必要です。")


@bot.hybrid_command(name="weather")
async def advanced_weather(ctx, prefectures):
    """指定した都道府県の天気予報を表示するコマンド"""
    try:
        api_key = "9cd00891a519224dfe93779c47eb89ad"
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {"q": prefectures, "appid": api_key, "units": "metric"}

        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params, timeout=10) as response:
                data = await response.json()

        if data["cod"] == "404":
            message = f'都市 "{prefectures}" が見つかりませんでした。'
        else:
            temperature = data["main"]["temp"]
            min_temperature = data["main"]["temp_min"]
            max_temperature = data["main"]["temp_max"]
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]
            detailed_weather = data["weather"][0]["description"]
            pressure = data["main"]["pressure"]
            visibility = data["visibility"]

            embed = discord.Embed(
                title=f"{prefectures}の現在の天気",
                description=f"詳細な天気: {detailed_weather}",
                color=0x3498db
            )
            embed.add_field(name="気温", value=f"{temperature}℃", inline=True)
            embed.add_field(name="最低気温", value=f"{min_temperature}℃", inline=True)
            embed.add_field(name="最高気温", value=f"{max_temperature}℃", inline=True)
            embed.add_field(name="湿度", value=f"{humidity}%", inline=True)
            embed.add_field(name="風速", value=f"{wind_speed} m/s", inline=True)
            embed.add_field(name="気圧", value=f"{pressure} hPa", inline=True)
            embed.add_field(name="視程", value=f"{visibility/1000} km", inline=True)

            message = None

        await ctx.send(content=message, embed=embed)
    except aiohttp.ClientConnectorError as e:
        await ctx.send(f'接続エラーが発生しました: {e}')
    except asyncio.TimeoutError as e:
        await ctx.send(f'タイムアウトエラーが発生しました: {e}')
    except Exception as e:
        await ctx.send(f'エラーが発生しました: {e}')




last_used = {}
last_result = {}

# おみくじの結果ごとの画像URLとメッセージを辞書で定義
result_data = {
    "大吉": {
        "image": "https://drive.google.com/file/d/15h1lWskMwhKaYkp4T7AUJtU-rZrTgAj-/view?usp=sharing",
        "messages": ["今日はあなたにとって最高の日になるでしょう。", "あなたの夢は現実になり、あなたの努力は実を結びます。", "あなたは幸運に恵まれ、周囲の人々から愛されます。"]
    },
    "中吉": {
        "image": "https://drive.google.com/file/d/1ltJqK-pU2-TZ5Yu1f6AdqDo1sowIEz-Y/view?usp=sharing",
        "messages": ["あなたは困難を乗り越え、成功を収めるでしょう。", "あなたの努力は認められ、あなたの才能は光を放つでしょう。", "あなたは新しいチャンスを見つけ、それを活用するでしょう。"]
    },
    "小吉": {
        "image": "https://drive.google.com/file/d/1zpntgVlGFDaG88GXHp1sq6pwcybYJ1vw/view?usp=sharing",
        "messages": ["あなたは小さな幸せを見つけ、それを大切にするでしょう。", "あなたの日常は平穏で、あなたの心は安らぎます。", "あなたは自分自身を信じ、前進し続けるでしょう。"]
    },
    "吉": {
        "image": "https://drive.google.com/file/d/17Vsxdt-mNb_K8wEuat2SzQArsebi-VDY/view?usp=sharing",
        "messages": ["あなたは困難を乗り越え、成功を収めるでしょう。", "あなたの努力は認められ、あなたの才能は光を放つでしょう。", "あなたは新しいチャンスを見つけ、それを活用するでしょう。"]
    },
    "末吉": {
        "image": "https://drive.google.com/file/d/12Xxsva0oOxoXBDDPBv9a0yN-kMobZViR/view?usp=sharing",
        "messages": ["あなたは今は困難かもしれませんが、将来的には成功を収めるでしょう。", "あなたの努力は時間をかけて認められ、あなたの才能は最終的に光を放つでしょう。", "あなたは新しいチャンスを見つけ、それを活用するでしょう。"]
    },
    "凶": {
        "image": "https://drive.google.com/file/d/1B3XbFuMsz0182dOw_ce83jPiVctSx9S6/view?usp=sharing",
        "messages": ["あなたは困難に直面するかもしれませんが、それはあなたを強くするでしょう。", "あなたの努力は一時的に報われないかもしれませんが、あきらめずに続けてください。", "あなたは失敗から学び、それを成長の機会とするでしょう。"]
    },
    "大凶": {
        "image": "https://drive.google.com/file/d/1EOT2EwHQnGEOUbrfl4QK8F0K-ZBvqPxa/view?usp=sharing",
        "messages": ["あなたは大きな困難に直面するかもしれませんが、それはあなたを更に強くするでしょう。", "あなたの努力は一時的に報われないかもしれませんが、あきらめずに続けてください。", "あなたは失敗から学び、それを成長の機会とするでしょう。"]
    },
}

@bot.hybrid_command(name="omikuji")
async def omikuji(ctx):
    """おみくじをすることが出来るコマンド"""
    user_id = ctx.author.id
    now = datetime.now(timezone(timedelta(hours=+9)))  # JST

    if user_id in last_used and (now - last_used[user_id]).days < 1:
        await ctx.send(f'{ctx.author.mention}さん、一日に一回だけおみくじを引けます。また明日お試しください。')
        return

    results = list(result_data.keys())
    weights = [5, 15, 25, 25, 20, 5, 5]  # 結果の確率を調整

    # 前回の結果に基づいて確率を調整
    if user_id in last_result:
        if last_result[user_id] == "大吉":
            weights[results.index("凶")] += 10  # 「凶」の確率を上げる

    result = random.choices(results, weights=weights, k=1)[0]

    # 結果に対応するメッセージをランダムに選択
    message = random.choice(result_data[result]["messages"])

    # Embedを作成
    embed = discord.Embed(title="おみくじの結果", description=f'{ctx.author.mention} のおみくじの結果は... {result} です!\n{message}', color=0x00ff00)

    # 結果に対応する画像をEmbedに追加
    embed.set_thumbnail(url=result_data[result]["image"])

    await ctx.send(embed=embed)

    last_used[user_id] = now
    last_result[user_id] = result  # 結果を記録


@bot.hybrid_command(name="roleinfo")
@commands.check(is_admin)
async def roleinfo(ctx, *, role: discord.Role):
    """指定したロールの情報を表示するコマンド"""
    embed = discord.Embed(title=f'ロール情報: {role.name}', color=role.color)
    embed.add_field(name='ID', value=role.id, inline=True)
    embed.add_field(name='メンバー数', value=len(role.members), inline=True)
    embed.add_field(name='作成日時', value=f"<t:{int(role.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name='カラーコード', value=role.color, inline=True)
    embed.add_field(name='役職が表示されるか', value=role.hoist, inline=True)
    embed.add_field(name='管理者権限', value=role.permissions.administrator, inline=True)
    embed.add_field(name='メンション可能か', value=role.mentionable, inline=True)

    await ctx.send(embed=embed)

@roleinfo.error
async def roleinfo_error(ctx, error):
    """ロール表示エラー"""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("コマンドの使用法: `!roleinfo [ロール名]`")


@bot.hybrid_command()
async def serverinfo(ctx):
    """サーバーの情報を表示するコマンド"""
    server = ctx.guild
    server_id = server.id
    server_name = server.name
    server_created_at = server.created_at
    num_channels = len(server.channels)
    num_users = len(server.members)
    server_icon_url = str(server.icon.url) if server.icon else None

    embed = discord.Embed(title=f"{server.name}", color=discord.Color.blue())
    embed.add_field(name="ID", value=server_id, inline=True)
    embed.add_field(name="名前", value=server_name, inline=True)
    embed.add_field(name="サーバー作成日時", value=f"<t:{int(server.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="チャンネル数", value=num_channels, inline=True)
    embed.add_field(name="ユーザー数", value=num_users, inline=True)
    if server_icon_url:
        embed.set_thumbnail(url=server_icon_url)

    await ctx.send(embed=embed)

@bot.hybrid_command()
async def userinfo(ctx, member: discord.Member = None):
    """指定したユーザーの情報を表示するコマンド"""
    if member is None:
        member = ctx.message.author

    roles = [role.mention for role in member.roles if role.name != "@everyone"]

    joined_at = member.joined_at
    created_at = member.created_at

    embed = discord.Embed(title=f"{member.name}", color=discord.Color.blue())
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="グローバルネーム", value=member.display_name, inline=True)
    embed.add_field(name="アカウント作成日時", value=f"<t:{int(created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="サーバー参加日時", value=f"<t:{int(joined_at.timestamp())}:F>", inline=True)
    embed.add_field(name="役職", value=", ".join(roles), inline=True)
    embed.add_field(name="ニックネーム", value=member.nick if member.nick else "なし", inline=True)
    embed.set_thumbnail(url=member.display_avatar)

    await ctx.send(embed=embed)

@bot.hybrid_command(name="nick", pass_content=True)
@commands.check(is_admin)
async def change_nick(ctx, member: discord.Member, nick):
  """ニックネームを変更するコマンド(運営のみ)"""
  await member.edit(nick=nick)
  embed = discord.Embed(title="ニックネームを変更しました",description=f"変更された人物: {member.mention}",color=0xffffff)
  await ctx.send(embed=embed)

@change_nick.error
async def change_nick_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("このコマンドを実行する権限がありません。運営ロールが必要です。")


@bot.hybrid_command(name="botinfo", aliases=["ボット情報"])
async def botinfo(ctx):
    """このbotの情報を表示するコマンド"""
    bot_embed = discord.Embed(
        title="🤖 ボット情報",
        description="以下は、このボットの情報です。",
        color=0x3498db  # カスタマイズ可能な色
    )
    # ボットの情報を追加
    bot_embed.add_field(name="名前", value=bot.user.name, inline=True)
    bot_embed.add_field(name="ID", value=bot.user.id, inline=True)
    bot_embed.add_field(name="作成日時", value=bot.user.created_at.strftime("%Y-%m-%d %H:%M"), inline=True)
    bot_embed.add_field(name="ボットバージョン", value="1.0", inline=True)
    bot_embed.add_field(name="ボット開発者", value="<@993422862000062485>", inline=True)
    await ctx.send(embed=bot_embed)

# 予約メッセージを管理する辞書
scheduled_messages = []

@bot.hybrid_command(name="schedule")
@commands.check(is_admin)
async def schedule(ctx, year: int, month: int, day: int, hour: int, minute: int, channel: discord.TextChannel, *, content):
    """指定した時間にメッセージを送信できるコマンド (運営のみ)

    Args:
        year (int): 年
        month (int): 月
        day (int): 日
        hour (int): 時
        minute (int): 分
        channel (discord.TextChannel): メッセージを送信するチャンネル
        content (str): 送信するメッセージの内容
    """
    try:
        date_time = datetime(year, month, day, hour, minute)
    except ValueError:
        await ctx.send('日時を正しい形式で指定してください。例: !schedule 2024 1 31 12 00 #channel 予約メッセージ内容')
        return

    if date_time <= datetime.now():
        await ctx.send('過去の日時は予約できません。')
        return

    heapq.heappush(scheduled_messages, (date_time, channel.id, content))
    await ctx.send('予約メッセージを登録しました。')

async def check_scheduled_messages():
    await bot.wait_until_ready()
    while not bot.is_closed():
        while scheduled_messages and scheduled_messages[0][0] <= datetime.now():
            date_time, channel_id, content = heapq.heappop(scheduled_messages)
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(content)
                except discord.Forbidden:
                    print(f"メッセージを送信できません: {content}")
            else:
                print(f"チャンネルが見つかりません: {channel_id}")
        await asyncio.sleep(max(1, (scheduled_messages[0][0] - datetime.now()).total_seconds() if scheduled_messages else 10))

@schedule.error
async def schedule_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("このコマンドを実行する権限がありません。運営ロールが必要です。")


def restart_bot():
    os.execv(sys.executable, ['python'] + sys.argv)

@bot.hybrid_command(name='restart')
@commands.guild_only()  # サーバー上でのみ実行可能にする
@commands.check(is_admin)
async def restart(ctx):
    """このbotを再起動するコマンド(運営のみ)"""
    embed = discord.Embed(
        title="再起動中",
        description="ボットを再起動しています...",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)
    restart_bot()

@restart.error
async def restart_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        embed = discord.Embed(
            title="エラー",
            description="このコマンドはボットの所有者のみが利用できます。",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)



# あなた自身のAPIキーと検索エンジンIDを使用してください
API_KEY = "AIzaSyDhWUbZyKIBfLO9S0NDTl2sznc2hbVdLLk"
SEARCH_ENGINE_ID = "478b74ec0b8c64c53"


@bot.hybrid_command(name="google")
async def google(ctx, *, query: str):
    """google検索が出来るコマンド"""
    url = f"https://www.googleapis.com/customsearch/v1?key={API_KEY}&cx={SEARCH_ENGINE_ID}&q={query}"

    try:
        response = requests.get(url)
        data = response.json()

        search_results = data['items']

        embed = discord.Embed(title=f"Google検索結果: {query}", color=0x4285F4)  # Googleのロゴ色と同じ色を指定

        for result in search_results[:5]:  # 最初の5つの結果のみ表示
            title = result['title']
            link = result['link']
            snippet = result['snippet']

            embed.add_field(name=title, value=f"[リンク]({link})\n{snippet}", inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"検索中にエラーが発生しました: {e}")


@bot.hybrid_command(name="google-image")
async def image(ctx, *, query: str):
    """google画像検索が出来るコマンド"""
    image_url = f"https://www.googleapis.com/customsearch/v1?key={API_KEY}&cx={SEARCH_ENGINE_ID}&searchType=image&q={query}"

    try:
        response = requests.get(image_url)
        data = response.json()

        image_results = data['items']

        embed = discord.Embed(title=f"Google画像検索結果: {query}", color=0x4285F4)

        for result in image_results[:5]:  # 最初の5つの結果のみ表示
            title = result['title']
            link = result['link']
            embed.set_image(url=link)

            embed.add_field(name=title, value=f"[画像リンク]({link})", inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"画像検索中にエラーが発生しました: {e}")


@bot.hybrid_command(name="purge")
@commands.check(is_admin)
async def clear(ctx, amount: int = 1, user: discord.Member = None, *, content: str = None):
    """メッセージを削除するコマンド(運営のみ)"""
    if amount < 1:
        await ctx.send("削除するメッセージ数は1以上でなければなりません。")
        return

    def check_message(message):
        if user and message.author != user:
            return False
        if content and content.lower() not in message.content.lower():
            return False
        return True

    deleted = []
    async for message in ctx.channel.history(limit=None):
        if len(deleted) >= amount:
            break
        if check_message(message):
            deleted.append(message)
            await message.delete()

    embed = discord.Embed(title="メッセージ削除完了", description=f"削除されたメッセージ数: {len(deleted)}", color=discord.Color.green())
    await ctx.send(embed=embed, delete_after=5)

@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("このコマンドを実行する権限がありません。管理者権限が必要です。")




existing_tickets = {}  # ユーザーごとの既存のチケットを格納する辞書
deleted_tickets = set()  # 削除されたチケットの内容を格納するセット


@bot.hybrid_command(name="ticket-add")
async def ticket(ctx, *, issue: str):
    """チケットを作成するコマンド"""
    user_id = ctx.author.id
    if issue in deleted_tickets:
        deleted_tickets.remove(issue)  # 削除されたチケットのセットから削除する

    category = discord.utils.get(ctx.guild.categories, name="Tickets")
    if category is None:
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True),
            ctx.author: discord.PermissionOverwrite(read_messages=True)
        }
        category = await ctx.guild.create_category(name="Tickets", overwrites=overwrites)

    ticket_channel_name = issue[:50]  # チケットの内容から最初の50文字をチャンネル名に使用
    existing_channel = discord.utils.get(ctx.guild.text_channels, name=ticket_channel_name)
    if existing_channel:
        await ctx.send("すでにチケットが作成されています。")
        return

    channel = await category.create_text_channel(name=ticket_channel_name)
    await channel.set_permissions(ctx.author, read_messages=True, send_messages=True)

    embed = discord.Embed(title="新しいチケットが作成されました", description=f"問題: {issue}", color=discord.Color.green())
    embed.add_field(name="チケット作成者", value=ctx.author.mention, inline=True)
    embed.add_field(name="チケットチャンネル", value=channel.mention, inline=True)
    message = await channel.send(embed=embed)
    await ctx.send("チケットが正常に作成されました！")
    existing_tickets[user_id] = issue
    await message.add_reaction("🔒")



@ticket.error
async def ticket_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("チケットの内容を提供してください。例: `!ticket サーバーがダウンしています`")



@bot.hybrid_command(name="translate")
async def translate(ctx, *, arg):
    """日本語に翻訳するコマンド"""
    translator = Translator(service_urls=['translate.google.com'])
    translation = translator.translate(arg, dest='ja')
    
    embed = discord.Embed(title="翻訳結果", color=0x00ff00)
    embed.add_field(name="翻訳言語", value=LANGUAGES[translation.src], inline=True)
    embed.add_field(name="翻訳前", value=translation.origin, inline=True)
    embed.add_field(name="翻訳語", value=translation.text, inline=True)
    await ctx.send(embed=embed)



@bot.hybrid_command(name="permissions")
async def permissions(ctx, channel: discord.TextChannel=None, *, member: discord.Member=None):
    """指定したチャンネルまたはユーザーの権限を表示するコマンド"""
    if not member:
        member = ctx.message.author
    if not channel:
        channel = ctx.channel

    # 権限とその説明を定義
    permissions = {
        'General': {
            'administrator': '全ての権限を持つ',
            'view_audit_log': '監査ログを見る',
            'manage_guild': 'サーバーを管理する',
            'manage_roles': 'ロールを管理する',
            'manage_channels': 'チャンネルを管理する',
            'kick_members': 'メンバーをキックする',
            'ban_members': 'メンバーをBANする',
            'create_instant_invite': '招待を作成する',
            'change_nickname': 'ニックネームを変更する',
            'manage_nicknames': 'ニックネームを管理する'
        },
        'Text': {
            'read_messages': 'メッセージを読む',
            'send_messages': 'メッセージを送信する',
            'send_tts_messages': 'TTSメッセージを送信する',
            'manage_messages': 'メッセージを管理する',
            'embed_links': 'リンクを埋め込む',
            'attach_files': 'ファイルを添付する',
            'read_message_history': 'メッセージの履歴を読む',
            'mention_everyone': '@everyone, @here, and all rolesをメンションする',
            'use_external_emojis': '外部の絵文字を使用する'
        },
        'Voice': {
            'connect': '接続する',
            'speak': '話す',
            'mute_members': 'メンバーをミュートする',
            'deafen_members': 'メンバーの音声を遮断する',
            'move_members': 'メンバーを移動する',
            'use_voice_activation': '音声検出を使用する'
        }
    }

    # 絵文字で権限の有無を表示
    enabled = '✅'
    disabled = '❌'

    embed = discord.Embed(title=f'{member} の {channel.name} チャンネルでの権限')
    for category, perms in permissions.items():
        value = '\n'.join(f'{enabled if getattr(channel.permissions_for(member), perm) else disabled} {perm}: {desc}' for perm, desc in perms.items())
        embed.add_field(name=category, value=value, inline=True)

    await ctx.send(embed=embed)




cache = TTLCache(maxsize=100, ttl=300)

@bot.hybrid_command(name="5choen")
async def generate(ctx, top: str, bottom: str):
    """５兆円ジェネレーターを生成するコマンド"""
    url = f"https://gsapi.cbrx.io/image?top={top}&bottom={bottom}"

    if url in cache:
        file = discord.File(cache[url], filename="image.png")
        embed = discord.Embed(title="5000兆円ジェネレーター", description="生成された画像です。")
        embed.set_image(url="attachment://image.png")
        await ctx.send(file=file, embed=embed)
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.read()
                with open("image.png", 'wb') as f:
                    f.write(data)
                cache[url] = "image.png"
                file = discord.File("image.png", filename="image.png")
                embed = discord.Embed(title="5000兆円ジェネレーター", description="生成された画像です。")
                embed.set_image(url="attachment://image.png")
                await ctx.send(file=file, embed=embed)
            else:
                await ctx.send('画像の生成に失敗しました。')


@bot.hybrid_command(name='george')
async def send_message(ctx, *, message):
    "ジョージの話聞かない奴危機感持ったほうがいいよ"
    responses = {
        'この時期にTwitterやってる受験生、ガチで危機感持った方がいいよ': 'https://pbs.twimg.com/media/GFQRJcKa4AAmBhz?format=jpg&name=900x900',
        '今頃𝕏のことTwitterとか呼んでる人マジで危機感持った方がいいよ': 'https://pbs.twimg.com/media/GFkR3K5aQAAQvF8?format=jpg&name=small',
        'おでんでご飯いく人ガチで危機感持った方がいいよ': 'https://pbs.twimg.com/media/GFGGd9ubAAA8Vqh?format=jpg&name=small',
        '雪なのに帰れない会社、マジで危機感持った方がいいよ': 'https://pbs.twimg.com/media/GFj3BhdbAAAGt4f?format=jpg&name=900x900',
        '低重量で効かせるとか言ってるトレーニー。ガチで危機感持った方がいい。': 'https://pbs.twimg.com/media/GFao24zaYAAhlqF?format=jpg&name=900x900',
        'ブラックホールの謎を解明していない人類重力の本質に気付いてない人類マジで危機感持った方がいいと思う': 'https://pbs.twimg.com/media/GFGGwC4bAAA2jq5?format=jpg&name=900x900',
        'すぐゲームに課金する奴、ガチで危機感持った方がいいよ': 'https://pbs.twimg.com/media/GFpi6-CbsAAfbo4?format=jpg&name=small',
        '呪術も扱えない猿共マジで危機感持った方がいいよ': 'https://pbs.twimg.com/media/GFeMIySaEAAW7JJ?format=jpg&name=small',
        '5G使ってる奴は危機感持った方がいい': 'https://pbs.twimg.com/media/GFFZw8CbIAAxgsm?format=jpg&name=900x900',
        'ロリで抜いてる人、マジで危機感持った方がいいよ。': 'https://pbs.twimg.com/media/GFa1QkEbsAAL1sY?format=jpg&name=900x900',
        '春休みなのに予定がない大学生はガチで危機感持ったほうがいい。': 'https://pbs.twimg.com/media/GFt4sCcbQAA5Bdp?format=jpg&name=small',
        '黙祷意味ないとか言ってる男、マジで危機感持った方がいいよ': 'https://pbs.twimg.com/media/GFQD4TobcAA4izm?format=jpg&name=900x900',
        '運動部？入る必要ないよ危機感？持たなくていいよ絶　対　君　は　モ　テ　る　よ　！　！': 'https://pbs.twimg.com/media/GF43eT5asAANolh?format=jpg&name=900x900',
        '納税額の低い男、ガチで危機感持ったほうがいいと思うよ': 'https://pbs.twimg.com/media/GFuW_8CawAEYy8H?format=jpg&name=900x900',
        'ログインスタンプの魔法石をバレンタインガチャだと思ってる奴､ガチで危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GFyG35naoAA7fPT?format=jpg&name=large',
        'いい歳して風呂で小便してるやつ、マジで危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GGOksUlacAA6MqK?format=png&name=small',
        'まじで学歴しかアイデンティティ無いやつ危機感持ったほうがいいよ誰も関わりたくないから': 'https://pbs.twimg.com/media/GFQtvrRaQAAjd2i?format=jpg&name=medium',
        'もうそろそろ高校生活終わるのに童貞の奴はマジで危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GGYEzXHa4AA7AgT?format=jpg&name=medium',
        'X以外で友達いないやつ危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GGqpXbrboAAZCny?format=jpg&name=small',
        'バレンタインでチョコ貰えない人たち危機感持ったほうがいいよ。': 'https://pbs.twimg.com/media/GGOfUVdaoAAn6BG?format=jpg&name=small',
        '受験生なのにTwitter毎日見てるやつ危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GGNtNI6akAAlzID?format=jpg&name=small',
        '阪神煽ってるやつ、ガチで危機感を持ったほうがいいよ': 'https://pbs.twimg.com/media/GIS4Lm7asAA2-sb?format=jpg&name=medium',
        'ネットにしか友達がいない人ガチで危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GH090f_bwAAoAsh?format=jpg&name=medium',
        '俺のこと未だに叩いてる奴、そろそろ危機感持ったほうがいいよ。': 'https://pbs.twimg.com/media/GF7wiw1a0AAZFOx?format=jpg&name=small',
        '今焦ってるやつ危機感持ったほうがいいよ。けどそれはお前が頑張った軌跡だから誇りも持った方がいいよ。': 'https://pbs.twimg.com/media/GIG2M4nbUAAvp_U?format=jpg&name=small',
        '女性を下に見てる自称ドSの男ガチで危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GFP-mpGakAA4wWb?format=jpg&name=medium',
        'サイゼが一店舗もない宮崎は危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GFKWAtXaYAAUSqC?format=jpg&name=medium',
        'デカければ釣れると思ってるやつ危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GHU2Sc-bEAAYecx?format=jpg&name=large',
        '危機感持ってない男、マジでヤバいから、危機感持ったほうがいいと思うよ': 'https://pbs.twimg.com/media/GGS8OhgbEAAzeL0?format=jpg&name=medium',
        '私危機です、ガチで危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GFualDWawAALcJM?format=jpg&name=large',
        '【歴史を変えに来た】\n信長マジで危機感持ったほうがいいよ': 'https://pbs.twimg.com/media/GIEpk1naUAEOxEf?format=jpg&name=large',
    }
    response = random.choice(list(responses.keys()))
    image_url = responses[response]

    embed = discord.Embed(title="あなたのメッセージ", description=message, color=0x00ff00)
    embed.add_field(name="ジョージからの返答", value=response, inline=False)
    embed.set_image(url=image_url)
    await ctx.send(embed=embed)


@bot.hybrid_command(name="fortnite-profile")
async def fortnite(ctx, player_name: str):
    """指定したユーザーのフォートナイトのステータスを表示するコマンド"""
    headers = {'Authorization': '32df38c7-c5ab-4174-b88b-8b49fe93b234'}
    response = requests.get(f'https://fortnite-api.com/v1/stats/br/v2?name={player_name}', headers=headers)
    data = response.json()

    # 取得した情報から特定のデータを抽出
    try:
        overall = data['data']['stats']['all']['overall']
        solo = data['data']['stats']['all']['solo']
        duo = data['data']['stats']['all']['duo']
        trio = data['data']['stats']['all']['trio']
        squad = data['data']['stats']['all']['squad']

        # Embedを作成
        embed = discord.Embed(title=f"{player_name}さんのFortniteプロフィール", color=0x00ff00)
        embed.add_field(name="全体", value=f"スコア: {overall['score']}\nキル数: {overall['kills']}\nマッチ数: {overall['matches']}\nKD: {overall['kd']}\n勝率: {overall['winRate']}%", inline=False)
        embed.add_field(name="ソロ", value=f"スコア: {solo['score']}\nキル数: {solo['kills']}\nマッチ数: {solo['matches']}\nKD: {solo['kd']}\n勝率: {solo['winRate']}%", inline=False)
        embed.add_field(name="デュオ", value=f"スコア: {duo['score']}\nキル数: {duo['kills']}\nマッチ数: {duo['matches']}\nKD: {duo['kd']}\n勝率: {duo['winRate']}%", inline=False)
        embed.add_field(name="トリオ", value=f"スコア: {trio['score']}\nキル数: {trio['kills']}\nマッチ数: {trio['matches']}\nKD: {trio['kd']}\n勝率: {trio['winRate']}%", inline=False)
        embed.add_field(name="スクワッド", value=f"スコア: {squad['score']}\nキル数: {squad['kills']}\nマッチ数: {squad['matches']}\nKD: {squad['kd']}\n勝率: {squad['winRate']}%", inline=False)

        # EmbedをDiscordチャンネルに送信
        await ctx.send(embed=embed)
    except KeyError:
        await ctx.send("申し訳ありません、探している情報が見つかりませんでした。")


@bot.hybrid_command(name="fortnite-map")
async def map(ctx):
    """フォートナイトのマップを表示するコマンド"""
    response = requests.get('https://fortnite-api.com/v1/map?language=ja')
    data = response.json()
    if 'data' in data and 'images' in data['data']:
        map_image_url = data['data']['images']['pois']
        embed = discord.Embed(title="現在のマップ")
        embed.set_image(url=map_image_url)
        await ctx.send(embed=embed)


ALS_API_KEY = 'a6e02120697281e9270cf8da058fc7db'

@bot.hybrid_command(name="apex-map")
async def apexmap(ctx):
    """APEXのマップローテーションを表示するコマンド"""
    try:
        response = requests.get('https://api.mozambiquehe.re/maprotation?auth=a6e02120697281e9270cf8da058fc7db')
        response.raise_for_status()  # これにより、HTTPエラーが発生した場合に例外が発生します
    except requests.exceptions.RequestException as err:
        await ctx.send(f'APIへのリクエスト中にエラーが発生しました: {err}')
        return

    data = response.json()

    current_map = data['current'].get('map', '不明')
    remaining_time = data['current'].get('remainingTimer', '不明')
    current_map_image = data['current'].get('asset', '')
    next_map = data['next'].get('map', '不明')

    embed = discord.Embed(title="Apex Legends マップローテーション", color=0x00ff00)
    embed.add_field(name="現在のマップ", value=current_map, inline=False)
    embed.add_field(name="残り時間", value=remaining_time, inline=False)
    embed.add_field(name="次のマップ", value=next_map, inline=False)
    embed.set_thumbnail(url=current_map_image)

    await ctx.send(embed=embed)





@bot.hybrid_command(name="qr")
async def qr(ctx, *, url: str):
    """指定したURLのQRコードを生成するコマンド"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    with BytesIO() as image_binary:
        img.save(image_binary, 'PNG')
        image_binary.seek(0)

        file = discord.File(fp=image_binary, filename='qr.png')
        embed = discord.Embed(title="QR Code", description=f"URL:{url}")
        embed.set_image(url="attachment://qr.png")
        await ctx.send(file=file, embed=embed)




async def send_reminder(user, delay, message):
    await asyncio.sleep(delay)
    await user.send(message)

@bot.hybrid_command(name="alarm")
async def timed_message(ctx, hour: int, minute: int, *, message: str):
    """指定した時間にお知らせするコマンド"""
    # 現在の時間を取得します
    now = datetime.now()

    # 指定された時間を現在の日付に適用します
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # もし指定された時間がすでに過ぎていたら、次の日に設定します
    if target_time < now:
        target_time += timedelta(days=1)

    # 現在の時間と指定された時間の差（秒）を計算します
    delay = (target_time - now).total_seconds()

    # お知らせメッセージを送信します
    for reminder in [30, 15, 10, 5]:
        reminder_seconds = reminder * 60
        if delay > reminder_seconds:
            bot.loop.create_task(send_reminder(ctx.author, delay - reminder_seconds, f"{ctx.author.mention}\n指定した時間まで残り{reminder}分になりました。"))

    await ctx.send(f"{ctx.author.mention}に{hour}時{minute}分にメッセージを送信します。")
    await asyncio.sleep(delay)

    # Embedメッセージを作成します
    embed = discord.Embed(description=f"{ctx.author.mention}\n{message}の時間になりました。")
    await ctx.author.send(embed=embed)


@bot.hybrid_command(name="top")
async def top(ctx):
    # メッセージのリストを取得し、最初のメッセージを取得します
    async for message in ctx.channel.history(limit=1, oldest_first=True):
        # メッセージが見つかった場合、Embedを作成して送信します
        if message:
            embed = discord.Embed(title="最上部のメッセージ", description=message.content, color=discord.Color.blue())
            embed.add_field(name="送信者", value=message.author.mention, inline=False)
            embed.add_field(name="リンク", value=f"[メッセージへのリンク]({message.jump_url})", inline=False)
            await ctx.send(embed=embed)
            break
    else:
        await ctx.send("メッセージが見つかりませんでした")































#bot.event

@bot.event
async def on_ready():
    channel = bot.get_channel(1118839526836678659)
    await bot.change_presence(status=discord.Status.online)

    """bot起動"""
    channel = bot.get_channel(1204010572094636094)
    if channel:
        embed = discord.Embed(title="ボットが起動しました", color=discord.Color.green())
        await channel.send(embed=embed)
    else:
        print("準備完了")

    # ボットがオンラインの場合
    if bot.is_ready():
        await bot.change_presence(activity=discord.Game(name=f'参加してるサーバー数{len(bot.guilds)}'))
    # ボットがオフラインの場合
    else:
        await bot.change_presence(activity=None)

    await bot.tree.sync()
    bot.loop.create_task(check_scheduled_messages())
    check_scheduled_tasks.start()


# 指定した日付と時間にメッセージを送信するタスクのリスト
scheduled_tasks = [
    {"year": datetime.now().year, "month": 1, "day": 1, "hour": 24, "minute": 0, "message": "happy birthday <@993652613759373313>  :zap:\n\nおめでとうございます:tada:\nこれからも<@993652613759373313>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 1, "day": 15, "hour": 24, "minute": 0, "message": "happy birthday <@1092362241464074260> :zap:\n\nおめでとうございます:tada:\nこれからも<@1092362241464074260>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 1, "day": 21, "hour": 24, "minute": 0, "message": "happy birthday <@802862694595821578> :zap:\n\nおめでとうございます:tada:\nこれからも<@802862694595821578>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 1, "day": 28, "hour": 24, "minute": 0, "message": "happy birthday <@918085158970740747> :zap:\n\nおめでとうございます:tada:\nこれからも<@918085158970740747>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 2, "day": 20, "hour": 24, "minute": 0, "message": "happy birthday <@1131083527211974737> :zap:\n\nおめでとうございます:tada:\nこれからも<@1131083527211974737>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 4, "day": 6, "hour": 24, "minute": 0, "message": "happy birthday <@1027968954389500034> :zap:\n\nおめでとうございます:tada:\nこれからも<@1027968954389500034>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 4, "day": 11, "hour": 24, "minute": 0, "message": "happy birthday <@936944747019374622> <@1091028619415003259> :zap:\n\nおめでとうございます:tada:\nこれからも<@936944747019374622> <@1091028619415003259> は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 4, "day": 15, "hour": 24, "minute": 0, "message": "happy birthday <@1027142703626059776> :zap:\n\nおめでとうございます:tada:\nこれからも<@1027142703626059776>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 6, "day": 5, "hour": 24, "minute": 0, "message": "happy birthday <@824553817139838977> :zap:\n\nおめでとうございます:tada:\nこれからも<@824553817139838977>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 6, "day": 15, "hour": 24, "minute": 0, "message": "happy birthday <@877911391875530803> :zap:\n\nおめでとうございます:tada:\nこれからも<@877911391875530803>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 6, "day": 18, "hour": 24, "minute": 0, "message": "happy birthday <@964710203465556078> :zap:\n\nおめでとうございます:tada:\nこれからも<@964710203465556078>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 6, "day": 21, "hour": 24, "minute": 0, "message": "happy birthday <@986971587465052160> :zap:\n\nおめでとうございます:tada:\nこれからも<@986971587465052160>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 7, "day": 14, "hour": 24, "minute": 0, "message": "happy birthday <@1053686372877226044> :zap:\n\nおめでとうございます:tada:\nこれからも<@1053686372877226044>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 7, "day": 21, "hour": 24, "minute": 0, "message": "happy birthday <@1003873363942449182> :zap:\n\nおめでとうございます:tada:\nこれからも<@1003873363942449182>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 8, "day": 4, "hour": 24, "minute": 0, "message": "happy birthday <@1092442490403041300> :zap:\n\nおめでとうございます:tada:\nこれからも<@1092442490403041300>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 8, "day": 14, "hour": 24, "minute": 0, "message": "happy birthday <@675911677295853578> :zap:\n\nおめでとうございます:tada:\nこれからも<@675911677295853578>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 8, "day": 15, "hour": 24, "minute": 0, "message": "happy birthday <@1088447225639735296> :zap:\n\nおめでとうございます:tada:\nこれからも<@1088447225639735296> は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 8, "day": 20, "hour": 24, "minute": 0, "message": "happy birthday <@986577850184400946> <@1166348875200745543> :zap:\n\nおめでとうございます:tada:\nこれからも<@986577850184400946> <@1166348875200745543>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 8, "day": 27, "hour": 24, "minute": 0, "message": "happy birthday <@987725333497253958> :zap:\n\nおめでとうございます:tada:\nこれからも<@987725333497253958>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 10, "day": 2, "hour": 24, "minute": 0, "message": "happy birthday <@993422862000062485> :zap:\n\nおめでとうございます:tada:\nこれからも<@993422862000062485>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 10, "day": 3, "hour": 24, "minute": 0, "message": "happy birthday <@1081534077296971838> :zap:\n\nおめでとうございます:tada:\nこれからも<@1081534077296971838>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 10, "day": 24, "hour": 24, "minute": 0, "message": "happy birthday <@924278055294345217> :zap:\n\nおめでとうございます:tada:\nこれからも<@924278055294345217>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 10, "day": 25, "hour": 24, "minute": 0, "message": "happy birthday <@695100148006780949> :zap:\n\nおめでとうございます:tada:\nこれからも<@695100148006780949>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 10, "day": 26, "hour": 24, "minute": 0, "message": "happy birthday <@1081560477601107998> :zap:\n\nおめでとうございます:tada:\nこれからも<@1081560477601107998>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 11, "day": 6, "hour": 24, "minute": 0, "message": "happy birthday <@841207764596293633> :zap:\n\nおめでとうございます:tada:\nこれからも<@841207764596293633>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 11, "day": 16, "hour": 24, "minute": 0, "message": "happy birthday <@957152977146224641> :zap:\n\nおめでとうございます:tada:\nこれからも<@957152977146224641>は成長していきます！応援してあげてください！"},
    {"year": datetime.now().year, "month": 11, "day": 21, "hour": 24, "minute": 0, "message": "happy birthday <@1036870189725274145> :zap:\n\nおめでとうございます:tada:\nこれからも<@1036870189725274145>は成長していきます！応援してあげてください！"},
]

CHANNEL_ID = 1140529860100493333

@tasks.loop(seconds=1)
async def check_scheduled_tasks():
    now = datetime.now()
    for task in scheduled_tasks:
        if now.year == task["year"] and now.month == task["month"] and now.day == task["day"] and now.hour == task["hour"] and now.minute == task["minute"]:
            channel = bot.get_channel(CHANNEL_ID)
            await channel.send(task["message"])
            task["year"] += 1  # タスクを次の年に更新






@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild and message.guild.id != 1140529859467161722:
        return

    if message.embeds:
        embed = message.embeds[0]
        trans_fields = []

        for field in embed.fields:
            trans_name = translator.translate(field.name, dest="ja").text
            trans_value = translator.translate(field.value, dest="ja").text
            trans_fields.append((trans_name, trans_value))

        trans_title = translator.translate(embed.title, dest="ja").text if embed.title else ""
        trans_desc = translator.translate(embed.description, dest="ja").text if embed.description else ""

        trans_embed = discord.Embed(title=trans_title, description=trans_desc, color=embed.color, url=embed.url)

        for name, value in trans_fields:
            trans_embed.add_field(name=name, value=value, inline=False)

        await message.channel.send(f"{message.content}", embed=trans_embed)

    for word in message.content.split():
        if word.startswith('https://discord.com/channels/') or word.startswith('https://discordapp.com/channels/'):
            parts = word.split('/')
            if len(parts) == 7:
                guild_id, channel_id, message_id = parts[4], parts[5], parts[6]
                try:
                    guild = bot.get_guild(int(guild_id))
                    channel = None
                    if guild:
                        channel = guild.get_channel(int(channel_id))
                    else:
                        channel = await bot.fetch_channel(int(channel_id))
                    fetched_message = await channel.fetch_message(int(message_id))
                    invite_link = await channel.create_invite(max_age=300)
                    message_content = fetched_message.content

                    embed = discord.Embed()
                    embed.add_field(name=" ", value=f"```{message_content}```", inline=True)
                    embed.add_field(name="🗨️メッセージ詳細", value=f"サーバー：{guild.name}\n チャンネル：{channel.name}\n メッセージ：{fetched_message.author.display_name}\n メッセージ作成時間：{fetched_message.created_at.strftime('%Y/%m/%d %H:%M:%S')}", inline=False)
                    embed.set_author(name=fetched_message.author.display_name, icon_url=fetched_message.author.display_avatar)
                    embed.set_footer(text=fetched_message.author.guild.name, icon_url=fetched_message.author.guild.icon)

                    if fetched_message.attachments:
                        embed.set_image(url=fetched_message.attachments[0].url)

                    await message.channel.send(embed=embed)
                except discord.NotFound:
                    await message.channel.send("メッセージが見つかりませんでした。")
                except discord.Forbidden:
                    await message.channel.send("権限がありません。")
                except Exception as e:
                    print(e)
                    await message.channel.send("エラーが発生しました。")

    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return  # Botの場合は無視する

    if member.guild.id != 1140529859467161722:
        return  # 特定のサーバー以外は無視する

    channel_id = 1211243199062876222  # 通知を送信したいチャンネルのIDに置き換える
    notification_channel = bot.get_channel(channel_id)

    # ボイスチャンネル更新時の処理
    # ボットが接続している通話を取得
    voice_client = member.guild.voice_client

    if voice_client is not None:
        # 通話に他のメンバーがいなくなった場合
        if len(voice_client.channel.members) == 1:  # ボット自身も含まれているので1を引く
            # 通話から切断
            await voice_client.disconnect()

    """一時的なチャンネル作成"""
    if before.channel is None and after.channel and after.channel.id == 1199967152174792736:
        category = after.channel.category
        new_channel_name = f"{member.display_name}'s Channel"
        new_channel = await category.create_voice_channel(new_channel_name)
        await member.move_to(new_channel)
    elif before.channel and not after.channel:
        if before.channel.name == f"{member.display_name}'s Channel":
            # チャンネルがまだ存在するか確認
            existing_channel = discord.utils.get(member.guild.voice_channels, name=f"{member.display_name}'s Channel")
            if existing_channel:
                await existing_channel.delete()
    elif before.channel and after.channel and before.channel != after.channel:
        if before.channel.name == f"{member.display_name}'s Channel":
            # チャンネルがまだ存在するか確認
            existing_channel = discord.utils.get(member.guild.voice_channels, name=f"{member.display_name}'s Channel")
            if existing_channel:
                await existing_channel.delete()

    # ボイスチャンネル参加/切断時の通知処理
    if before.channel is None and after.channel is not None:
        # 通話に参加した場合
        channel_mention = after.channel.mention
        member_mentions = ' '.join([m.mention for m in after.channel.members if not m.bot])  # 参加しているBot以外のメンバーのメンションのリストを作成
        embed = discord.Embed(title="通話参加通知", description=f"{member.mention} さんが {channel_mention} に参加しました。\n現在のメンバー:\n{member_mentions}", color=discord.Color.green())
        await notification_channel.send(embed=embed)

    elif before.channel is not None and after.channel is None:
        # 通話から切断された場合
        channel_mention = before.channel.mention
        member_mentions = ' '.join([m.mention for m in before.channel.members if not m.bot])  # 参加しているBot以外のメンバーのメンションのリストを作成
        embed = discord.Embed(title="通話切断通知", description=f"{member.mention} さんが {channel_mention} から切断されました。\n現在のメンバー:\n{member_mentions}", color=discord.Color.red())
        await notification_channel.send(embed=embed)


























@bot.event
async def on_raw_reaction_add(payload):
    if payload.member.bot:
        return
    if payload.emoji.name == "🔒":
        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if message.author == bot.user:
            # 削除されたチケットの内容を記録
            issue = message.embeds[0].description.split(': ')[1]  # チケットの内容を取得
            deleted_tickets.add(issue)  # 削除されたチケットの内容をセットに追加
            await channel.delete()

@bot.event
async def on_command(ctx):
    """コマンド使用ログ"""
    guild_id_to_log = 1140529859467161722  # ログを送信したいサーバーのIDに置き換えてください
    guild = ctx.guild  # コマンドが実行されたサーバーを取得

    # コマンドが実行されたサーバーのIDがログを送信したいサーバーのIDと一致するか確認
    if guild and guild.id == guild_id_to_log:
        channel = ctx.channel  # 使用されたチャンネルを取得

        embed = discord.Embed(title="コマンド使用ログ", color=0x00ff00)
        embed.add_field(name="使用コマンド", value=f"```{ctx.command}```", inline=False)
        command_time = ctx.message.created_at.strftime('%Y /%m / %d %H:%M')
        embed.add_field(name="使用時刻", value=command_time, inline=False)
        embed.add_field(name="チャンネル", value=channel.mention, inline=False)
        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar)

        # 送信したいチャンネルのIDに置き換えてください
        channel_id = 1190485105165209681
        log_channel = bot.get_channel(channel_id)
        if log_channel:
            await log_channel.send(embed=embed)
        else:
            print("指定したIDのチャンネルが見つかりません")


@bot.event
async def on_message_delete(message):
    if message.author.bot or message.guild.id != 1140529859467161722:  # あなたのサーバーのIDに置き換えてください
        return  # ボットのメッセージと他のサーバーからのメッセージは無視する

    log_channel_id = 1190485105165209681  # ログを送信するチャンネルのIDに置き換えてください
    log_channel = bot.get_channel(log_channel_id)

    if log_channel:
        now = datetime.now()  # 現在の日時を取得
        formatted_time = now.strftime('%Y /%m /%d %H:%M')  # 時刻をフォーマット
        embed = discord.Embed(title="メッセージ削除ログ", color=discord.Color.red())
        embed.add_field(name="メッセージ", value=f"```{message.content}```", inline=False)
        embed.add_field(name="時刻", value=formatted_time, inline=False)
        embed.add_field(name="チャンネル", value=message.channel.mention, inline=False)
        embed.set_footer(text=message.author.display_name, icon_url=message.author.display_avatar)

        # メッセージに画像が含まれている場合
        if message.attachments:
            image_urls = [attachment.url for attachment in message.attachments if attachment.width and attachment.height]
            if image_urls:
                for image_url in image_urls:
                    embed_with_image = embed.copy()
                    embed_with_image.set_image(url=image_url)
                    await log_channel.send(embed=embed_with_image)
        else:
            await log_channel.send(embed=embed)



@bot.event
async def on_message_edit(before, after):
    """メッセージ編集ログ"""
    if before.content != after.content and after.guild.id == 1140529859467161722:
        channel_id = 1190485105165209681  # ログを送信するチャンネルのID
        log_channel = bot.get_channel(channel_id)

        if log_channel:
            embed = discord.Embed(
                title="メッセージ編集ログ",
                color=discord.Color.blue()
            )
            embed.add_field(name="変更前", value=f"```{before.content}```", inline=False)  # 変更前のメッセージをコードブロックで表示
            embed.add_field(name="変更後", value=f"```{after.content}```", inline=False)   # 変更後のメッセージをコードブロックで表示
            if after.edited_at is not None:  # メッセージが編集された場合のみ時刻を表示
                embed.add_field(name="時刻", value=f"{after.edited_at.strftime('%Y /%m / %d %H:%M')}")
            embed.add_field(name="チャンネル", value=f"{after.channel.mention}", inline=False)
            embed.set_footer(text=after.author.display_name, icon_url=after.author.display_avatar)

            await log_channel.send(embed=embed)








# エラーログを出力するチャンネルのID
ERROR_LOG_CHANNEL_ID = 1204010572094636094

# エラーログを送信する関数
async def send_error_log(channel_id, event_name, error_message, ctx=None):
    error_log_channel = bot.get_channel(channel_id)
    if error_log_channel:
        embed = discord.Embed(title=f"An error occurred in event '{event_name}'", description="詳細情報は以下の通りです：", color=discord.Color.red())
        embed.add_field(name="エラーメッセージ", value=f"```{error_message}```", inline=True)
        if ctx:
            embed.add_field(name="発生したコンテキスト", value=f"サーバー: {ctx.guild.name} ({ctx.guild.id})\nチャンネル: {ctx.channel.name} ({ctx.channel.id})\nユーザー: {ctx.author.name} ({ctx.author.id})")
        embed.set_footer(text="エラーログが役立つ情報を提供するよう心がけてください。")
        await error_log_channel.send(embed=embed)
    else:
        print("エラーログのチャンネルが見つかりません。ERROR_LOG_CHANNEL_IDを確認してください。")

# エラーハンドラデコレータ
@bot.event
async def on_error(event, *args, **kwargs):
    """エラー"""
    error_message = traceback.format_exc()
    await send_error_log(ERROR_LOG_CHANNEL_ID, event, error_message)

# コマンドエラーハンドラデコレータ
@bot.event
async def on_command_error(ctx, error):
    """コマンドエラー"""
    if isinstance(error, commands.CommandError):
        error_message = getattr(error, 'original', error)
        await send_error_log(ERROR_LOG_CHANNEL_ID, f"コマンド '{ctx.command}'", str(error_message))


@bot.event
async def on_member_join(member):
    """新規加入者歓迎"""
    # サーバーに参加したのがBotであれば何もしない
    if member.bot:
        return

    # サーバーのIDを指定
    target_server_id = 1140529859467161722 # ここにサーバーのIDを入力

    # サーバーIDが一致しない場合は処理しない
    if member.guild.id != target_server_id:
        return

    # 歓迎メッセージを送信するチャンネルのID
    welcome_channel_id = 1140529860100493333
    # 歓迎メッセージの作成
    welcome_message = f"{member.mention}さんよろしくお願いします！"
    # 歓迎メッセージを送信するチャンネルを取得
    welcome_channel = bot.get_channel(welcome_channel_id)
    # 歓迎メッセージを送信
    await welcome_channel.send(welcome_message)
    # 新規メンバーに付与する役職のID
    welcome_role_id = 1141974521142849557
    # 新規メンバーに付与する役職を取得
    welcome_role = member.guild.get_role(welcome_role_id)
    # 役職が存在する場合は、新規メンバーに役職を付与
    if welcome_role:
        await member.add_roles(welcome_role)






bot.run(TOKEN)
