#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت إداري متكامل - نظام كرامة + هيبة + عقوبات تلقائية
"""

import logging
import json
import os
from datetime import datetime, timezone, timedelta
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler,
)
from telegram.error import BadRequest, Forbidden
from telegram.request import HTTPXRequest

# ═══════════════════════════════════════════════
#  ضع توكنك هنا - لا تشاركه مع أحد!
# ═══════════════════════════════════════════════
BOT_TOKEN = "8676088219:AAHgIcUmiYnhVjO-HS6yNiB_opiE-FYFoZw"

# ═══════════════════════════════════════════════
#  إعدادات نظام الإنذارات
# ═══════════════════════════════════════════════
MAX_WARNS = 3          # عدد الإنذارات قبل الحظر التلقائي
WARN_ACTION = "ban"    # ban أو mute بعد تجاوز الحد

# ملف حفظ الإنذارات (محلي)
WARNS_FILE = "warns_data.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
#  نظام حفظ الإنذارات
# ═══════════════════════════════════════════════

def load_warns() -> dict:
    if os.path.exists(WARNS_FILE):
        try:
            with open(WARNS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_warns(data: dict):
    with open(WARNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_warns(chat_id: int, user_id: int) -> list:
    data = load_warns()
    key = f"{chat_id}:{user_id}"
    return data.get(key, [])


def add_warn(chat_id: int, user_id: int, reason: str, by: str) -> int:
    data = load_warns()
    key = f"{chat_id}:{user_id}"
    if key not in data:
        data[key] = []
    data[key].append({
        "reason": reason,
        "by": by,
        "time": datetime.now(timezone.utc).isoformat(),
    })
    save_warns(data)
    return len(data[key])


def remove_warn(chat_id: int, user_id: int) -> int:
    data = load_warns()
    key = f"{chat_id}:{user_id}"
    if key in data and data[key]:
        data[key].pop()
    save_warns(data)
    return len(data.get(key, []))


def reset_warns(chat_id: int, user_id: int):
    data = load_warns()
    key = f"{chat_id}:{user_id}"
    data[key] = []
    save_warns(data)


# ═══════════════════════════════════════════════
#  دوال مساعدة
# ═══════════════════════════════════════════════

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    uid = user_id or update.effective_user.id
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, uid)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False


async def is_owner(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    uid = user_id or update.effective_user.id
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, uid)
        return member.status == "creator"
    except Exception:
        return False


async def bot_is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        bot_member = await context.bot.get_chat_member(
            update.effective_chat.id, context.bot.id
        )
        return bot_member.status in ["administrator", "creator"]
    except Exception:
        return False


async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استخراج المستخدم المستهدف"""
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        return target, None
    if context.args:
        arg = context.args[0]
        try:
            if arg.lstrip("-").isdigit():
                member = await context.bot.get_chat_member(update.effective_chat.id, int(arg))
            else:
                member = await context.bot.get_chat_member(
                    update.effective_chat.id, arg.lstrip("@")
                )
            return member.user, None
        except Exception:
            return None, f"⚠️ ما لقيت المستخدم: `{arg}`"
    return None, "⚠️ حدد المستخدم بالرد على رسالته أو اكتب @username"


def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """استخراج السبب من الأوامر"""
    if update.message.reply_to_message:
        return " ".join(context.args) if context.args else ""
    return " ".join(context.args[1:]) if context.args and len(context.args) > 1 else ""


def warn_bar(current: int, total: int) -> str:
    """شريط مرئي للإنذارات"""
    filled = "🔴" * current
    empty = "⚪" * (total - current)
    return filled + empty


# ═══════════════════════════════════════════════
#  نظام الكرامة - رد البوت على من ينادي عليه
# ═══════════════════════════════════════════════

async def handle_bot_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ردود البوت لما يتم تنادي عليه - نظام الهيبة والكرامة"""
    msg = update.message
    if not msg or not msg.text:
        return

    text_lower = msg.text.lower()
    bot_username = (await context.bot.get_me()).username.lower()

    # تحقق إذا البوت متذكر أو تمت الإشارة إليه
    mentioned = (
        f"@{bot_username}" in text_lower
        or any(e.type == "mention" for e in (msg.entities or []))
    )
    if not mentioned:
        return

    user = msg.from_user
    user_name = user.first_name

    # ردود هيبة بحسب نوع الرسالة
    insults = ["غبي", "حمار", "بليد", "مجنون", "احمق", "stupid", "idiot", "dumb", "trash", "useless"]
    thanks = ["شكرا", "تسلم", "يعطيك", "مشكور", "thanks", "thx", "جزاك"]
    praise = ["ممتاز", "رائع", "احسنت", "بارك", "برافو", "excellent", "great", "perfect", "ذكي"]
    challenge = ["تقدر", "جرب", "مو قادر", "ضعيف", "خايس", "مو شي"]

    if any(w in text_lower for w in insults):
        replies = [
            f"🤖 يا {user_name}، أنا بوت مو إنسان — ما راح أنزل لمستواك.\n"
            f"ركّز على حياتك أحسن.",
            f"😐 كلامك ما يأثر فيّ يا {user_name}.\n"
            f"أنا هنا لأخدم المجموعة، مو لأسمع كلامك.",
            f"🔇 {user_name}، الشخص اللي يشتم البوت عنده وقت فاضي كثير.\n"
            f"يمكن تحتاج تشتغل على نفسك شوية.",
        ]
    elif any(w in text_lower for w in thanks):
        replies = [
            f"✅ العفو يا {user_name}، أنا هنا دايماً للمساعدة.",
            f"🤖 بكل سرور يا {user_name} — هذا واجبي.",
            f"💪 حاضر يا {user_name}، أي شي ثاني؟",
        ]
    elif any(w in text_lower for w in praise):
        replies = [
            f"🙂 شكراً يا {user_name}، أحاول أكون بمستوى المجموعة.",
            f"✨ {user_name} — أنا بس أؤدي دوري، الفضل للأدمن.",
        ]
    elif any(w in text_lower for w in challenge):
        replies = [
            f"😏 {user_name}، أنا قادر على كثير — جرّب تخالف قانون المجموعة وشوف.",
            f"🤖 ضعيف؟ اسأل اللي اتحظروا من قبلي.",
        ]
    else:
        # رد عام
        replies = [
            f"👋 {user_name}، ذكرتني؟ اكتب /help لترى شو أقدر أسوي.",
            f"🤖 نعم يا {user_name}؟ أنا هنا — اكتب /help.",
            f"📋 هلا يا {user_name}! شو تحتاج؟ اكتب /help للأوامر.",
        ]

    import random
    await msg.reply_text(random.choice(replies))


# ═══════════════════════════════════════════════
#  نظام الكرامة - حماية من يدخل بدون صلاحية
# ═══════════════════════════════════════════════

async def check_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ترحيب بالأعضاء الجدد مع تحقق الصلاحيات"""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # البوت أضيف للمجموعة
            bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
            if bot_member.status != "administrator":
                await update.message.reply_text(
                    "⚠️ أنا محتاج صلاحيات أدمن عشان أشتغل صح!\n"
                    "ارفعني مشرف مع كامل الصلاحيات وإلا رح أغادر.\n\n"
                    "🚪 مغادر خلال 10 ثواني إذا ما صار..."
                )
                import asyncio
                await asyncio.sleep(10)
                # تحقق مرة ثانية
                bot_member2 = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
                if bot_member2.status != "administrator":
                    await update.message.reply_text("🚪 وداعاً — ارفعني أدمن وأضفني من جديد.")
                    await context.bot.leave_chat(update.effective_chat.id)


# ═══════════════════════════════════════════════
#  أمر الإنذار /warn
# ═══════════════════════════════════════════════

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنذار مستخدم - عند تجاوز الحد يتحظر تلقائياً"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return

    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return

    if await is_admin(update, context, target.id):
        await update.message.reply_text("⚠️ ما يمكن إنذار مشرف!")
        return

    reason = get_reason(update, context) or "لم يُذكر"
    admin_name = update.effective_user.first_name
    count = add_warn(update.effective_chat.id, target.id, reason, admin_name)
    bar = warn_bar(count, MAX_WARNS)
    name = target.mention_html()

    if count >= MAX_WARNS:
        # تجاوز الحد - عقوبة تلقائية
        reset_warns(update.effective_chat.id, target.id)
        try:
            if WARN_ACTION == "ban":
                await context.bot.ban_chat_member(update.effective_chat.id, target.id)
                action_text = "🚫 تم حظره تلقائياً"
            else:
                silent = ChatPermissions(can_send_messages=False)
                await context.bot.restrict_chat_member(update.effective_chat.id, target.id, silent)
                action_text = "🔇 تم كتمه تلقائياً"
        except Exception as e:
            action_text = f"⚠️ فشل التنفيذ: {e}"

        await update.message.reply_html(
            f"⚠️ <b>إنذار نهائي!</b>\n\n"
            f"👤 المستخدم: {name}\n"
            f"📋 السبب: {reason}\n"
            f"📊 الإنذارات: {bar} ({count}/{MAX_WARNS})\n\n"
            f"{action_text} بعد تجاوز حد الإنذارات!"
        )
    else:
        remaining = MAX_WARNS - count
        await update.message.reply_html(
            f"⚠️ <b>إنذار</b>\n\n"
            f"👤 المستخدم: {name}\n"
            f"📋 السبب: {reason}\n"
            f"📊 الإنذارات: {bar} ({count}/{MAX_WARNS})\n"
            f"⏳ متبقي {remaining} إنذار قبل العقوبة التلقائية!"
        )


async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة إنذار واحد"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return

    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return

    count = remove_warn(update.effective_chat.id, target.id)
    bar = warn_bar(count, MAX_WARNS)
    name = target.mention_html()
    await update.message.reply_html(
        f"✅ تم إزالة إنذار من {name}\n"
        f"📊 الإنذارات الحالية: {bar} ({count}/{MAX_WARNS})"
    )


async def resetwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسح كل إنذارات مستخدم"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return

    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return

    reset_warns(update.effective_chat.id, target.id)
    name = target.mention_html()
    await update.message.reply_html(f"🗑 تم مسح جميع إنذارات {name}!")


async def warns_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إنذارات مستخدم"""
    target, err = await get_target_user(update, context)
    if not target:
        target = update.effective_user

    warns = get_user_warns(update.effective_chat.id, target.id)
    name = target.mention_html()
    bar = warn_bar(len(warns), MAX_WARNS)

    if not warns:
        await update.message.reply_html(f"✅ {name} ليس عنده إنذارات!")
        return

    text = f"📋 <b>إنذارات {name}</b>\n{bar} ({len(warns)}/{MAX_WARNS})\n\n"
    for i, w in enumerate(warns, 1):
        time_str = w.get("time", "")[:10]
        text += f"{i}. 📌 {w.get('reason','—')} — بواسطة {w.get('by','؟')} ({time_str})\n"

    await update.message.reply_html(text)


# ═══════════════════════════════════════════════
#  الحظر والكتم والطرد
# ═══════════════════════════════════════════════

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return
    if await is_admin(update, context, target.id):
        await update.message.reply_text("⚠️ ما يمكن حظر مشرف!")
        return
    reason = get_reason(update, context) or "لم يُذكر"
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        reset_warns(update.effective_chat.id, target.id)
        name = target.mention_html()
        await update.message.reply_html(
            f"🚫 <b>تم الحظر</b>\n\n"
            f"👤 المستخدم: {name}\n"
            f"📋 السبب: {reason}\n"
            f"👮 المشرف: {update.effective_user.first_name}"
        )
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ فشل الحظر: {e}")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, target.id, only_if_banned=True)
        name = target.mention_html()
        await update.message.reply_html(f"✅ تم رفع الحظر عن {name}!")
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ فشل: {e}")


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return
    if await is_admin(update, context, target.id):
        await update.message.reply_text("⚠️ ما يمكن طرد مشرف!")
        return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        name = target.mention_html()
        await update.message.reply_html(
            f"👢 <b>تم الطرد</b>\n\n"
            f"👤 المستخدم: {name}\n"
            f"👮 المشرف: {update.effective_user.first_name}"
        )
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ فشل الطرد: {e}")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كتم - /mute @user [30 أو 2h أو 1d]"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return
    if await is_admin(update, context, target.id):
        await update.message.reply_text("⚠️ ما يمكن كتم مشرف!")
        return

    # تحليل المدة
    duration = None
    duration_text = "دائم"
    time_args = context.args[1:] if (context.args and not update.message.reply_to_message) else context.args
    if time_args:
        t = time_args[0] if not update.message.reply_to_message else (context.args[0] if context.args else None)
        if t:
            try:
                if t.endswith("h"):
                    mins = int(t[:-1]) * 60
                    duration_text = f"{t[:-1]} ساعة"
                elif t.endswith("d"):
                    mins = int(t[:-1]) * 1440
                    duration_text = f"{t[:-1]} يوم"
                elif t.endswith("m"):
                    mins = int(t[:-1])
                    duration_text = f"{t[:-1]} دقيقة"
                else:
                    mins = int(t)
                    duration_text = f"{mins} دقيقة"
                duration = datetime.now(timezone.utc) + timedelta(minutes=mins)
            except ValueError:
                pass

    reason = get_reason(update, context) or "لم يُذكر"
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target.id,
            ChatPermissions(can_send_messages=False, can_send_polls=False,
                            can_send_other_messages=False, can_add_web_page_previews=False),
            until_date=duration,
        )
        name = target.mention_html()
        await update.message.reply_html(
            f"🔇 <b>تم الكتم</b>\n\n"
            f"👤 المستخدم: {name}\n"
            f"📋 السبب: {reason}\n"
            f"⏱ المدة: {duration_text}\n"
            f"👮 المشرف: {update.effective_user.first_name}"
        )
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ فشل الكتم: {e}")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target.id,
            ChatPermissions(can_send_messages=True, can_send_polls=True,
                            can_send_other_messages=True, can_add_web_page_previews=True),
        )
        name = target.mention_html()
        await update.message.reply_html(f"🔊 تم رفع الكتم عن {name}!")
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ فشل: {e}")


# ═══════════════════════════════════════════════
#  رفع وتنزيل الأدمن
# ═══════════════════════════════════════════════

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return
    # عنوان المشرف الجديد
    title = " ".join(context.args[1:]) if (context.args and len(context.args) > 1 and not update.message.reply_to_message) else ""
    if update.message.reply_to_message and context.args:
        title = " ".join(context.args)
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, target.id,
            can_delete_messages=True, can_restrict_members=True,
            can_pin_messages=True, can_promote_members=False,
            can_change_info=True, can_invite_users=True,
            can_manage_chat=True, can_manage_video_chats=True,
        )
        if title:
            await context.bot.set_chat_administrator_custom_title(
                update.effective_chat.id, target.id, title
            )
        name = target.mention_html()
        title_line = f"\n🏷 اللقب: {title}" if title else ""
        await update.message.reply_html(
            f"⭐ <b>تمت الترقية</b>\n\n"
            f"👤 المشرف الجديد: {name}{title_line}\n"
            f"👮 رقّاه: {update.effective_user.first_name}"
        )
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ فشل الترقية: {e}")


async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    target, err = await get_target_user(update, context)
    if not target:
        await update.message.reply_text(err)
        return
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, target.id,
            can_delete_messages=False, can_restrict_members=False,
            can_pin_messages=False, can_promote_members=False,
            can_change_info=False, can_invite_users=False,
            can_manage_chat=False, can_manage_video_chats=False,
        )
        name = target.mention_html()
        await update.message.reply_html(
            f"🔽 <b>تم التنزيل</b>\n\n"
            f"👤 المستخدم: {name}\n"
            f"👮 نزّله: {update.effective_user.first_name}"
        )
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ فشل التنزيل: {e}")


# ═══════════════════════════════════════════════
#  قفل/فتح المجموعة والروابط والتوجيه
# ═══════════════════════════════════════════════

async def lock_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    try:
        await context.bot.set_chat_permissions(
            update.effective_chat.id,
            ChatPermissions(can_send_messages=False, can_send_polls=False,
                            can_send_other_messages=False, can_add_web_page_previews=False,
                            can_change_info=False, can_invite_users=False, can_pin_messages=False)
        )
        await update.message.reply_text("🔒 المجموعة مقفلة — فقط الأدمن يكتب الآن.")
    except BadRequest as e:
        await update.message.reply_text(f"❌ {e}")


async def unlock_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    try:
        await context.bot.set_chat_permissions(
            update.effective_chat.id,
            ChatPermissions(can_send_messages=True, can_send_polls=True,
                            can_send_other_messages=True, can_add_web_page_previews=True,
                            can_change_info=False, can_invite_users=True, can_pin_messages=False)
        )
        await update.message.reply_text("🔓 المجموعة مفتوحة للجميع!")
    except BadRequest as e:
        await update.message.reply_text(f"❌ {e}")


async def lock_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    try:
        p = update.effective_chat.permissions
        await context.bot.set_chat_permissions(
            update.effective_chat.id,
            ChatPermissions(can_send_messages=p.can_send_messages,
                            can_send_polls=p.can_send_polls,
                            can_send_other_messages=p.can_send_other_messages,
                            can_add_web_page_previews=False,
                            can_change_info=p.can_change_info,
                            can_invite_users=p.can_invite_users,
                            can_pin_messages=p.can_pin_messages)
        )
        await update.message.reply_text("🔒 تم قفل الروابط!")
    except BadRequest as e:
        await update.message.reply_text(f"❌ {e}")


async def unlock_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    try:
        p = update.effective_chat.permissions
        await context.bot.set_chat_permissions(
            update.effective_chat.id,
            ChatPermissions(can_send_messages=p.can_send_messages,
                            can_send_polls=p.can_send_polls,
                            can_send_other_messages=p.can_send_other_messages,
                            can_add_web_page_previews=True,
                            can_change_info=p.can_change_info,
                            can_invite_users=p.can_invite_users,
                            can_pin_messages=p.can_pin_messages)
        )
        await update.message.reply_text("🔓 تم فتح الروابط!")
    except BadRequest as e:
        await update.message.reply_text(f"❌ {e}")


async def lock_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    try:
        await update.effective_chat.set_protected_content(True)
        await update.message.reply_text("🔒 تم قفل التوجيه — الرسائل محمية!")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def unlock_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    try:
        await update.effective_chat.set_protected_content(False)
        await update.message.reply_text("🔓 تم فتح التوجيه!")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


# ═══════════════════════════════════════════════
#  أوامر إضافية
# ═══════════════════════════════════════════════

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ رد على الرسالة التي تريد تثبيتها!")
        return
    try:
        await context.bot.pin_chat_message(
            update.effective_chat.id,
            update.message.reply_to_message.message_id
        )
        await update.message.reply_text("📌 تم التثبيت!")
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ {e}")


async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    try:
        await context.bot.unpin_all_chat_messages(update.effective_chat.id)
        await update.message.reply_text("📌 تم إلغاء تثبيت جميع الرسائل!")
    except (BadRequest, Forbidden) as e:
        await update.message.reply_text(f"❌ {e}")


async def del_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ للأدمن فقط!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ رد على الرسالة التي تريد حذفها!")
        return
    try:
        await context.bot.delete_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await update.message.delete()
    except BadRequest as e:
        await update.message.reply_text(f"❌ {e}")


async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target, _ = await get_target_user(update, context)
    if not target:
        target = update.effective_user
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, target.id)
        status_map = {
            "creator": "👑 مالك",
            "administrator": "⭐ مشرف",
            "member": "👤 عضو",
            "restricted": "🔇 مقيّد",
            "left": "🚪 غادر",
            "kicked": "🚫 محظور",
        }
        warns = get_user_warns(update.effective_chat.id, target.id)
        bar = warn_bar(len(warns), MAX_WARNS)
        await update.message.reply_html(
            f"👤 <b>معلومات المستخدم</b>\n\n"
            f"📛 الاسم: {target.full_name}\n"
            f"🆔 المعرف: <code>{target.id}</code>\n"
            f"📲 اليوزر: {'@' + target.username if target.username else 'لا يوجد'}\n"
            f"🏷 الحالة: {status_map.get(member.status, member.status)}\n"
            f"⚠️ الإنذارات: {bar} ({len(warns)}/{MAX_WARNS})"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_html(
            "👋 مرحباً! أنا بوت إداري متكامل.\n\n"
            "أضفني لمجموعتك كمشرف واكتب /help للأوامر.\n\n"
            "⚠️ <b>تنبيه:</b> إذا أضفتني بدون صلاحيات سأغادر تلقائياً!"
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "🤖 <b>قائمة الأوامر</b>\n\n"

        "<b>⚠️ الإنذارات:</b>\n"
        "/warn @user [سبب] — إنذار (عند {} ينعاقب تلقائي)\n"
        "/unwarn @user — إزالة إنذار\n"
        "/resetwarn @user — مسح كل الإنذارات\n"
        "/warns @user — عرض الإنذارات\n\n"

        "<b>🚫 الحظر والطرد:</b>\n"
        "/ban @user [سبب] — حظر\n"
        "/unban @user — رفع حظر\n"
        "/kick @user — طرد (بدون حظر)\n\n"

        "<b>🔇 الكتم:</b>\n"
        "/mute @user [مدة] — كتم (30m / 2h / 1d)\n"
        "/unmute @user — رفع الكتم\n\n"

        "<b>⭐ الإدارة:</b>\n"
        "/promote @user [لقب] — ترقية لمشرف\n"
        "/demote @user — تنزيل من المشرفين\n\n"

        "<b>🔒 القفل:</b>\n"
        "/lock — قفل المجموعة كاملاً\n"
        "/unlock — فتح المجموعة\n"
        "/locklink — قفل الروابط\n"
        "/unlocklink — فتح الروابط\n"
        "/lockfwd — قفل التوجيه\n"
        "/unlockfwd — فتح التوجيه\n\n"

        "<b>🛠 أخرى:</b>\n"
        "/del — حذف رسالة (رد عليها)\n"
        "/pin — تثبيت رسالة\n"
        "/unpin — إلغاء التثبيت\n"
        "/info [@user] — معلومات مستخدم\n\n"

        "💡 الأوامر تشتغل بالرد أو @username أو ID".format(MAX_WARNS)
    )


# ═══════════════════════════════════════════════
#  تشغيل البوت
# ═══════════════════════════════════════════════

def main():
    if BOT_TOKEN == "ضع_توكنك_هنا":
        print("❌ خطأ: ضع التوكن الصحيح في متغير BOT_TOKEN!")
        print("   احصل على توكن جديد من @BotFather لأن القديم صار مكشوف.")
        return

    # ═══════════════════════════════════════════
    # إعدادات الاتصال - حل مشكلة TimedOut والحجب
    # ═══════════════════════════════════════════
    # الخيار 1: زيادة مهلة الاتصال (جرب هذا أول)
    request = HTTPXRequest(
        connect_timeout=30.0,   # مهلة الاتصال
        read_timeout=30.0,      # مهلة القراءة
        write_timeout=30.0,     # مهلة الكتابة
        pool_timeout=30.0,      # مهلة انتظار الاتصال
    )

    # الخيار 2: إذا تليجرام محجوب عندك، فعّل البروكسي بالتعليق أدناه
    # (اشترِ بروكسي SOCKS5 أو استخدم Tor أو VPN)
    #
    # للبروكسي العادي HTTP:
    # request = HTTPXRequest(proxy="http://127.0.0.1:8080")
    #
    # لبروكسي SOCKS5 (مثل Tor على المنفذ 9050):
    # request = HTTPXRequest(proxy="socks5://127.0.0.1:9050")
    #
    # لبروكسي MTProto الرسمي لتليجرام:
    # أضف في builder: .proxy("https://t.me/proxy?server=...&port=...&secret=...")

    app = Application.builder().token(BOT_TOKEN).request(request).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("info", info_cmd))

    # الإنذارات
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("resetwarn", resetwarn))
    app.add_handler(CommandHandler("warns", warns_list))

    # الحظر والطرد
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))

    # الكتم
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))

    # الإدارة
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))

    # القفل
    app.add_handler(CommandHandler("lock", lock_all))
    app.add_handler(CommandHandler("unlock", unlock_all))
    app.add_handler(CommandHandler("locklink", lock_links))
    app.add_handler(CommandHandler("unlocklink", unlock_links))
    app.add_handler(CommandHandler("lockfwd", lock_forward))
    app.add_handler(CommandHandler("unlockfwd", unlock_forward))

    # أخرى
    app.add_handler(CommandHandler("del", del_msg))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("unpin", unpin))

    # نظام الكرامة - رد على المنشن
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Entity("mention") & ~filters.COMMAND,
        handle_bot_mention
    ))

    # كشف إضافة البوت للمجموعة
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, check_new_member))

    print("✅ البوت شغّال! اضغط Ctrl+C للإيقاف.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
