
import asyncio
import copy
import random

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from cogfiles.image_editing import temp_png
from ioutils import RandomColorEmbed

CARD_COUNT = 5
BOARD_SIZE = 3
COLUMN_X_COORDINATES = (517, 837, 1157)
COLUMN_Y_COORDINATES = (112, 433, 754)


class Card:
    """A card in Triple Triad."""
    
    def __init__(self, name: str, background: Image.Image, top: int, right: int, bottom: int, left: int):
        self.name = name
        self.background = background
        self.top = top
        self.right = right
        self.bottom = bottom
        self.left = left
        self.color = "None"

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
        #with open("card_data.json", "r") as f:
        #    card_data = json.load(f)
        card_data = [Card("Satoko", Image.open("image_resources/satoko.png"), 1, 2, 3, 4)]
        cards = []
        for _ in range(CARD_COUNT):
            # Each dealt card needs its own color state. Reusing the template would mutate the shared card whenever another player is dealt it
            card = copy.copy(random.choice(card_data))
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
        player_color_image = Image.open(f"image_resources/card-{board_space.card.color}.png")
        board_image = Image.open(self.board_image_filename)
        board_image.paste(player_color_image, (x, y), player_color_image)
        board_image.paste(board_space.card.background, (x, y), board_space.card.background)
        draw = ImageDraw.Draw(board_image)
        draw.font = ImageFont.truetype("image_resources/sazanami-gothic.ttf", 28)
        draw.text((x + 30, y + 10), str(board_space.card.top), fill=(0, 0, 0))
        draw.text((x + 50, y + 30), str(board_space.card.right), fill=(0, 0, 0))
        draw.text((x + 30, y + 50), str(board_space.card.bottom), fill=(0, 0, 0))
        draw.text((x + 10, y + 30), str(board_space.card.left), fill=(0, 0, 0))
        frame = Image.open("image_resources/frame-4-character.png")
        board_image.paste(frame, (x, y), frame)
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
        player2_score = sum(1 for row in self.board for space in row if space.owner == self.player2)
        if player1_score > player2_score:
            winner = self.player1
        elif player2_score > player1_score:
            winner = self.player2
        else:
            await self.channel.send(f"The game is a tie! Both players have {player1_score} cards on the board.", file=discord.File(self.board_image_filename))
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
            return await interaction.response.send_message("You are not the challenged player.", ephemeral=True)
        await interaction.response.defer()
        self.stop()
        await self.message.delete()
        await self.bot.get_cog("tripletriad").start_game(interaction, self.user, self.opponent)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.opponent:
            return await interaction.response.send_message("You are not the challenged player.", ephemeral=True)
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
            return await interaction.response.send_message("You are not a player in this game.", ephemeral=True)
        player = self.game.player1 if interaction.user == self.game.player1.member else self.game.player2
        await interaction.response.send_message(view=CardHandView(self.game, player), ephemeral=True)

    @discord.ui.button(label="Choose a space", style=discord.ButtonStyle.blurple, emoji="<:triple_triad:1541294408430002306>")
    async def select_space(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in (self.game.player1.member, self.game.player2.member):
            return await interaction.response.send_message("You are not a player in this game.", ephemeral=True)
        player = self.game.player1 if interaction.user == self.game.player1.member else self.game.player2
        await interaction.response.send_message(view=BoardSpacesView(self.game, player), ephemeral=True)

class CardButton(discord.ui.Button):
    def __init__(self, card: Card, game: TripleTriadGame):
        self.card = card
        self.game = game
        super().__init__(label=f"{card.name} ↑{card.top} →{card.right} ↓{card.bottom} ←{card.left}", style=discord.ButtonStyle.blurple if card.color == "blue" else discord.ButtonStyle.red, emoji="<:triple_triad:1541294408430002306>")

    async def callback(self, interaction: discord.Interaction):
        player = self.game.player1 if interaction.user == self.game.player1.member else self.game.player2
        if player != self.game.current_player:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return
        player.card_selected = self.card
        await interaction.response.send_message("👍", ephemeral=True, delete_after=2)
        if player.card_selected and player.space_selected:
            await self.game.move_to_next_turn()

class CardHandView(discord.ui.View):
    def __init__(self, game: TripleTriadGame, player: Player):
        self.game = game
        self.player = player
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
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return
        player.space_selected = (self.x, self.y)
        await interaction.response.send_message("👍", ephemeral=True, delete_after=2)
        if player.card_selected and player.space_selected:
            await self.game.move_to_next_turn()

class BoardSpacesView(discord.ui.View):
    def __init__(self, game: TripleTriadGame, player: Player):
        self.game = game
        self.player = player
        super().__init__(timeout=None)
        for x in range(3):
            for y in range(3):
                self.add_item(BoardSpaceButton(x, y, game))

class TripleTriad(commands.GroupCog, name="tripletriad"):
    """A game of Triple Triad."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command()
    @app_commands.guild_only()
    async def challenge(self, interaction: discord.Interaction, opponent: discord.Member):
        """Challenge another player to a game of Triple Triad."""
        embed = RandomColorEmbed(title="Triple Triad Challenge", description=f"{interaction.user.mention} has challenged {opponent.mention} to a game of Triple Triad!")
        view = ChallengeView(self.bot, interaction.user, opponent, None)
        message = await interaction.response.send_message(content=opponent.mention, embed=embed, view=view)
        view.message = message.resource

    async def start_game(self, interaction: discord.Interaction, player1: discord.Member, player2: discord.Member):
        """Start a game of Triple Triad between two players."""
        image_file = discord.File("image_resources/board-mat.jpg", filename="board.png")
        game = TripleTriadGame(Player(player1, TripleTriadGame.deal_cards("red")), Player(player2, TripleTriadGame.deal_cards("blue")), "image_resources/board-mat.jpg", interaction.channel)
        view = TripleTriadView(game)
        await interaction.channel.send(f"🎲 **And the first player is...**", file=image_file)
        await asyncio.sleep(1)
        await interaction.channel.send(content=game.current_player.member.mention, view=view)