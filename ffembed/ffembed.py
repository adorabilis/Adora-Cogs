import asyncio
import discord
import re
import requests

from bs4 import BeautifulSoup
from redbot.core import checks, commands, Config

__version__ = "1.0.1"

BaseCog = getattr(commands, "Cog", object)


class FFEmbed(BaseCog):
    """
    Show FanFiction, AO3, and SIYE story info in an embed message
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = requests.Session()
        self.config = Config.get_conf(
            self, identifier=77232917, force_registration=True
        )
        self.config.register_guild(enabled=True, disabled_channels=[])

    @commands.guild_only()
    @commands.command()
    @checks.is_owner()
    async def ffreset(self, ctx):
        """
        Reset FFEmbed's config for this server
        """
        await ctx.send(
            "Are you sure you want to reset FFEmbed's config for "
            "this server? Type 'yes' to proceed."
        )
        try:
            msg = await self.bot.wait_for(
                "message", check=lambda m: m.content.lower() == "yes", timeout=8
            )
        except asyncio.TimeoutError:
            await ctx.send("Command timed out. No changes were made.")
        else:
            await self.config.guild(ctx.guild).clear()
            await ctx.send("FFEmbed's config for this server has been reset.")

    @commands.guild_only()
    @commands.group(name="fftoggle", invoke_without_command=True)
    @checks.is_owner()
    async def toggle(self, ctx):
        """
        Enable or disable FFEmbed
        """
        enabled = await self.config.guild(ctx.guild).enabled()
        status = "enabled" if enabled else "disabled"
        desc = f"FFEmbed is {status} in this server."

        channels = await self.config.guild(ctx.guild).disabled_channels()
        channels = [ctx.guild.get_channel(channel) for channel in channels]
        if channels:
            channels = ", ".join([channel.mention for channel in channels])
        else:
            channels = "None"

        em = discord.Embed(description=desc, color=0x7289DA)
        em.add_field(name="Disabled in Channel(s)", value=channels)
        em.set_author(name="FFEmbed Config", icon_url=self.bot.user.avatar_url)
        await ctx.send(embed=em)

    @commands.guild_only()
    @toggle.command(name="server")
    async def toggle_server(self, ctx):
        """
        Enable or disable FFEmbed in this server
        """
        toggle = not await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(toggle)
        if toggle:
            await ctx.send("FFEmbed is now enabled in this server.")
        else:
            await ctx.send("FFEmbed is now disabled in this server.")

    @commands.guild_only()
    @toggle.command(name="channel")
    async def toggle_channel(self, ctx, channel: discord.TextChannel):
        """
        Enable or disable FFEmbed in a specific channel
        """
        if isinstance(channel, discord.TextChannel):
            channels = await self.config.guild(ctx.guild).disabled_channels()
            if channel.id in channels:
                channels.remove(channel.id)
                await self.config.guild(ctx.guild).disabled_channels.set(channels)
                await ctx.send(f"FFEmbed is now enabled in {channel.mention}.")
            else:
                channels.append(channel.id)
                await self.config.guild(ctx.guild).disabled_channels.set(channels)
                await ctx.send(f"FFEmbed is now disabled in {channel.mention}.")
        else:
            await ctx.send("Invalid channel. No changes were made.")

    def parse_url(self, message):
        url_regex = (
            "http[s]?://(?:www.)?(?:(?:m.)?fanfiction.net/s/\d+/\d+/"
            "(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),])+|"
            "archiveofourown.org/works/\d+(?:/chapters/\d+)?|"
            "siye.co.uk/siye/viewstory.php\?sid=\d+(?:&chapter=\d+)?)"
        )
        urls = re.findall(url_regex, message)
        return urls

    def fetch_url(self, url):
        resp = self.session.get(url, timeout=8)
        resp.encoding = "cp1252"
        page = BeautifulSoup(resp.text, "html.parser")
        return page

    def parse_FanFiction(self, page, url):
        base = "https://fanfiction.net/"
        div = page.find(id="profile_top")
        thumbnail = div.find("img", attrs={"class": "cimage"})
        author = div.find("a", attrs={"class": "xcontrast_txt"})
        title = div.find("b", attrs={"class": "xcontrast_txt"})
        desc = div.find("div", attrs={"class": "xcontrast_txt"})
        footer = div.find("span", attrs={"class": "xgray xcontrast_txt"})
        return {
            "link": url,
            "icon": "https://i.imgur.com/0eUBQHu.png",
            "thumbnail": "https:" + thumbnail["src"] if thumbnail else None,
            "author": author.get_text(),
            "author_link": base + author["href"],
            "title": title.get_text(),
            "desc": desc.get_text(),
            "footer": " ∙ ".join(footer.get_text().split("-")[:-1]),
        }

    def parse_AO3(self, page, url):
        base = "https://archiveofourown.org/"
        author = page.find("a", attrs={"rel": "author"})
        title = page.find("h2", attrs={"class": "title heading"})
        desc = page.find("blockquote", attrs={"class": "userstuff"})
        date = " ".join(x.get_text() for x in page.find_all(class_="published"))
        words = " ".join(x.get_text() for x in page.find_all(class_="words"))
        chapters = " ".join(x.get_text() for x in page.find_all(class_="chapters"))
        return {
            "link": url,
            "icon": "https://i.imgur.com/oJtk1Gp.png",
            "thumbnail": None,
            "author": author.get_text(),
            "author_link": base + author["href"],
            "title": title.get_text(),
            "desc": desc.get_text(),
            "footer": f"{date} ∙ {words} ∙ {chapters}",
        }

    def parse_SIYE(self, page, url):
        base = "http://siye.co.uk/"
        table_cell = page.find_all("td", attrs={"align": "left"})[1].get_text()
        rows = table_cell.strip().split("\n")
        author = page.find("font").next_sibling.next_sibling
        title = page.find("h3")
        desc = rows[6][9:]
        category = rows[0]
        characters = rows[1][:11] + " " + rows[1][11:]
        genres = rows[2]
        rating = rows[4]
        return {
            "link": url,
            "icon": "https://i.imgur.com/27czS4l.jpg",
            "thumbnail": None,
            "author": author.get_text(),
            "author_link": base + author["href"],
            "title": title.get_text(),
            "desc": desc,
            "footer": f"{category} ∙ {characters} ∙ {genres} ∙ {rating}",
        }

    def parse(self, page, url):
        if "fanfiction" in url:
            return self.parse_FanFiction(page, url)
        elif "archiveofourown" in url:
            return self.parse_AO3(page, url)
        elif "siye" in url:
            return self.parse_SIYE(page, url)

    def format_embed(self, metadata):
        em = discord.Embed(
            title=metadata["title"],
            url=metadata["link"],
            description=metadata["desc"],
            color=0x7289DA,
        )
        em.set_author(
            name=metadata["author"],
            url=metadata["author_link"],
            icon_url=metadata["icon"],
        )
        em.set_footer(text=metadata["footer"])
        if metadata["thumbnail"]:
            em.set_thumbnail(url=metadata["thumbnail"])
        return em

    @commands.Cog.listener()
    async def on_message(self, message):
        enabled = await self.config.guild(message.guild).enabled()
        disabled_channels = await self.config.guild(message.guild).disabled_channels()
        if not enabled or message.channel.id in disabled_channels:
            pass
        else:
            urls = self.parse_url(message.content)
            for url in urls:
                url = url.replace("//m.", "//")
                try:
                    page = self.fetch_url(url)
                    metadata = self.parse(page, url)
                    em = self.format_embed(metadata)
                    await message.channel.send(embed=em)
                except Exception as e:
                    print(e)
                    await message.channel.send("Failed to retrieve story.")
