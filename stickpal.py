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

from telegram.error import BadRequest, TelegramError

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

from database import (
    initialize_database,
    register_user,
    create_pack,
    list_packs,
    get_pack_by_id,
)

# load environment variables
load_dotenv()  # loads the token from .env
TOKEN = os.getenv("BOT_TOKEN")

# global settings
PACK_TITLE_LIMIT = 64
FALLBACK_EMOJI = "🌟"

(
    HOME,
    WAITING_FOR_PACK_TITLE,
    WAITING_FOR_FIRST_STICKER,
    AFTER_FIRST_STICKER,
    CHOOSING_PACK_TO_ADD,
    COLLECTING_STICKERS,
) = range(6)

# logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Create a pack",
                callback_data="create",
            ),
            InlineKeyboardButton(
                "📦 My packs",
                callback_data="packs",
            ),
        ],
        [
            InlineKeyboardButton(
                "➕ Add to a pack",
                callback_data="add",
            ),
        ],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])


def collection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("I'm done", callback_data="done")]
    ])


def get_sticker_format(sticker: Sticker) -> str:
    """Return Telegram's format name for a sticker."""

    if sticker.is_animated:
        return "animated"

    if sticker.is_video:
        return "video"

    return "static"


def get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Return the bot's username."""

    username = context.bot.username

    if not username:
        raise ValueError("I couldn't determine my bot username.")

    return username


async def pack_exists(context: ContextTypes.DEFAULT_TYPE, pack_name: str) -> bool:
    """Check if a sticker pack already exists."""

    try:
        await context.bot.get_sticker_set(pack_name)
        return True

    except BadRequest as error:
        if "STICKERSET_INVALID" in str(error).upper():
            return False

        raise


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE, ) -> int:
    """Show the home screen and clear temporary conversation data."""

    context.user_data.pop("active_pack_id", None)

    text = (
        "Welcome to StickPalBot! 👋\n\n"
        "What would you like to do?"
    )

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text,
            reply_markup=home_keyboard(),
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=home_keyboard(),
        )

    return HOME


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Register the user."""

    if update.effective_user:
        register_user(update.effective_user.id)

    return await show_home(update, context)


async def create_pack_start(update: Update, _: ContextTypes.DEFAULT_TYPE, ) -> int:
    text = (
        "What would you like to call your sticker pack?\n\n"
        "Send the title you'd like people to see in Telegram."
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            reply_markup=cancel_keyboard(),
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=cancel_keyboard(),
        )

    return WAITING_FOR_PACK_TITLE


async def receive_pack_title(update: Update, context: ContextTypes.DEFAULT_TYPE, ) -> int:
    if not update.message or not update.effective_user:
        return WAITING_FOR_PACK_TITLE

    title = (update.message.text or "").strip()

    if not title:
        await update.message.reply_text(
            "Please send a title containing at least one character.",
            reply_markup=cancel_keyboard(),
        )
        return WAITING_FOR_PACK_TITLE

    if len(title) > PACK_TITLE_LIMIT:
        await update.message.reply_text(
            "That title is too long. Please keep it to 64 characters.",
            reply_markup=cancel_keyboard(),
        )
        return WAITING_FOR_PACK_TITLE

    try:
        pack = create_pack(user_id=update.effective_user.id, pack_title=title, bot_username=get_bot_username(context), )

    except (ValueError, TelegramError) as error:
        await update.message.reply_text(
            f"❌ I couldn't prepare that pack: {error}",
            reply_markup=cancel_keyboard(),
        )

        return WAITING_FOR_PACK_TITLE

    context.user_data["active_pack_id"] = pack["id"]

    await update.message.reply_text(
        f"Your pack '{pack['pack_title']}' is ready! ✨\n\n"
        "Now send me the first sticker. I'll create the Telegram pack after that.",
        reply_markup=cancel_keyboard(),
    )

    return WAITING_FOR_FIRST_STICKER


async def choose_pack_to_add(update: Update, _: ContextTypes.DEFAULT_TYPE, ) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    packs = list_packs(user_id)

    if not packs:
        await query.edit_message_text(
            "You don't have any packs yet. Create one first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "➕ Create a pack",
                    callback_data="create",
                )],
                [InlineKeyboardButton(
                    "🏠 Home",
                    callback_data="home",
                )],
            ]),
        )
        return HOME

    buttons = [
        [InlineKeyboardButton(
            pack["pack_title"],
            callback_data=f"choose:{pack['id']}",
        )]
        for pack in packs
    ]
    buttons.append([
        InlineKeyboardButton("Cancel", callback_data="cancel")
    ])

    await query.edit_message_text(
        "Which pack would you like to add stickers to?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    return CHOOSING_PACK_TO_ADD


async def select_pack_for_collection(update: Update, context: ContextTypes.DEFAULT_TYPE, ) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    pack_id = int(query.data.split(":", 1)[1])
    pack = get_pack_by_id(user_id, pack_id)

    if not pack:
        await query.edit_message_text(
            "I couldn't find that pack in your account. Please try again.",
            reply_markup=home_keyboard(),
        )
        return HOME

    context.user_data["active_pack_id"] = pack["id"]

    await query.edit_message_text(
        f"Selected '{pack['pack_title']}'.\n\n"
        "Send me stickers to add them to this pack. "
        "Tap I'm done when you've finished.",
        reply_markup=collection_keyboard(),
    )

    return COLLECTING_STICKERS


async def create_or_add_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE, pack: dict, ) -> bool:
    """Create the Telegram set if needed, otherwise add the sticker."""
    sticker = update.message.sticker
    user_id = update.effective_user.id
    short_name = pack["telegram_short_name"]

    input_sticker = InputSticker(
        sticker=sticker.file_id,
        emoji_list=[sticker.emoji or FALLBACK_EMOJI],
        format=get_sticker_format(sticker),
    )

    exists = await pack_exists(context, short_name)

    if not exists:
        await context.bot.create_new_sticker_set(
            user_id=user_id,
            name=short_name,
            title=pack["pack_title"],
            stickers=[input_sticker],
        )
        return True

    await context.bot.add_sticker_to_set(
        user_id=user_id,
        name=short_name,
        sticker=input_sticker,
    )

    return False


async def receive_first_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE, ) -> int:
    if not update.message or not update.message.sticker:
        return WAITING_FOR_FIRST_STICKER

    if not update.effective_user:
        return WAITING_FOR_FIRST_STICKER

    pack_id = context.user_data.get("active_pack_id")
    pack = get_pack_by_id(update.effective_user.id, pack_id)

    if not pack:
        await update.message.reply_text(
            "I couldn't find that pack. Please start again with /start."
        )
        return await show_home(update, context)

    try:
        await create_or_add_sticker(update, context, pack)

    except TelegramError:
        logger.exception("Failed to create the Telegram sticker pack.")
        await update.message.reply_text(
            "❌ I couldn't create the Telegram pack. Your pack details are saved. Please send the sticker again."
        )
        return WAITING_FOR_FIRST_STICKER

    link = f"https://t.me/addstickers/{pack['telegram_short_name']}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Open pack", url=link)],
        [
            InlineKeyboardButton(
                "➕ Add more stickers",
                callback_data="more",
            ),
            InlineKeyboardButton(
                "🏠 Back to home",
                callback_data="done",
            ),
        ],
    ])

    await update.message.reply_text(
        f"Your pack '{pack['pack_title']}' has been created! 🎉",
        reply_markup=keyboard,
    )

    return AFTER_FIRST_STICKER


async def begin_adding_more(update: Update, _: ContextTypes.DEFAULT_TYPE, ) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Send me as many stickers as you'd like.\n\n"
        "Tap I'm done whenever you're finished.",
        reply_markup=collection_keyboard(),
    )

    return COLLECTING_STICKERS


async def collect_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE, ) -> int:
    if not update.message or not update.message.sticker:
        return COLLECTING_STICKERS

    if not update.effective_user:
        return COLLECTING_STICKERS

    pack_id = context.user_data.get("active_pack_id")
    pack = get_pack_by_id(update.effective_user.id, pack_id)

    if not pack:
        await update.message.reply_text(
            "I couldn't find that pack. Please choose a pack again."
        )
        return await show_home(update, context)

    try:
        await create_or_add_sticker(update, context, pack)

    except TelegramError:
        logger.exception("Failed to add a sticker.")
        await update.message.reply_text(
            "❌ I couldn't add that sticker. Please try again.",
            reply_markup=collection_keyboard(),
        )
        return COLLECTING_STICKERS

    link = f"https://t.me/addstickers/{pack['telegram_short_name']}"

    await update.message.reply_text(
        f"✅ Added a sticker to '{pack['pack_title']}'.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Open pack", url=link)],
            [InlineKeyboardButton(
                "I'm done",
                callback_data="done",
            )],
        ]),
    )

    return COLLECTING_STICKERS


async def show_packs(update: Update, _: ContextTypes.DEFAULT_TYPE, ) -> int:
    user_id = update.effective_user.id
    packs = list_packs(user_id)

    if not packs:
        text = "You haven't created any packs yet. Choose Create a pack to get started."

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "➕ Create a pack",
                callback_data="create",
            )],
            [InlineKeyboardButton("🏠 Home", callback_data="home")],
        ])
    else:
        lines = ["📦 Your sticker packs:\n"]
        buttons = []

        for pack in packs:
            link = "https://t.me/addstickers/" + pack["telegram_short_name"]

            lines.append(f"• {pack['pack_title']}\n{link}")
            buttons.append([
                InlineKeyboardButton(
                    f"➕ Add to: {pack['pack_title']}",
                    callback_data=f"choose:{pack['id']}",
                )
            ])

        buttons.append([
            InlineKeyboardButton("🏠 Home", callback_data="home")
        ])

        text = "\n\n".join(lines)
        keyboard = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=keyboard,
                                                      )
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

    return HOME


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await show_home(update, context)


async def add_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await begin_adding_more(update, context)


async def done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await show_home(update, context)


async def create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await create_pack_start(update, context)


async def add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await choose_pack_to_add(update, context)


async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await show_home(update, context)


async def packs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await show_packs(update, context)


async def packs_command(update: Update, context: ContextTypes.DEFAULT_TYPE,) -> int:
    return await show_packs(update, context)


async def addtopack_command(update: Update, _: ContextTypes.DEFAULT_TYPE,) -> int:
    if not update.message:
        return HOME

    # reuse the same pack-selection flow as the home button
    packs = list_packs(update.effective_user.id)

    if not packs:
        await update.message.reply_text(
            "You don't have any packs yet. Create one first!",
            reply_markup=home_keyboard(),
        )
        return HOME

    buttons = [
        [InlineKeyboardButton(
            pack["pack_title"],
            callback_data=f"choose:{pack['id']}",
        )]
        for pack in packs
    ]
    buttons.append([
        InlineKeyboardButton("Cancel", callback_data="cancel")
    ])

    await update.message.reply_text(
        "Which pack would you like to add stickers to?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    return CHOOSING_PACK_TO_ADD


def main() -> None:
    """Configure and run the bot."""

    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Check your .env file.")

    initialize_database()

    # setting up the application
    app = ApplicationBuilder().token(TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("createpack", create_pack_start),
            CommandHandler("packs", packs_command),
            CommandHandler("addtopack", addtopack_command),
        ],
        states={
            HOME: [
                CallbackQueryHandler(create_callback, pattern="^create$"),
                CallbackQueryHandler(packs_callback, pattern="^packs$"),
                CallbackQueryHandler(add_callback, pattern="^add$"),
            ],
            WAITING_FOR_PACK_TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_pack_title,
                ),
            ],
            WAITING_FOR_FIRST_STICKER: [
                MessageHandler(
                    filters.Sticker.ALL,
                    receive_first_sticker,
                ),
            ],
            AFTER_FIRST_STICKER: [
                CallbackQueryHandler(
                    add_more_callback,
                    pattern="^more$",
                ),
            ],
            CHOOSING_PACK_TO_ADD: [
                CallbackQueryHandler(
                    select_pack_for_collection,
                    pattern=r"^choose:\d+$",
                ),
            ],
            COLLECTING_STICKERS: [
                MessageHandler(
                    filters.Sticker.ALL,
                    collect_sticker,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("packs", packs_command),
            CommandHandler("addtopack", addtopack_command),
            CommandHandler("createpack", create_pack_start),
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$"),
            CallbackQueryHandler(done_callback, pattern="^done$"),
            CallbackQueryHandler(home_callback, pattern="^home$"),
        ],
        allow_reentry=True,
    )

    app.add_handler(conversation)

    logger.info("StickPalBot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
