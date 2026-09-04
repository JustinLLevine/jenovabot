
import asyncio
import json
import random

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image

from cogfiles.image_editing import temp_png
from ioutils import RandomColorEmbed

CARD_COUNT = 5
BOARD_SIZE = 3
COLUMN_X_COORDINATES = (517, 837, 1157)
COLUMN_Y_COORDINATES = (112, 433, 754)
IMAGE_DIRECTORY = "triple_triad"

class Card:
    """A card in Triple Triad."""
    
    def __init__(self, name: str, top: int, right: int, bottom: int, left: int):
        self.name = name
        self.top = top
        self.right = right
        self.bottom = bottom
        self.left = left
        self.level: int = 0
        self.color: str | None = "None"

    def set_level(self, level: int):
        """Set the card's level and apply +x to all stats, where x is the level."""
        old_level = self.level
        self.level = level
        for attr in ("top", "right", "bottom", "left"):
            setattr(self, attr, getattr(self, attr) + (level - old_level)) # Increase the card's stats based on its level

    def draw(self) -> str:
        """Create an image of this card, with player color and frame. Returns the name of the image file."""
        image = Image.open(f"{IMAGE_DIRECTORY}/card-{self.color}.png")
        card_image = Image.open(f"{IMAGE_DIRECTORY}/{self.name.lower()}.png")
        image.paste(card_image, (0, 0), card_image)

        top_rank_image = Image.open(f"{IMAGE_DIRECTORY}/rank-{self.top}.png")
        image.paste(top_rank_image, (33, 10), top_rank_image)
        right_rank_image = Image.open(f"{IMAGE_DIRECTORY}/rank-{self.right}.png")
        image.paste(right_rank_image, (56, 33), right_rank_image)
        bottom_rank_image = Image.open(f"{IMAGE_DIRECTORY}/rank-{self.bottom}.png")
        image.paste(bottom_rank_image, (33, 56), bottom_rank_image)
        left_rank_image = Image.open(f"{IMAGE_DIRECTORY}/rank-{self.left}.png")
        image.paste(left_rank_image, (10, 33), left_rank_image)

        frame = Image.open(f"{IMAGE_DIRECTORY}/frame-{self.level}.png")
        image.paste(frame, (0, 0), frame)

        with temp_png() as temp_file:
            image_name = temp_file.name
        image.save(image_name)
        return image_name

class Player:
    """A player in Triple Triad."""
    
    def __init__(self, member: discord.Member, cards: list[Card]):
        self.member = member
        self.cards: list[Card] = cards
        self.card_selected: Card | None = None
        self.space_selected: tuple[int, int] | None = None

class BoardSpace:
    """A space on the Triple Triad board."""
    
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.card: Card | None = None
        self.owner: Player | None = None

class TripleTriadGame:
    """A game of Triple Triad."""
    
    def __init__(self, player1: Player, player2: Player, board_image_filename: str, channel: discord.TextChannel):
        self.player1 = player1
        self.player2 = player2
        self.board_image_filename = board_image_filename
        self.channel = channel
        self.board: list[list[BoardSpace]] = [
            [BoardSpace(x, y) for y in range(BOARD_SIZE)]
            for x in range(BOARD_SIZE)
        ]
        self.current_player = random.choice([player1, player2])

    @staticmethod
    def deal_cards(color: str) -> list[Card]:
        """Deal 5 random cards to a player, giving all of them a specific color."""
        with open(f"{IMAGE_DIRECTORY}/cards.json", "r") as f:
            card_data = json.load(f)
        cards = []
        levels = [0, 0, 1, 2, 3]
        while levels:
            level = levels.pop(0)
            random_choice = random.choice(card_data)
            card_data.remove(random_choice)
            card = Card(**random_choice)
            card.set_level(level)
            card.color = color
            cards.append(card)
        return cards

    def try_flip_neighbors(self, x: int, y: int) -> str:
        """Check the neighbors of the card at (x, y) and flip them if the current player's card is stronger."""
        current_space = self.board[x][y]
        current_card = current_space.card
        if current_card is None:
            return
        neighbors = (
            (x, y - 1, current_card.top, "bottom"),
            (x + 1, y, current_card.right, "left"),
            (x, y + 1, current_card.bottom, "top"),
            (x - 1, y, current_card.left, "right"),
        )
        for neighbor_x, neighbor_y, attack, defense in neighbors:
            if not (0 <= neighbor_x < BOARD_SIZE and 0 <= neighbor_y < BOARD_SIZE):
                continue
            neighbor = self.board[neighbor_x][neighbor_y]
            if (neighbor.card and neighbor.owner != self.current_player and attack > getattr(neighbor.card, defense)):
                neighbor.owner = self.current_player
                neighbor.card.color = self.current_player.card_selected.color
                self.board_image_filename = self.draw_card_on_board(neighbor, neighbor_x, neighbor_y)

        return self.board_image_filename

    def draw_card_on_board(self, board_space: BoardSpace, row: int, col: int) -> str:
        """Draw a card on the board at the specified coordinates. First draw the card's background, then draw the card's character image, then draw the card's stats, then draw the card's frame."""
        x = COLUMN_X_COORDINATES[row]
        y = COLUMN_Y_COORDINATES[col]
        
        board_image = Image.open(self.board_image_filename)
        card_image = Image.open(board_space.card.draw())
        board_image.paste(card_image, (x, y), card_image)

        with temp_png() as temp_file:
            image_name = temp_file.name
        board_image.save(image_name)
        self.board_image_filename = image_name
        return image_name

    async def move_to_next_turn(self):
        """End the current player's turn and switch to the other player."""
        x = self.current_player.space_selected[0]
        y = self.current_player.space_selected[1]
        self.board[x][y].card = self.current_player.card_selected
        self.board[x][y].owner = self.current_player
        self.draw_card_on_board(self.board[x][y], x, y)
        self.try_flip_neighbors(x, y)
        self.current_player.cards.remove(self.current_player.card_selected)
        if self.current_player.cards:
            self.current_player.card_selected = None
            self.current_player.space_selected = None
            self.current_player = self.player1 if self.current_player == self.player2 else self.player2
            await self.channel.send(self.current_player.member.mention, file=discord.File(self.board_image_filename), view=TripleTriadView(self))
        else:
            await self.end_game()

    async def end_game(self):
        """End the game and declare a winner."""
        player1_score = sum(1 for row in self.board for space in row if space.owner == self.player1)
        player1_score += sum(1 for _ in self.player1.cards)
        player2_score = sum(1 for row in self.board for space in row if space.owner == self.player2)
        player2_score += sum(1 for _ in self.player2.cards)
        if player1_score > player2_score:
            winner = self.player1
        elif player2_score > player1_score:
            winner = self.player2
        else:
            await self.channel.send(f"**It's a tie! {player1_score} - {player2_score}**", file=discord.File(self.board_image_filename))
            return
        await self.channel.send(f"**{winner.member.mention} wins {max(player1_score, player2_score)} - {min(player1_score, player2_score)}!**", file=discord.File(self.board_image_filename))

class ChallengeView(discord.ui.View):

    def __init__(self, bot, user: discord.Member, opponent: discord.Member, message: discord.Message):
        self.bot = bot
        self.user = user
        self.opponent = opponent
        self.message = message
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.opponent:
            return await interaction.response.send_message("You are not the challenged player.", ephemeral=True, delete_after=5)
        await interaction.response.defer()
        self.stop()
        await self.bot.get_cog("tripletriad").start_game(interaction, self.user, self.opponent)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.opponent:
            return await interaction.response.send_message("You are not the challenged player.", ephemeral=True, delete_after=5)
        await interaction.response.defer()
        self.stop()
        await self.message.delete()
        await interaction.response.send_message(f"{self.opponent.mention} has declined the challenge from {self.user.mention}.")

class TripleTriadView(discord.ui.View):
    def __init__(self, game: TripleTriadGame):
        self.game = game
        super().__init__(timeout=None)

    @discord.ui.button(label="Choose a card", style=discord.ButtonStyle.blurple, emoji="<:triple_triad:1541294408430002306>")
    async def deal_cards(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in (self.game.player1.member, self.game.player2.member):
            return await interaction.response.send_message("You are not a player in this game.", ephemeral=True, delete_after=5)
        player = self.game.player1 if interaction.user == self.game.player1.member else self.game.player2
        card_images = [discord.File(card.draw()) for card in player.cards]
        await interaction.response.send_message(view=CardHandView(self.game, player, interaction), files=card_images, ephemeral=True)

    @discord.ui.button(label="Choose a space", style=discord.ButtonStyle.blurple, emoji="<:triple_triad:1541294408430002306>")
    async def select_space(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in (self.game.player1.member, self.game.player2.member):
            return await interaction.response.send_message("You are not a player in this game.", ephemeral=True, delete_after=5)
        player = self.game.player1 if interaction.user == self.game.player1.member else self.game.player2
        await interaction.response.send_message(view=BoardSpacesView(self.game, player, interaction), ephemeral=True)


class CardButton(discord.ui.Button):
    def __init__(self, card: Card, game: TripleTriadGame):
        self.card = card
        self.game = game
        super().__init__(label=f"{card.name} ↑{card.top} →{card.right} ↓{card.bottom} ←{card.left}", style=discord.ButtonStyle.blurple if card.color == "blue" else discord.ButtonStyle.red, emoji="<:triple_triad:1541294408430002306>")

    async def callback(self, interaction: discord.Interaction):
        player = self.game.player1 if interaction.user == self.game.player1.member else self.game.player2
        if player != self.game.current_player:
            await interaction.response.send_message("It's not your turn.", ephemeral=True, delete_after=5)
            return
        if self.card not in player.cards:
            await interaction.response.send_message("You don't have that card.", ephemeral=True, delete_after=5)
            return
        player.card_selected = self.card
        await interaction.response.send_message("👍", ephemeral=True, delete_after=1)
        await self.view.interaction.delete_original_response()
        if player.card_selected and player.space_selected:
            await self.game.move_to_next_turn()

class CardHandView(discord.ui.View):
    def __init__(self, game: TripleTriadGame, player: Player, interaction: discord.Interaction):
        self.game = game
        self.player = player
        self.interaction = interaction
        super().__init__(timeout=None)
        for card in player.cards:
            self.add_item(CardButton(card, game))

class BoardSpaceButton(discord.ui.Button):
    def __init__(self, x: int, y: int, game: TripleTriadGame):
        self.x = x
        self.y = y
        self.game = game
        card_at_space = game.board[x][y].card
        style = discord.ButtonStyle.gray if card_at_space is None else (discord.ButtonStyle.blurple if card_at_space.color == "blue" else discord.ButtonStyle.red)
        super().__init__(disabled = card_at_space is not None, style=style, emoji="<:triple_triad:1541294408430002306>", row=y)

    async def callback(self, interaction: discord.Interaction):
        player = self.game.player1 if interaction.user == self.game.player1.member else self.game.player2
        if player != self.game.current_player:
            await interaction.response.send_message("It's not your turn.", ephemeral=True, delete_after=5)
            return
        card_at_space = self.game.board[self.x][self.y].card
        if card_at_space:
            await interaction.response.send_message("That space is already occupied.", ephemeral=True,  delete_after=5)
            return

        player.space_selected = (self.x, self.y)
        await interaction.response.send_message("👍", ephemeral=True, delete_after=1)
        await self.view.interaction.delete_original_response()
        if player.card_selected and player.space_selected:
            await self.game.move_to_next_turn()

class BoardSpacesView(discord.ui.View):
    def __init__(self, game: TripleTriadGame, player: Player, interaction: discord.Interaction):
        self.game = game
        self.player = player
        self.interaction = interaction
        super().__init__(timeout=None)
        for x in range(3):
            for y in range(3):
                self.add_item(BoardSpaceButton(x, y, game))

class TripleTriad(commands.GroupCog, name="tripletriad"):
    """A game of Triple Triad."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(app_commands.ContextMenu(name="Wanna play cards?", callback=self.send_challenge)) # You can't use @app_commands.context_menu() in a cog

    @app_commands.command()
    @app_commands.guild_only()
    async def challenge(self, interaction: discord.Interaction, opponent: discord.Member):
        """Challenge another player to a game of Triple Triad."""
        await self.send_challenge(interaction, opponent)

    async def send_challenge(self, interaction: discord.Interaction, opponent: discord.Member):
        """Challenge another player to a game of Triple Triad."""
        embed = RandomColorEmbed(title="Triple Triad Challenge", description=f"{interaction.user.mention} has challenged {opponent.mention} to a game of Triple Triad!")
        view = ChallengeView(self.bot, interaction.user, opponent, None)
        message = await interaction.response.send_message(content=opponent.mention, embed=embed, view=view)
        view.message = message.resource

    @app_commands.command()
    async def card(self, interaction: discord.Interaction, name: str):
        """View an image of a card."""
        with open(f"{IMAGE_DIRECTORY}/cards.json", "r") as f:
            card_data = json.load(f)
        card = next((Card(**card) for card in card_data if card["name"].lower() == name.lower()), None)
        if not card:
            await interaction.response.send_message("Unable to find a card with this name.", ephemeral=True)
            return
        card.color = "gray"

        files = []
        for i in range(4):
            card.set_level(i)
            files.append(discord.File(card.draw()))
        await interaction.response.send_message(files=files)

    async def start_game(self, interaction: discord.Interaction, player1: discord.Member, player2: discord.Member):
        """Start a game of Triple Triad between two players."""
        image_file = discord.File(f"{IMAGE_DIRECTORY}/board-mat.jpg", filename="board.png")
        game = TripleTriadGame(Player(player1, TripleTriadGame.deal_cards("red")), Player(player2, TripleTriadGame.deal_cards("blue")), f"{IMAGE_DIRECTORY}/board-mat.jpg", interaction.channel)
        view = TripleTriadView(game)
        await interaction.channel.send(f"🎲 **And the first player is...**")
        await asyncio.sleep(1)
        await interaction.channel.send(content=game.current_player.member.mention, file=image_file, view=view)