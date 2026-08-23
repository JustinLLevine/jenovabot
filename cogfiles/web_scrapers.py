import aiohttp
import base64
import discord
import json
import os
import re

from bs4 import BeautifulSoup
from dateutil import parser
from ioutils import RandomColorEmbed
from howlongtobeatpy import HowLongToBeat
from thefuzz import process

from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt
from enum import Enum


ITAD_API_KEY = os.getenv("ITAD_API_KEY")
EBAY_APP_NAME = os.getenv("EBAY_APP_NAME")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID")


class AnilistSearchType(Enum):
    Anime = 1
    Manga = 2
    Both = 3

class WebScrapers(commands.Cog, name="Web Scrapers"):
    """Grab data from various websites and send it."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command()
    @app_commands.rename(game_name="search")
    async def howlongtobeat(self, interaction: discord.Interaction, game_name: str):
        """Search HowLongToBeat (HLTB) with the given game name and show completion time info."""
        
        game_list = await WebScrapers.hltb_search(game_name)
        if game_list is None:
            return await interaction.response.send_message("Could not find a game with that title.", ephemeral=True)
        
        game = game_list[0]

        game_data = RandomColorEmbed(title=game.game_name, url=game.game_web_link)
        game_data.set_thumbnail(url=game.game_image_url)
        
        if game.main_story != 0:
            game_data.add_field(name="Main Story", value=f"{game.main_story} Hours", inline=False)
        if game.main_extra != 0:
            game_data.add_field(name="Main + Extra", value=f"{game.main_extra} Hours", inline=False)
        if game.completionist != 0:
            game_data.add_field(name="Completionist", value=f"{game.completionist} Hours", inline=False)

        await interaction.response.send_message(embed=game_data)
        
    #@app_commands.command()
    #@app_commands.rename(game_name="search")
    #async def howlongtobeatlist(self, interaction: discord.Interaction, game_name: str):
    #    """Search HowLongToBeat with the given game name and show at most the first 10 results."""
    #    game_list = await WebScrapers.hltb_search(game_name)
    #    if game_list is None:
    #        await interaction.response.send_message("Could not find a game with that title.", ephemeral=True)
    #        return
        
    #    game_list_data = RandomColorEmbed(
    #        title=f"HowLongToBeat Search: {game_name!r}",
    #        description='\n'.join([f"{i+1}. [{game.game_name}]({game.game_web_link})" for i, game in enumerate(game_list[:10])])
    #    )
    #    game_list_data.set_thumbnail(url="https://howlongtobeat.com/img/hltb_brand.png")

    #    await interaction.response.send_message(embed=game_list_data)

    @staticmethod
    async def hltb_search(game_name: str):
        """Search HowLongToBeat with the given game name. Returns the full list of results, sorted by similarity to the given name."""
        results_list = await HowLongToBeat().async_search(game_name, similarity_case_sensitive=False)
        if results_list is None or len(results_list) == 0:
            return None
        
        return sorted(results_list, key=lambda element: element.similarity, reverse=True)

    @app_commands.command()
    @app_commands.rename(song_name="search")
    async def heady(self, interaction: discord.Interaction, song_name: str):
        """Search HeadyVersion with the given song name."""
        await interaction.response.defer()

        async with aiohttp.ClientSession() as session:
            # First, perform a GET request to get the CSRF token
            async with session.get("http://headyversion.com/search/") as response:
                token = response.cookies["csrftoken"].value
            # Then, perform a POST request with the title and CSRF token to search HeadyVersion
            async with session.post("http://headyversion.com/search/", data={"title": song_name, "csrfmiddlewaretoken": token}) as response:
                content = await response.read()
                soup = BeautifulSoup(content, "html.parser")

                if str(response.url) == "http://headyversion.com/search/":
                    table = soup.find("table")
                    # If table is None, we know that no results were found
                    if table is None:
                        return await interaction.followup.send("Could not find a song with that title.")
                    # If the HTML has a table, then Heady is listing multiple song choices, and we choose the first one
                    else:
                        songs = table.find_all("div", class_="big_link")
                        song_link = songs[0].find("a").get("href")
                        async with session.get(f"http://headyversion.com{song_link}") as response:
                            content = await response.read()
                            soup = BeautifulSoup(content, "html.parser")

        # This regex is how Heady lists its webpage titles. Extract the name of the song from this webpage title and add it to our embed title
        song_title = re.search(r"Grateful Dead best (.+) \| headyversion", soup.find("title").string).group(1)
        title = f"HeadyVersion: {song_title}"
        description = ""
        # Find the first 5 shows in Heady's list of show dates, and add each one to the description for the embed
        for show in list(soup.find_all("div", class_="row s2s_submission bottom_border"))[:5]:
            votes = re.search(r"(\d+)", show.find("div", class_="score").string).group(1)
                    
            # Extract all the details from the show, and retrieve the date, Heady link, and archive.org link from the details
            show_details = show.find("div", class_="show_details_info")
            show_date = show_details.find("div", class_="show_date")
            show_heady_link = f"http://headyversion.com{show_details.find('a').get('href')}"
            show_archive_link = f"http://headyversion.com{show.find('div', class_='show_links').find('a', target='_blank').get('href')}"

            for stripped_show_date in show_date.stripped_strings:
                field_name = f"**{stripped_show_date}** \n{votes} votes"
                field_value = f"[HeadyVersion Link]({show_heady_link}) | [Archive.org Link]({show_archive_link})\n\n"
                description += f"{field_name}\n {field_value}"

        embed = RandomColorEmbed(title=title, url=response.url, description=description)
        embed.set_thumbnail(url="https://clipartspub.com/images/grateful-dead-clipart-template-5.png")
        await interaction.followup.send(embed=embed)

    @app_commands.command()
    async def anilist(self, interaction: discord.Interaction, search: str, type: AnilistSearchType | None):
        """Search AniList for an anime and/or manga with a title matching the provided search."""
        url = "https://graphql.anilist.co"
        # Here we define our query as a multi-line string
        type_str = ", type: ANIME" if type == AnilistSearchType.Anime else ", type: MANGA" if type == AnilistSearchType.Manga else ""
        query = """
        query ($search: String) {
            Media (search: $search%s) {
                siteUrl
            }
        }""" % (type_str)

        # Define our query variables and values that will be used in the query request
        variables = {
            "search": search
        }

        # Make the API request
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"query": query, "variables": variables}) as response:
                response_text = await response.text()
        response_json = json.loads(response_text)
        media = response_json["data"]["Media"]
        if media is None:
            await interaction.response.send_message("Could not find an anime/manga with that name.", ephemeral=True)
        else:
            await interaction.response.send_message(media["siteUrl"])

    @app_commands.command()
    @app_commands.rename(vn_name="search")
    async def vndb(self, interaction: discord.Interaction, vn_name: str):
        """Search VNDB for a visual novel matching the provided search."""
        vn_request_data = f"""{{
            "filters": ["search", "=", "{vn_name}"],
            "fields": "id, title, image.url, image.sexual, image.violence, length_minutes, description, developers.name"
        }}"""

        async with aiohttp.ClientSession(headers={'Content-Type': 'application/json'}) as session:
            async with session.post("https://api.vndb.org/kana/vn", data=vn_request_data) as response:
                results = (await response.json())["results"]
            
        if not results:
            return await interaction.response.send_message("Could not find a VN with that title.", ephemeral=True)

        vn, _ = process.extractOne(vn_name, results, processor=lambda vn: vn if vn == vn_name else vn["title"])

        if vn["description"] is None:
            vn["description"] = ""

        vn["description"] = re.sub(r"\[url=(\/.*?)\](.*?)\[\/url\]", r"[\2](http://vndb.org\1)", vn["description"]) # Changes internal URL tags to match Discord's formatting
        vn["description"] = re.sub(r"\[url=(.*?)\](.*?)\[\/url\]", r"[\2](\1)", vn["description"]) # Changes external URL tags to match Discord's formatting
        vn["description"] = vn["description"].replace("[i]", "*").replace("[\i]", "*") # Changes italics tags to match Discord's formatting
        vn["description"] = vn["description"].replace("[spoiler]", "||").replace("[\spoiler]", "||") # Changes spoiler tags to match Discord's formatting
        vn["description"] = WebScrapers.shorten(vn["description"], width=500, placeholder="[...]")
        if vn["description"].count("[i]") != vn["description"].count("[\i]"): # If true, then we have an unclosed italic tag
            vn["description"] += " [\i]"
        if vn["description"].count("||") % 2 != 0: # If odd number of spoiler markers, then we have an unclosed spoiler tag
            vn["description"] += " ||"

        developers = ", ".join(developer["name"] for developer in vn["developers"])
        length_hours = "Unknown" if vn["length_minutes"] is None else f"{float(vn['length_minutes'] / 60):.2f} hours"
        description = f"**Developed by: {developers}**\n**Average completion time: {length_hours}**\n\n{vn['description']}"
        vn_data = RandomColorEmbed(title=vn["title"], url=f"https://vndb.org/{vn['id']}", description=description)
        if vn["image"]["sexual"] < 2 and vn["image"]["violence"] < 2:
            vn_data.set_thumbnail(url=vn["image"]["url"])
        
        await interaction.response.send_message(embed=vn_data)

    @app_commands.command()
    async def isthereanydeal(self, interaction: discord.Interaction, search: str):
        """Search IsThereAnyDeal (ITAD) for a game matching the provided search.
        This command retrives the first 5 results of a search on ITAD. 
        For each result, prints the name of the game, the sale percent and new price, and the store with that price."""
        async with aiohttp.ClientSession() as session:
            api = f"https://api.isthereanydeal.com/games/search/v1?key={ITAD_API_KEY}&title={search}"
            async with session.get(api) as response:

                content = await response.read()
                content = json.loads(content)

                if response.status != 200 or len(content) == 0:
                    content = None

        if content is None:
            return await interaction.response.send_message("Could not find a game with that title.", ephemeral=True)

        await interaction.response.defer()

        description = ""

        valid_games = 0
        for i in range(len(content)):
            game_id = content[i]["id"]
            game_title = content[i]["title"]

            game_slug = content[i]["slug"]
            itad_url = f"https://isthereanydeal.com/game/{game_slug}"
            
            request_data = f"""{json.dumps([game_id])}"""
            api = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}"
            async with aiohttp.ClientSession() as session:
                async with session.post(api, data=request_data) as response:
                    price_content = await response.read()
                    price_content = json.loads(price_content)

            # Some entries in the list of results are not being sold on any stores.
            # Trying to find the price of these games results in an IndexError.
            # To avoid displaying these entries, skip over them if an IndexError occurs.
            # Once 5 valid entries have been found and added to the description, we are done.
            try:
                game_deals = price_content[0]["deals"][0]
                price_cut = game_deals["cut"]
                price_new = f"{float(game_deals['price']['amount']):.2f}"
                store_name = game_deals["shop"]["name"]
                game_url = game_deals["url"]
                    
                description += f"**[{game_title}]({itad_url})**\n**${price_new}** ({price_cut}% Off)\n[{store_name}]({game_url})\n\n"

                valid_games += 1
                if valid_games >= 5:
                    break

            except IndexError:
                continue

        embed = RandomColorEmbed(title="Is There Any Deal?", description=description)
        embed.set_thumbnail(url="https://i.imgur.com/kd2JUwX.png")
        await interaction.followup.send(embed=embed)

    @app_commands.command()
    async def ebay(self, interaction: discord.Interaction, search: str):
        """Search eBay for listings matching the provided search.
        This command retrives the first 5 results of a search on eBay."""
        async with aiohttp.ClientSession() as session:
            # Generate fresh OAuth token
            api = "https://api.ebay.com/identity/v1/oauth2/token"
            basic_auth = base64.b64encode(f"{EBAY_APP_NAME}:{EBAY_CERT_ID}".encode()).decode()
            headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {basic_auth}"}
            data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
            async with session.post(api, data=data, headers=headers) as response:
                content = await response.read()
                content = json.loads(content)
                access_token = content["access_token"]

            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"} 
            api = f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={search}&limit=5&filter=buyingOptions:{{AUCTION|FIXED_PRICE}}"
            async with session.get(api, headers=headers) as response:
                content = await response.read()
                content = json.loads(content)

        items = content["itemSummaries"]
        if len(items) == 0:
            return await interaction.response.send_message("Could not find any search results.", ephemeral=True)

        embed = RandomColorEmbed(title=f"eBay: {search}")
        embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/EBay_logo.svg/960px-EBay_logo.svg.png")

        description = ""
        # Iterate through the first 5 results, and extract information about each. 
        for item in items[:5]:
            title = item["title"]
            url = item["itemWebUrl"]
                    
            # Each listing is an auction and/or fixed price. Display the correct price.
            listing_types = item["buyingOptions"]
            price_info = []
            end_time_info = ""
            if "AUCTION" in listing_types:
                price = f"{float(item['currentBidPrice']['value']):.2f}"
                price_info.append(f"Current Bid: ${price}")
                end_time_info = f"\nEnds {format_dt(parser.parse(item['itemEndDate']), style ='R')}"
            if "FIXED_PRICE" in listing_types:
                price = f"{float(item['price']['value']):.2f}"
                price_info.append(f"Buy It Now: ${price}")
            price_info = " | ".join(price_info)

            description += f"**[{title}]({url})**\n{price_info}{end_time_info}\n\n"

        embed.description = description

        await interaction.response.send_message(embed=embed)

    @staticmethod
    def shorten(text: str, width: int, placeholder: str = "[...]") -> str:
        """Collapse and truncate the given text to fit in the given width.

        Unlike textwrap.shorten, this function will preserve line breaks."""
        if len(text) <= width:
            return text
        placeholder = " " + placeholder
        while len(text) + len(placeholder) > width:
            text = " ".join(text[:width].split(" ")[:-1])
        text += placeholder
        return text