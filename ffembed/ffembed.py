import aiohttp
import asyncio
import discord
import re

from bs4 import BeautifulSoup
from redbot.core import checks, commands, Config

__version__ = "1.1.4"

BaseCog = getattr(commands, "Cog", object)


class FFEmbed(BaseCog):
    """
    Show FanFiction, AO3, and SIYE story info in an embed message
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(
            self, identifier=77232917, force_registration=True
        )
        self.config.register_guild(enabled=True, disabled_channels=[])

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @checks.is_owner()
    @commands.guild_only()
    @commands.command(name="ffreset")
    async def reset(self, ctx):
        """
        Reset FFEmbed's config for this server
        """
        await ctx.send(
            "Are you sure you want to reset FFEmbed's config for "
            "this server? Type 'yes' to proceed."
        )
        try:
            await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.content.lower() == "yes",
                timeout=8,
            )
        except asyncio.TimeoutError:
            await ctx.send("No confirmation received. No changes were made.")
        else:
            await self.config.guild(ctx.guild).clear()
            await ctx.send("FFEmbed's config for this server has been reset.")

    @checks.is_owner()
    @commands.guild_only()
    @commands.group(name="fftoggle", invoke_without_command=True)
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
        em.add_field(name="Disabled In Channel(s)", value=channels)
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
            r"https?://(?:www.)?(?:(?:m.)?fanfiction.net/"
            r"(?:(?:(?:s|u)/\d+/?)|~)(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),])*|"
            r"archiveofourown.org/works/\d+(?:/chapters/\d+)?|"
            r"siye.co.uk/(?:siye/)?viewstory.php\?sid=\d+(?:&chapter=\d+)?)"
        )
        urls = re.findall(url_regex, message)
        for i, url in enumerate(urls):
            url = url.replace("//m.", "//")
            # Handle invalid certificate for SIYE
            url = url.replace("https", "http") if "siye" in url else url
            # Redirect FanFiction stories to chapter 1
            if re.search(r"fanfiction.net/s/\d+", url):
                sp = url.split("/")
                url = "/".join(sp[:5] + ["1"] + sp[6:])
            urls[i] = url
        return urls

    async def fetch_url(self, url):
        # AO3 presents warning page for NSFW-tagged stories
        if "archiveofourown" in url:
            url = url + "?view_adult=true"
        async with self.session.get(url, timeout=8) as r:
            html = await r.text()
            page = BeautifulSoup(html, "html.parser")
        if "archiveofourown" in url and page.select("p[class='message footnote']"):
            chapter = page.select("ul[class='actions']")[0].find("a")["href"]
            url = "https://archiveofourown.org" + chapter
            async with self.session.get(url, timeout=8) as r:
                html = await r.text()
                page = BeautifulSoup(html, "html.parser")
        return page

    def parse_FanFiction_author(self, page, url):
        div = page.find(id="content_wrapper_inner")
        thumbnail = div.find(id="bio").img
        author = div.span
        desc = page.find("meta", attrs={"name": "description"})["content"]
        footer = div.find_all("td", {"colspan": "2"})[2]
        footer = footer.get_text().replace("id", "ID")
        footer = footer[:6] + ":" + footer[6:]
        return {
            "link": None,
            "icon": "https://i.imgur.com/0eUBQHu.png",
            "thumbnail": "https:" + thumbnail["data-original"] if thumbnail else None,
            "author": author.get_text(strip=True),
            "author_link": url,
            "title": None,
            "desc": desc,
            "footer": " ∙ ".join(footer.split(", ")),
        }

    def parse_FanFiction(self, page, url):
        base = "https://fanfiction.net"
        div = page.find(id="profile_top")
        thumbnail = div.find("img", attrs={"class": "cimage"})
        author = div.find("a", attrs={"class": "xcontrast_txt"})
        title = div.find("b", attrs={"class": "xcontrast_txt"})
        desc = div.find("div", attrs={"class": "xcontrast_txt"})
        footer = div.find("span", attrs={"class": "xgray xcontrast_txt"})
        footer = ": ".join(x.strip() for x in footer.get_text().split(":"))
        return {
            "link": url,
            "icon": "https://i.imgur.com/0eUBQHu.png",
            "thumbnail": "https:" + thumbnail["src"] if thumbnail else None,
            "author": author.get_text(strip=True),
            "author_link": base + author["href"],
            "title": title.get_text(strip=True),
            "desc": desc.get_text(strip=True),
            "footer": " ∙ ".join(footer.split("-")[:-1]),
        }

    def parse_AO3(self, page, url):
        base = "https://archiveofourown.org"
        author = page.find("a", attrs={"rel": "author"})
        title = page.find("h2", attrs={"class": "title heading"})
        desc = page.find("div", attrs={"class": "summary module"})
        desc = "Summary not specified." if desc is None else desc.p.get_text(strip=True)
        date = " ".join(x.get_text() for x in page.find_all(class_="published"))
        status = " ".join(x.get_text() for x in page.find_all(class_="status"))
        chapters = " ".join(x.get_text() for x in page.find_all(class_="chapters"))
        words = f"Words: {int(page.find_all(class_='words')[1].get_text()):,}"
        kudos = f"Kudos: {int(page.find_all(class_='kudos')[1].get_text()):,}"
        hits = f"Hits: {int(page.find_all(class_='hits')[1].get_text()):,}"
        return {
            "link": url,
            "icon": "https://i.imgur.com/oJtk1Gp.png",
            "thumbnail": None,
            "author": author.get_text(strip=True),
            "author_link": base + author["href"],
            "title": title.get_text(strip=True),
            "desc": desc,
            "footer": f"{date} ∙ {status} ∙ {chapters} ∙ {words} ∙ {kudos} ∙ {hits}",
        }

    def parse_SIYE(self, page, url):
        base = "http://siye.co.uk"
        table_cell = page.find_all("td", attrs={"align": "left"})[1].get_text()
        rows = table_cell.strip().split("\n")
        rows = [row for row in rows if ":" in row]  # Handle completed story
        author = page.find("font").next_sibling.next_sibling
        title = page.find("h3")
        desc = rows[6][9:]
        category = rows[0]
        characters = rows[1][:11] + " " + rows[1][11:]
        genres = rows[2]
        rating = rows[4]
        return {
            "link": url,
            "icon": "https://i.imgur.com/TXRYIBN.jpg",
            "thumbnail": None,
            "author": author.get_text(strip=True),
            "author_link": base + "/" + author["href"],
            "title": title.get_text(strip=True),
            "desc": desc,
            "footer": f"{category} ∙ {characters} ∙ {genres} ∙ {rating}",
        }

    def parse(self, page, url):
        if "fanfiction" in url:
            if "/s/" in url:
                return self.parse_FanFiction(page, url)
            else:
                return self.parse_FanFiction_author(page, url)
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
        if (
            not message.guild
            or message.author.bot
            or message.content.startswith(
                tuple(await self.bot.db.guild(message.guild).prefix())
            )
        ):
            return
        else:
            enabled = await self.config.guild(message.guild).enabled()
            disabled_ch = await self.config.guild(message.guild).disabled_channels()

        if not enabled or message.channel.id in disabled_ch:
            pass
        else:
            urls = self.parse_url(message.content)
            for url in urls:
                try:
                    page = await self.fetch_url(url)
                    metadata = self.parse(page, url)
                except Exception as e:
                    print(e)
                    await message.channel.send("Failed to retrieve story.")
                else:
                    em = self.format_embed(metadata)
                    await message.channel.send(embed=em)
