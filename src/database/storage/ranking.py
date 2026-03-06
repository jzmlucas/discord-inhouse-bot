import discord

def get_medal(mmr):
    if mmr <= 1000: return "🐒 Iniciante"
    if mmr < 1100: return "🍑 Jogador mediano"
    if mmr < 1200: return "🚀 Evoluindo"
    if mmr < 1500: return "🛡️ Bom jogador"
    if mmr < 2000: return "⭐ Acima da média"
    if mmr < 3000: return "💎 Professor de Dota"
    if mmr < 4000: return "🔱 Deus do jogo"
    return "🔥 Rei da Liga"

def get_next_rank_info(mmr):
    ranks = [
        (1000, "Iniciante"), (1100, "Jogador mediano"), (1200, "Evoluindo"),
        (1500, "Bom jogador"), (2000, "Acima da média"), 
        (3000, "Professor de Dota"), (4000, "Deus do jogo")
    ]
    for value, name in ranks:
        if mmr < value:
            return name, value - mmr
    return "Máximo", 0

def get_progress_bar(mmr):
    steps = 10
    percentage = (mmr % 100) / 100
    filled = int(percentage * steps)
    bar = "🟦" * filled + "⬛" * (steps - filled)
    return f"{bar} `{int(percentage*100)}%`"

def get_rank_color(mmr):
    """Esta função resolve o erro da imagem 2"""
    if mmr < 1000: return discord.Color.light_gray()
    if mmr < 1500: return discord.Color.blue()
    if mmr < 2000: return discord.Color.purple()
    return discord.Color.gold()