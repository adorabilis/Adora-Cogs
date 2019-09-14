from .ffembed import FFEmbed

def setup(bot):
    cog = FFEmbed(bot)
    bot.add_cog(cog)
