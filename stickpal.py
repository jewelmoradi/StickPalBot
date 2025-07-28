import os
from dotenv import load_dotenv
from telegram import Update, Sticker
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

load_dotenv()  # Loads the token from .env
TOKEN = os.getenv("BOT_TOKEN")

# Global settings
STICKER_SET_NAME = "favs_by_stickpal"
STICKER_SET_TITLE = "My Favorite Stickers ✨"
has_created = False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send me any sticker — static, animated, or video — and I’ll collect it into your sticker pack!"
    )


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global has_created

    sticker = update.message.sticker
    sticker: Sticker = update.message.sticker
    user_id = update.effective_user.id
    emoji = sticker.emoji or "🌟"  # Use original emoji or default

    if not has_created:
        try:
            await context.bot.create_new_sticker_set(
                user_id=user_id,
                name=STICKER_SET_NAME,
                title=STICKER_SET_TITLE,
                stickers=[{
                    "sticker": sticker.file_id,
                    "emoji": emoji
                }],
                sticker_format=sticker.format  # Supporting 'static', 'animated', or 'video'
            )
            has_created = True
            await update.message.reply_text("✅ Created your sticker pack and added the first sticker!")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to create sticker set: {e}")
    else:
        try:
            await context.bot.add_sticker_to_set(
                user_id=user_id,
                name=STICKER_SET_NAME,
                sticker={
                    "sticker": sticker.file_id,
                    "emoji": emoji
                }
            )
            await update.message.reply_text("✅ Added sticker to your favorites!")
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding sticker: {e}")


# Setting up application
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

app.run_polling()
