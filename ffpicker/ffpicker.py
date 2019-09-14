import asyncio
import discord
import re
import requests

from bs4 import BeautifulSoup
from redbot.core import checks, commands, Config
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS


__version__ = "1.0"

BaseCog = getattr(commands, "Cog", object)


class FFPicker(BaseCog):
    """
    Allow saving and retrieval of FanFiction, AO3, and SIYE stories
    to and from a curated collection
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = requests.Session()
        self.config = Config.get_conf(
            self, identifier=482071529, force_registration=True
        )
        self.config.register_guild(stories=[])

    @commands.guild_only()
    @commands.group(name="ffpicker", invoke_without_command=True)
    async def picker(self, ctx, page_num: int = 1):
        """
        Show the curated collection of stories in this server
        """
        listing = ""
        stories = await self.config.guild(ctx.guild).stories()
        if not stories:
            await ctx.send("There are no stories to show, add some!")
            return
        for idx, story in enumerate(stories, 1):
            listing += (
                f"**{idx}** [{story['title']}]({story['link']}) "
                f"by {story['author']}\n"
            )
            if idx % 2 == 0:
                listing += "\n"

        embeds = []
        pages = listing.strip().split("\n\n")
        for idx, page in enumerate(pages, 1):
            em = discord.Embed(description=page, color=0x7289DA)
            em.set_author(
                name=f"{ctx.guild.name}'s Story Collection", icon_url=ctx.guild.icon_url
            )
            em.set_footer(
                text=f"Page {idx} of {len(pages)} • Total stories: {len(stories)}"
            )
            embeds.append(em)

        await menu(ctx, embeds, DEFAULT_CONTROLS, page=page_num - 1)

    @commands.guild_only()
    @picker.command()
    @checks.is_owner()
    async def reset(self, ctx):
        """
        Reset the story collection of this server
        """
        await ctx.send(
            "Are you sure you want to remove all the stories collected "
            "in this server? Type 'yes' to proceed."
        )
        try:
            msg = await self.bot.wait_for(
                "message", check=lambda m: m.content.lower() == "yes", timeout=8
            )
        except asyncio.TimeoutError:
            await ctx.send("No confirmation received. No changes were made.")
        else:
            await self.config.guild(ctx.guild).clear()
            await ctx.send("All the stories have been removed.")

    def parse_url(self, message):
        url_regex = (
            "http[s]?://(?:www.)?(?:(?:m.)?fanfiction.net/s/\d+/\d+/"
            "(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),])+|"
            "archiveofourown.org/works/\d+(?:/chapters/\d+)?|"
            "siye.co.uk/(?:siye/)?viewstory.php\?sid=\d+(?:&chapter=\d+)?)"
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

    @commands.guild_only()
    @picker.command(name="add")
    async def addfic(self, ctx, url):
        """
        Add a story to the collection
        """
        url = self.parse_url(url)
        if not url:
            await ctx.send("Invalid link. No story added.")
            return

        try:
            url = url[0]
            page = self.fetch_url(url)
            metadata = self.parse(page, url)
        except Exception as e:
            print(e)
            await ctx.send("Failed to retrieve and add story.")
        else:
            guild_conf = self.config.guild(ctx.guild)
            if any(
                story["title"] == metadata["title"]
                and story["author"] == metadata["author"]
                for story in await guild_conf.stories()
            ):
                await ctx.send(
                    "That story already exists in the collection. "
                    "Duplicate stories will not be added."
                )
            else:
                async with guild_conf.stories() as stories:
                    story = {
                        "title": metadata["title"],
                        "author": metadata["author"],
                        "link": metadata["link"],
                        "user_id": ctx.author.id,
                    }
                    stories.append(story)
                    stories_len = len(stories)
                msg = (
                    f"**{metadata['title']}** by **{metadata['author']}** "
                    f"has been added to the collection as story #{stories_len}."
                )
                em = self.format_embed(metadata)
                await ctx.send(msg, embed=em)

    @commands.guild_only()
    @picker.command(name="remove")
    async def removefic(self, ctx, num: int):
        """
        Remove a story from the collection by its index number
        """
        guild_conf = self.config.guild(ctx.guild)
        async with guild_conf.stories() as stories:
            if abs(num) > len(stories) or num == 0:
                await ctx.send("Invalid index number. No story removed.")
                return
            elif num < 0:
                idx = len(stories) - num - 1
            else:
                idx = num - 1

            story = stories.pop(idx)
            user = ctx.guild.get_member(story["user_id"])
            user = "Unknown Member" if not user else user.display_name
            await ctx.send(
                f"**{story['title']}** by **{story['author']}** "
                f"(story #{idx+1} added by {user}) has been removed."
            )

    @commands.guild_only()
    @picker.command(name="show")
    async def showfic(self, ctx, num: int):
        """
        Show a story from the collection by its index number
        """
        stories = await self.config.guild(ctx.guild).stories()
        if abs(num) > len(stories) or num == 0:
            await ctx.send(
                f"Please keep the index number between 1 and {len(stories)}."
            )
            return
        elif num < 0:
            idx = len(stories) - num - 1
        else:
            idx = num - 1

        story = stories[idx]
        url = story["link"]
        try:
            page = self.fetch_url(url)
            metadata = self.parse(page, url)
        except Exception as e:
            print(e)
            await ctx.send(f"Failed to retrieve and show story #{idx+1}.")
        else:
            user = ctx.guild.get_member(story["user_id"])
            user = "Unknown Member" if not user else user.display_name
            msg = f"Showing story #{idx+1} added by {user}."
            em = self.format_embed(metadata)
            await ctx.send(msg, embed=em)
