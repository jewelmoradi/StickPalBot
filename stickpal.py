import logging
import os

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputSticker,
    Sticker,
    Update,
)

from telegram.error import (
    BadRequest,
    TelegramError,
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

# load environment variables
load_dotenv()  # loads the token from .env
TOKEN = os.getenv("BOT_TOKEN")

# global settings
PACK_TITLE = "My Favorite Stickers ✨"
FALLBACK_EMOJI = "🌟"

# logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_sticker_format(sticker: Sticker) -> str:
    """Return Telegram's format name for a sticker"""

    if sticker.is_animated:
        return "animated"

    if sticker.is_video:
        return "video"

    return "static"


def get_pack_name(bot_username: str) -> str:
    """Create the unique Telegram sticker-set short name."""

    username = bot_username.removeprefix("@").lower()
    return f"favs_by_{username}"


def get_pack_title() -> str:  # to be updated in the next versions
    """Create the human-readable sticker-set title."""

    return PACK_TITLE


async def pack_exists(context: ContextTypes.DEFAULT_TYPE, pack_name: str) -> bool:
    """Check if a sticker pack already exists."""

    try:
        await context.bot.get_sticker_set(pack_name)
        return True

    except BadRequest as error:
        if "STICKERSET_INVALID" in str(error).upper():
            return False

        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Hi! 👋\n\n"
            "Send me a sticker and I'll add it to your StickPal favorites!"
        )


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create the favorites pack if needed and add the sticker."""

    if not update.message or not update.message.sticker:
        return

    sticker: Sticker = update.message.sticker
    bot_username = context.bot.username

    if not bot_username:
        await update.message.reply_text("❌ I couldn't determine my bot username.")
        return

    pack_name = get_pack_name(bot_username)
    pack_title = get_pack_title()
    emoji = sticker.emoji or FALLBACK_EMOJI

    input_sticker = InputSticker(
        sticker=sticker.file_id,
        emoji_list=[emoji],
        format=get_sticker_format(sticker),
    )

    try:
        exists = await pack_exists(context, pack_name)

        if not exists:
            # the first sticker creates the pack
            await context.bot.create_new_sticker_set(
                user_id=update.effective_user.id,
                name=pack_name,
                title=pack_title,
                stickers=[input_sticker],
            )

            message = (
                f"✅ Created your sticker pack and added the sticker!"
            )

        else:
            # the pack already exists, so add the sticker to it
            await context.bot.add_sticker_to_set(
                user_id=update.effective_user.id,
                name=pack_name,
                sticker=input_sticker,
            )

            message = (
                f"✅ Added the sticker to your favorites!"
            )

        # create a link to the sticker pack.
        pack_url = f"https://t.me/addstickers/{pack_name}"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔗 Open pack",
                        url=pack_url,
                    )
                ]
            ]
        )

        # send the appropriate success message with the pack link
        await update.message.reply_text(
            message,
            reply_markup=keyboard,
        )

    except TelegramError:
        logger.exception("Telegram operation failed")

        try:
            await update.message.reply_text(
                "❌ I couldn't complete that Telegram operation. Please try again."
            )
        except TelegramError:
            logger.exception("Failed to send the error message.")


def main() -> None:
    """Configure and run the bot."""

    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Check your .env file.")


# setting up the application
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

logger.info("StickPalBot is starting...")
app.run_polling()

if __name__ == "__main__":
    main()
