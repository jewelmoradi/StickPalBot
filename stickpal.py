import os
from dotenv import load_dotenv
from telegram import InputSticker, Update, Sticker
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

load_dotenv()  # loads the token from .env
TOKEN = os.getenv("BOT_TOKEN")

# global settings
PACK_TITLE = "My Favorite Stickers ✨"

PACK_FORMATS = {
    "static": "static",
    "animated": "animated",
    "video": "video",
}


def get_sticker_format(sticker: Sticker) -> str:
    """Return Telegram's format name for a sticker"""

    if sticker.is_animated:
        return "animated"

    if sticker.is_video:
        return "video"

    return "static"


def get_pack_name(format_name: str, bot_username: str) -> str:
    """Create the unique Telegram sticker-set short name."""

    username = bot_username.removeprefix("@").lower()

    return f"favs_{format_name}_by_{username}"


def get_pack_title(format_name: str) -> str:
    """Create the human-readable sticker-set title."""

    return f"{PACK_TITLE} — {PACK_FORMATS[format_name]}"


async def pack_exists(context: ContextTypes.DEFAULT_TYPE, pack_name: str) -> bool:
    """Check if a sticker pack already exists."""

    try:
        await context.bot.get_sticker_set(pack_name)
        return True

    except BadRequest as error:
        if "STICKERSET_INVALID" in str(error).upper():
            return False

        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi!👋\n\n"
        "Send me a sticker and I'll add it to your StickPal favorites!"
    )


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):

    sticker: Sticker = update.message.sticker
    sticker_format = get_sticker_format(sticker)
    bot_username = context.bot.username

    if not bot_username:
        await update.message.reply_text("❌ I couldn't determine my bot username.")
        return

    pack_name = get_pack_name(sticker_format, bot_username)
    pack_title = get_pack_title(sticker_format)
    emoji = sticker.emoji or "🌟"

    input_sticker = InputSticker(
        sticker=sticker.file_id,
        emoji_list=[emoji],
        format=sticker_format,
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

            await update.message.reply_text(
                f"✅ Created your {sticker_format} sticker pack "
                f"and added the sticker!"
            )

        else:
            # the pack already exists, so add the sticker to it
            await context.bot.add_sticker_to_set(
                user_id=update.effective_user.id,
                name=pack_name,
                sticker=input_sticker,
            )

            await update.message.reply_text(
                f"✅ Added the sticker to your {sticker_format} favorites!"
            )

    except Exception as error:
        await update.message.reply_text(
            f"❌ Something went wrong:\n{error}"
        )


# setting up the application
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

app.run_polling()
