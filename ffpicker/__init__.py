from .ffpicker import FFPicker

def setup(bot):
    cog = FFPicker(bot)
    bot.add_cog(cog)
