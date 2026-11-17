import os
import json
import math
import random
import smtplib
import threading
import time
import urllib.request
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import requests
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# App & DB setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "liturgical-secret-2026")

raw_db_url = os.environ.get("DATABASE_URL", "sqlite:///liturgical.db")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "liturgical2026")

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------------------------
# Cloudinary helper
# ---------------------------------------------------------------------------

CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
if CLOUDINARY_URL:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)


def upload_file(file_storage):
    """Upload to Cloudinary if configured, else save locally. Returns public URL."""
    if not file_storage or file_storage.filename == "":
        return None
    filename = secure_filename(file_storage.filename)
    if CLOUDINARY_URL:
        result = cloudinary.uploader.upload(file_storage, resource_type="auto")
        return result.get("secure_url", "")
    else:
        dest = os.path.join(UPLOAD_FOLDER, filename)
        file_storage.save(dest)
        return f"/static/uploads/{filename}"

# ---------------------------------------------------------------------------
# Catholic Bible Verses (25, including Deuterocanonical)
# ---------------------------------------------------------------------------

CATHOLIC_BIBLE_VERSES = [
    {"verse": "Be strong and courageous. Do not be afraid; do not be discouraged, for the Lord your God will be with you wherever you go.", "reference": "Joshua 1:9"},
    {"verse": "I can do all things through Christ who strengthens me.", "reference": "Philippians 4:13"},
    {"verse": "For I know the plans I have for you, declares the Lord, plans to prosper you and not to harm you, plans to give you hope and a future.", "reference": "Jeremiah 29:11"},
    {"verse": "Trust in the Lord with all your heart and lean not on your own understanding; in all your ways submit to him, and he will make your paths straight.", "reference": "Proverbs 3:5-6"},
    {"verse": "The Lord is my shepherd; I shall not want.", "reference": "Psalm 23:1"},
    {"verse": "Even though I walk through the darkest valley, I will fear no evil, for you are with me; your rod and your staff, they comfort me.", "reference": "Psalm 23:4"},
    {"verse": "But those who hope in the Lord will renew their strength. They will soar on wings like eagles; they will run and not grow weary, they will walk and not be faint.", "reference": "Isaiah 40:31"},
    {"verse": "For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.", "reference": "John 3:16"},
    {"verse": "Love is patient, love is kind. It does not envy, it does not boast, it is not proud.", "reference": "1 Corinthians 13:4"},
    {"verse": "And now these three remain: faith, hope and love. But the greatest of these is love.", "reference": "1 Corinthians 13:13"},
    {"verse": "Do not be anxious about anything, but in every situation, by prayer and petition, with thanksgiving, present your requests to God.", "reference": "Philippians 4:6"},
    {"verse": "Come to me, all you who are weary and burdened, and I will give you rest.", "reference": "Matthew 11:28"},
    {"verse": "I am the way and the truth and the life. No one comes to the Father except through me.", "reference": "John 14:6"},
    {"verse": "My child, when you come to serve the Lord, prepare yourself for trials.", "reference": "Sirach 2:1"},
    {"verse": "The souls of the just are in the hand of God, and no torment shall touch them.", "reference": "Wisdom 3:1"},
    {"verse": "Prayer with fasting is good, but better than both is almsgiving with righteousness.", "reference": "Tobit 12:8"},
    {"verse": "With all your heart honor your father; your mother's birth pangs do not forget.", "reference": "Sirach 7:27"},
    {"verse": "Happy are those who fear the Lord and walk in his ways.", "reference": "Psalm 128:1"},
    {"verse": "The Lord is near to the brokenhearted and saves the crushed in spirit.", "reference": "Psalm 34:18"},
    {"verse": "She is more precious than jewels, and nothing you desire can compare with her.", "reference": "Proverbs 3:15"},
    {"verse": "Ask and it will be given to you; seek and you will find; knock and the door will be opened to you.", "reference": "Matthew 7:7"},
    {"verse": "Be still, and know that I am God.", "reference": "Psalm 46:10"},
    {"verse": "The Lord bless you and keep you; the Lord make his face shine on you and be gracious to you.", "reference": "Numbers 6:24-25"},
    {"verse": "Whatever you do, work at it with all your heart, as working for the Lord, not for human masters.", "reference": "Colossians 3:23"},
    {"verse": "May the God of hope fill you with all joy and peace as you trust in him.", "reference": "Romans 15:13"},
]

# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "noreply@liturgicalclub.com")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")


def _build_welcome_email_html(full_name: str, verse: dict) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Welcome to the Liturgical Club</title>
<style>
  body{{margin:0;padding:0;background:#0a1628;font-family:'Georgia',serif;}}
  .container{{max-width:600px;margin:0 auto;background:#0d1f3c;border:2px solid #c9a84c;border-radius:12px;overflow:hidden;}}
  .header{{background:linear-gradient(135deg,#0a1628 0%,#1a3a6e 50%,#0a1628 100%);padding:40px 30px;text-align:center;border-bottom:3px solid #c9a84c;}}
  .cross{{font-size:48px;color:#c9a84c;display:block;margin-bottom:12px;}}
  .header h1{{color:#c9a84c;font-size:26px;margin:0 0 8px;letter-spacing:2px;text-transform:uppercase;}}
  .header p{{color:#a8c4e0;font-size:14px;margin:0;letter-spacing:1px;}}
  .body{{padding:36px 30px;}}
  .greeting{{color:#e8d5a3;font-size:18px;margin-bottom:20px;}}
  .message{{color:#b8cfe8;font-size:15px;line-height:1.8;margin-bottom:28px;}}
  .verse-box{{background:linear-gradient(135deg,#1a3a6e,#0d2a52);border-left:4px solid #c9a84c;border-radius:8px;padding:24px;margin:28px 0;}}
  .verse-label{{color:#c9a84c;font-size:11px;letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;}}
  .verse-text{{color:#f0e6c8;font-size:16px;font-style:italic;line-height:1.7;margin-bottom:12px;}}
  .verse-ref{{color:#c9a84c;font-size:13px;font-weight:bold;text-align:right;}}
  .cta{{text-align:center;margin:30px 0;}}
  .cta a{{background:linear-gradient(135deg,#c9a84c,#e8c96a);color:#0a1628;padding:14px 32px;border-radius:30px;text-decoration:none;font-size:15px;font-weight:bold;letter-spacing:1px;display:inline-block;}}
  .footer{{background:#060f1e;padding:24px 30px;text-align:center;border-top:1px solid #1a3a6e;}}
  .footer p{{color:#4a6fa5;font-size:12px;margin:4px 0;}}
  .footer strong{{color:#c9a84c;}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <span class="cross">✝</span>
    <h1>Liturgical Club</h1>
    <p>Ora et Labora · Serving with Joy and Faith</p>
  </div>
  <div class="body">
    <p class="greeting">Dear {full_name},</p>
    <p class="message">
      We are overjoyed to receive your application to join the <strong style="color:#c9a84c;">Liturgical Club</strong>!
      Your desire to serve God through the sacred liturgy fills us with great hope.
      Our team will review your application and reach out to you shortly.
    </p>
    <p class="message">
      As you await our reply, we invite you to reflect on this sacred verse chosen especially for you:
    </p>
    <div class="verse-box">
      <div class="verse-label">✦ Your Verse for Today ✦</div>
      <div class="verse-text">"{verse['verse']}"</div>
      <div class="verse-ref">— {verse['reference']}</div>
    </div>
    <p class="message">
      May this Word accompany you as you begin this new chapter of service.
      We are grateful for your openness and look forward to journeying with you.
    </p>
    <div class="cta">
      <a href="#">Learn More About Our Ministries</a>
    </div>
  </div>
  <div class="footer">
    <p><strong>Liturgical Club</strong></p>
    <p>Serving God Through Sacred Liturgy</p>
    <p style="margin-top:12px;color:#2a4a7f;">This is an automated message. Please do not reply to this email.</p>
  </div>
</div>
</body>
</html>"""


def _send_welcome_email(full_name: str, to_email: str, verse: dict):
    subject = f"Welcome to the Liturgical Club, {full_name}! ✝"
    html_body = _build_welcome_email_html(full_name, verse)

    # Try Brevo first
    if BREVO_API_KEY and SENDER_EMAIL:
        try:
            resp = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "accept": "application/json",
                    "api-key": BREVO_API_KEY,
                    "content-type": "application/json",
                },
                json={
                    "sender": {"name": "Liturgical Club", "email": SENDER_EMAIL},
                    "to": [{"email": to_email, "name": full_name}],
                    "subject": subject,
                    "htmlContent": html_body,
                },
                timeout=15,
            )
            if resp.status_code in (200, 201):
                return
        except Exception:
            pass

    # Fallback: SMTP
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SENDER_EMAIL or SMTP_USER
            msg["To"] = to_email
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
                srv.ehlo()
                srv.starttls()
                srv.login(SMTP_USER, SMTP_PASS)
                srv.sendmail(msg["From"], [to_email], msg.as_string())
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(200), default="Liturgical Club")
    tagline = db.Column(db.String(500), default="Serving God Through Sacred Liturgy")
    hero_title = db.Column(db.String(300), default="Welcome to Liturgical Club")
    hero_subtitle = db.Column(db.String(500), default="A community of faith, worship, and service")
    hero_image_url = db.Column(db.String(1000), default="")
    about_text = db.Column(db.Text, default="")
    footer_rainbow_text = db.Column(db.String(500), default="Liturgical Club · Serving with Joy")
    contact_email = db.Column(db.String(200), default="")
    contact_phone = db.Column(db.String(100), default="")
    facebook_url = db.Column(db.String(500), default="")
    # Background music
    music_enabled = db.Column(db.Boolean, default=True)
    music_title = db.Column(db.String(300), default="Sacred Cathedral Instrumental")
    music_url = db.Column(db.String(1000), default="https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3")
    # Legacy column kept for backward compat
    background_music_url = db.Column(db.String(1000), default="")
    # Liturgical override
    liturgical_override_enabled = db.Column(db.Boolean, default=False)
    liturgical_override_text = db.Column(db.String(300), default="")
    liturgical_override_color = db.Column(db.String(50), default="green")


class HomepageInfoCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(100), default="✝")
    order_index = db.Column(db.Integer, default=0)


class Ministry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(1000), default="")
    order_index = db.Column(db.Integer, default=0)


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    day_time = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(300), default="")
    description = db.Column(db.Text, default="")
    order_index = db.Column(db.Integer, default=0)


class GalleryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    image_url = db.Column(db.String(1000), nullable=False)
    caption = db.Column(db.Text, default="")
    order_index = db.Column(db.Integer, default=0)


class Officer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    position = db.Column(db.String(200), nullable=False)
    image_url = db.Column(db.String(1000), default="")
    bio = db.Column(db.Text, default="")
    order_index = db.Column(db.Integer, default=0)


class Application(db.Model):
    __tablename__ = "application"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(300), nullable=False)
    age = db.Column(db.Integer)
    contact = db.Column(db.String(200), default="")
    ministry = db.Column(db.String(200), default="")
    experience = db.Column(db.Text, default="")
    note = db.Column(db.Text, default="")
    verse_sent = db.Column(db.Text, default="")
    status = db.Column(db.String(50), default="Pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------------------------------------------------------------------
# Liturgical calendar engine
# ---------------------------------------------------------------------------

def _easter(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return {1: f"{n}st", 2: f"{n}nd", 3: f"{n}rd"}.get(n % 10, f"{n}th")


def get_liturgical_info(today: date = None) -> dict:
    if today is None:
        today = date.today()
    year = today.year

    from datetime import timedelta

    easter = _easter(year)

    ash_wednesday = easter - timedelta(days=46)
    palm_sunday = easter - timedelta(days=7)
    holy_thursday = easter - timedelta(days=3)
    good_friday = easter - timedelta(days=2)
    holy_saturday = easter - timedelta(days=1)
    ascension = easter + timedelta(days=39)
    pentecost = easter + timedelta(days=49)
    trinity_sunday = pentecost + timedelta(days=7)
    corpus_christi = trinity_sunday + timedelta(days=4)

    christmas = date(year, 12, 25)
    advent_start_offset = (christmas.weekday() + 1) % 7
    last_sunday_before_xmas = christmas - timedelta(days=advent_start_offset if advent_start_offset else 7)
    advent_start = last_sunday_before_xmas - timedelta(weeks=3)

    christmas_prev = date(year - 1, 12, 25)
    offset_prev = (christmas_prev.weekday() + 1) % 7
    last_sun_prev = christmas_prev - timedelta(days=offset_prev if offset_prev else 7)
    advent_start_prev = last_sun_prev - timedelta(weeks=3)

    epiphany = date(year, 1, 6)
    days_after = (6 - epiphany.weekday()) % 7
    baptism_lord = epiphany + timedelta(days=days_after if days_after else 7)

    def week_num(start: date, t: date) -> int:
        return max(1, math.ceil((t - start).days / 7) + 1)

    if advent_start <= today < date(year, 12, 25):
        week = week_num(advent_start, today)
        ordinal = ["1st", "2nd", "3rd", "4th"][min(week - 1, 3)]
        return {"season": "Advent", "week_label": f"{ordinal} Week of Advent", "color": "purple", "color_hex": "#6B2D8B"}

    if today >= date(year, 12, 25) or today < epiphany:
        return {"season": "Christmas Season", "week_label": "Christmas Season", "color": "gold", "color_hex": "#FFD700"}

    if epiphany <= today <= baptism_lord:
        return {"season": "Christmas Season", "week_label": "Epiphany & Christmas Season", "color": "gold", "color_hex": "#FFD700"}

    if ash_wednesday <= today < easter:
        if today >= palm_sunday:
            if today == holy_thursday:
                return {"season": "Holy Week", "week_label": "Holy Thursday", "color": "gold", "color_hex": "#FFD700"}
            if today == good_friday:
                return {"season": "Holy Week", "week_label": "Good Friday", "color": "red", "color_hex": "#C0392B"}
            if today == holy_saturday:
                return {"season": "Holy Week", "week_label": "Holy Saturday", "color": "purple", "color_hex": "#6B2D8B"}
            return {"season": "Holy Week", "week_label": "Palm Sunday / Holy Week", "color": "red", "color_hex": "#C0392B"}
        week = week_num(ash_wednesday, today)
        ordinal_map = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th"}
        ordinal = ordinal_map.get(week, f"{week}th")
        return {"season": "Lent", "week_label": f"{ordinal} Week of Lent", "color": "purple", "color_hex": "#6B2D8B"}

    if today == easter:
        return {"season": "Easter Season", "week_label": "Easter Sunday", "color": "gold", "color_hex": "#FFD700"}

    if easter < today <= pentecost:
        week = week_num(easter, today)
        ordinal_map = {1:"1st",2:"2nd",3:"3rd",4:"4th",5:"5th",6:"6th",7:"7th",8:"8th"}
        ordinal = ordinal_map.get(week, f"{week}th")
        if today == ascension:
            return {"season": "Easter Season", "week_label": "Ascension Thursday", "color": "gold", "color_hex": "#FFD700"}
        if today == pentecost:
            return {"season": "Easter Season", "week_label": "Pentecost Sunday", "color": "red", "color_hex": "#C0392B"}
        return {"season": "Easter Season", "week_label": f"{ordinal} Week of Easter", "color": "gold", "color_hex": "#FFD700"}

    if baptism_lord < today < ash_wednesday:
        from datetime import timedelta as td
        ot_start = baptism_lord + td(days=1)
        week = week_num(ot_start, today)
        ordinal = _ordinal(week)
        return {"season": "Ordinary Time", "week_label": f"{ordinal} Week in Ordinary Time", "color": "green", "color_hex": "#2E7D32"}

    if pentecost < today < advent_start:
        from datetime import timedelta as td
        christ_king = advent_start - td(days=7)
        days_to_ck = (christ_king - today).days
        week_from_end = math.ceil(days_to_ck / 7)
        week = 34 - week_from_end
        week = max(8, min(34, week))
        ordinal = _ordinal(week)
        if today == trinity_sunday:
            return {"season": "Ordinary Time", "week_label": "Trinity Sunday", "color": "gold", "color_hex": "#FFD700"}
        if today == corpus_christi:
            return {"season": "Ordinary Time", "week_label": "Corpus Christi", "color": "gold", "color_hex": "#FFD700"}
        return {"season": "Ordinary Time", "week_label": f"{ordinal} Week in Ordinary Time", "color": "green", "color_hex": "#2E7D32"}

    if advent_start_prev <= today < date(year, 1, 1):
        week = week_num(advent_start_prev, today)
        ordinal = ["1st", "2nd", "3rd", "4th"][min(week - 1, 3)]
        return {"season": "Advent", "week_label": f"{ordinal} Week of Advent", "color": "purple", "color_hex": "#6B2D8B"}

    return {"season": "Ordinary Time", "week_label": "Ordinary Time", "color": "green", "color_hex": "#2E7D32"}

# ---------------------------------------------------------------------------
# Migration: add new columns safely on startup
# ---------------------------------------------------------------------------

def _safe_migrate():
    """Add any missing columns to existing Neon tables without crashing."""
    migrations = [
        # SiteSettings new music columns
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS music_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS music_title VARCHAR(300) DEFAULT 'Sacred Cathedral Instrumental'",
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS music_url VARCHAR(1000) DEFAULT 'https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3'",
        # Application table migration from old member_application schema
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS full_name VARCHAR(200)",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS email VARCHAR(300)",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS verse_sent TEXT",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS age INTEGER",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS contact VARCHAR(200)",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS ministry VARCHAR(200)",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS experience TEXT",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS note TEXT",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'Pending'",
        "ALTER TABLE application ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
    ]
    # Only run on PostgreSQL (Neon); SQLite uses IF NOT EXISTS differently
    if "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]:
        for stmt in migrations:
            try:
                db.session.execute(text(stmt))
            except Exception:
                db.session.rollback()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def seed_database():
    if SiteSettings.query.first():
        return

    settings = SiteSettings(
        site_name="Liturgical Club",
        tagline="Serving God Through Sacred Liturgy",
        hero_title="Welcome to the Liturgical Club",
        hero_subtitle="A community of young ministers dedicated to the beauty of Catholic worship",
        about_text=(
            "The Liturgical Club is a student-led organization committed to serving at Mass, "
            "promoting reverence in worship, and forming disciples who understand the richness "
            "of Catholic liturgical tradition. We serve as altar servers, lectors, choir members, "
            "and ushers — all united by one mission: to give glory to God."
        ),
        footer_rainbow_text="Liturgical Club · Ora et Labora · Serving with Joy and Faith",
        contact_email="liturgicalclub@example.com",
        contact_phone="+63 912 345 6789",
        facebook_url="https://facebook.com/liturgicalclub",
        music_enabled=True,
        music_title="Sacred Cathedral Instrumental",
        music_url="https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
    )
    db.session.add(settings)

    cards = [
        HomepageInfoCard(title="Our Patron Saint", body="We are proudly under the patronage of St. Tarcisius, the young martyr of the Eucharist, who died protecting the Blessed Sacrament. His courage and devotion inspire every member to serve at the altar with the same love.", icon="✝", order_index=1),
        HomepageInfoCard(title="Our Mission", body="To form servant-ministers who participate actively and reverently in the Sacred Liturgy — the source and summit of Christian life — through dedicated service, prayer, and ongoing formation.", icon="⛪", order_index=2),
        HomepageInfoCard(title="Weekly Formation", body="Every week we gather for liturgical formation sessions covering rites, rubrics, sacred music, and the theology behind each part of the Mass. All members are expected to attend.", icon="📖", order_index=3),
        HomepageInfoCard(title="Community & Fellowship", body="Beyond the altar, we are a family. From retreats and recollections to community service and social events, we journey together in faith, fun, and friendship.", icon="🕊", order_index=4),
        HomepageInfoCard(title="Open to All", body="Any student who desires to serve God in the liturgy is welcome. No prior experience needed — only an open heart. We train, equip, and accompany every new member.", icon="🙏", order_index=5),
        HomepageInfoCard(title="Annual Events", body="We host the Annual Mass of Thanksgiving, the Feast of St. Tarcisius, the Holy Week Vigil service, and an end-of-year Liturgical Awards Night to celebrate our ministers.", icon="🕯", order_index=6),
    ]
    for c in cards:
        db.session.add(c)

    ministries = [
        Ministry(name="Altar Servers", description="The core of our club — young men and women who assist the priest at the altar during Holy Mass, carrying the cross, candles, and sacred vessels with reverence and precision.", order_index=1),
        Ministry(name="Lectors & Commentators", description="Proclaim the Word of God with clarity and conviction. Lectors prepare diligently to read the Scriptures, while commentators guide the congregation through the liturgy.", order_index=2),
        Ministry(name="Liturgical Choir", description="Music ministers who lead the assembly in sacred song. The choir sings at Sunday Masses, feast days, and special liturgical celebrations throughout the year.", order_index=3),
        Ministry(name="Extraordinary Ministers", description="Trained ministers who assist in the distribution of Holy Communion during large celebrations. They serve with deep reverence for the Eucharist.", order_index=4),
    ]
    for m in ministries:
        db.session.add(m)

    schedules = [
        Schedule(title="Sunday Mass Service", day_time="Every Sunday, 8:00 AM", location="School Chapel", description="All altar servers rotate on the Sunday morning Mass schedule.", order_index=1),
        Schedule(title="Weekly Formation Meeting", day_time="Every Wednesday, 3:30 PM", location="Sacristy / AVR", description="Liturgical formation, rubrics review, and announcements for all members.", order_index=2),
        Schedule(title="Choir Rehearsal", day_time="Every Friday, 4:00 PM", location="Music Room", description="Choir and cantors rehearse music for the upcoming Sunday Mass and special celebrations.", order_index=3),
        Schedule(title="Monthly Recollection", day_time="First Saturday of the Month, 7:00 AM", location="School Chapel", description="A time for the whole club to pray, reflect, and renew our commitment to liturgical service.", order_index=4),
    ]
    for s in schedules:
        db.session.add(s)

    gallery_items = [
        GalleryItem(title="Easter Vigil 2026", image_url="https://images.unsplash.com/photo-1543702303-c14b1c9d2f0d?w=800", caption="Members serving at the glorious Easter Vigil Mass.", order_index=1),
        GalleryItem(title="Feast of St. Tarcisius", image_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800", caption="Annual celebration of our patron saint with a solemn Mass and procession.", order_index=2),
        GalleryItem(title="Formation Workshop", image_url="https://images.unsplash.com/photo-1529070538774-1843cb3265df?w=800", caption="Intensive liturgical formation day for new and returning members.", order_index=3),
        GalleryItem(title="Christmas Midnight Mass", image_url="https://images.unsplash.com/photo-1512389098783-66b81f86e199?w=800", caption="Servers and choir at the beautiful Midnight Mass on Christmas Eve.", order_index=4),
    ]
    for g in gallery_items:
        db.session.add(g)

    officers = [
        Officer(name="Maria Santos", position="President", bio="A senior member who has served in the Liturgical Club for four years, Maria leads with faith and dedication.", order_index=1),
        Officer(name="Juan dela Cruz", position="Vice President for Ministries", bio="Coordinates all ministry schedules and ensures every member is properly trained and assigned.", order_index=2),
        Officer(name="Ana Reyes", position="Secretary & Choir Director", bio="Manages club records and leads the liturgical choir with an ear for sacred beauty.", order_index=3),
    ]
    for o in officers:
        db.session.add(o)

    db.session.commit()

# ---------------------------------------------------------------------------
# Keep-alive daemon
# ---------------------------------------------------------------------------

def _keep_alive():
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not render_url:
        return
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(f"{render_url}/health", timeout=10)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Data serialization helpers
# ---------------------------------------------------------------------------

def _settings_dict(s: SiteSettings) -> dict:
    return {
        "id": s.id,
        "site_name": s.site_name or "",
        "tagline": s.tagline or "",
        "hero_title": s.hero_title or "",
        "hero_subtitle": s.hero_subtitle or "",
        "hero_image_url": s.hero_image_url or "",
        "about_text": s.about_text or "",
        "footer_rainbow_text": s.footer_rainbow_text or "",
        "background_music_url": s.background_music_url or "",
        "music_enabled": bool(s.music_enabled),
        "music_title": s.music_title or "Sacred Cathedral Instrumental",
        "music_url": s.music_url or "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
        "contact_email": s.contact_email or "",
        "contact_phone": s.contact_phone or "",
        "facebook_url": s.facebook_url or "",
        "liturgical_override_enabled": bool(s.liturgical_override_enabled),
        "liturgical_override_text": s.liturgical_override_text or "",
        "liturgical_override_color": s.liturgical_override_color or "green",
    }


def _card_dict(c: HomepageInfoCard) -> dict:
    return {
        "id": c.id,
        "title": c.title or "",
        "body": c.body or "",
        "icon": c.icon or "✝",
        "order_index": c.order_index or 0,
    }


def _ministry_dict(m: Ministry) -> dict:
    return {
        "id": m.id,
        "name": m.name or "",
        "description": m.description or "",
        "image_url": m.image_url or "",
        "order_index": m.order_index or 0,
    }


def _schedule_dict(s: Schedule) -> dict:
    return {
        "id": s.id,
        "title": s.title or "",
        "day_time": s.day_time or "",
        "location": s.location or "",
        "description": s.description or "",
        "order_index": s.order_index or 0,
    }


def _gallery_dict(g: GalleryItem) -> dict:
    return {
        "id": g.id,
        "title": g.title or "",
        "image_url": g.image_url or "",
        "caption": g.caption or "",
        "order_index": g.order_index or 0,
    }


def _officer_dict(o: Officer) -> dict:
    return {
        "id": o.id,
        "name": o.name or "",
        "position": o.position or "",
        "image_url": o.image_url or "",
        "bio": o.bio or "",
        "order_index": o.order_index or 0,
    }


def _app_dict(a: Application) -> dict:
    return {
        "id": a.id,
        "full_name": a.full_name or "",
        "email": a.email or "",
        "age": a.age,
        "contact": a.contact or "",
        "ministry": a.ministry or "",
        "experience": a.experience or "",
        "note": a.note or "",
        "verse_sent": a.verse_sent or "",
        "status": a.status or "Pending",
        "created_at": a.created_at.isoformat() if a.created_at else "",
    }


def _get_liturgical_display(settings: SiteSettings) -> dict:
    if settings.liturgical_override_enabled and settings.liturgical_override_text:
        color_map = {
            "green": "#2E7D32", "purple": "#6B2D8B", "gold": "#FFD700",
            "red": "#C0392B", "white": "#F5F5F5", "rose": "#FF6B9D"
        }
        return {
            "season": "Override",
            "week_label": settings.liturgical_override_text,
            "color": settings.liturgical_override_color,
            "color_hex": color_map.get(settings.liturgical_override_color, "#2E7D32"),
            "is_override": True,
        }
    info = get_liturgical_info()
    info["is_override"] = False
    return info


def _get_all_data(initial_page: str = "home") -> dict:
    settings = SiteSettings.query.first()
    cards = HomepageInfoCard.query.order_by(HomepageInfoCard.order_index).all()
    ministries = Ministry.query.order_by(Ministry.order_index).all()
    schedules = Schedule.query.order_by(Schedule.order_index).all()
    gallery = GalleryItem.query.order_by(GalleryItem.order_index).all()
    officers = Officer.query.order_by(Officer.order_index).all()
    liturgical = _get_liturgical_display(settings)
    return {
        "initial_page": initial_page,
        "settings": json.dumps(_settings_dict(settings)),
        "cards": json.dumps([_card_dict(c) for c in cards]),
        "ministries": json.dumps([_ministry_dict(m) for m in ministries]),
        "schedules": json.dumps([_schedule_dict(s) for s in schedules]),
        "gallery": json.dumps([_gallery_dict(g) for g in gallery]),
        "officers": json.dumps([_officer_dict(o) for o in officers]),
        "liturgical": json.dumps(liturgical),
    }

# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    return render_template("index.html", **_get_all_data("home"))


@app.route("/about")
def about():
    return render_template("index.html", **_get_all_data("about"))


@app.route("/ministries")
def ministries_page():
    return render_template("index.html", **_get_all_data("ministries"))


@app.route("/schedules")
def schedules_page():
    return render_template("index.html", **_get_all_data("schedules"))


@app.route("/gallery")
def gallery_page():
    return render_template("index.html", **_get_all_data("gallery"))


@app.route("/join")
def join():
    return render_template("index.html", **_get_all_data("join"))


@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.get_json(silent=True) or request.form.to_dict()

    full_name = (data.get("full_name") or data.get("name") or "").strip()
    email = (data.get("email") or "").strip()

    if not full_name:
        return jsonify({"success": False, "error": "full_name is required"}), 400
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "A valid email is required"}), 400

    chosen = random.choice(CATHOLIC_BIBLE_VERSES)
    verse_text = f'"{chosen["verse"]}" — {chosen["reference"]}'

    try:
        age_val = int(data.get("age", 0)) if data.get("age") else None
    except (ValueError, TypeError):
        age_val = None

    app_entry = Application(
        full_name=full_name,
        email=email,
        age=age_val,
        contact=data.get("contact", ""),
        ministry=data.get("ministry", ""),
        experience=data.get("experience", ""),
        note=data.get("note", ""),
        verse_sent=verse_text,
        status="Pending",
    )
    db.session.add(app_entry)
    db.session.commit()

    # Fire-and-forget email
    t = threading.Thread(
        target=_send_welcome_email,
        args=(full_name, email, chosen),
        daemon=True,
    )
    t.start()

    return jsonify({"success": True, "verse": verse_text}), 201

# ---------------------------------------------------------------------------
# Admin auth
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    settings = SiteSettings.query.first()
    cards = HomepageInfoCard.query.order_by(HomepageInfoCard.order_index).all()
    mins = Ministry.query.order_by(Ministry.order_index).all()
    scheds = Schedule.query.order_by(Schedule.order_index).all()
    gals = GalleryItem.query.order_by(GalleryItem.order_index).all()
    offs = Officer.query.order_by(Officer.order_index).all()
    apps = Application.query.order_by(Application.created_at.desc()).all()
    liturgical = get_liturgical_info()
    return render_template(
        "admin.html",
        settings=settings,
        cards=cards,
        ministries=mins,
        schedules=scheds,
        gallery=gals,
        officers=offs,
        applications=apps,
        liturgical=liturgical,
    )

# ---------------------------------------------------------------------------
# Admin CRUD — settings
# ---------------------------------------------------------------------------

@app.route("/admin/save/settings", methods=["POST"])
@admin_required
def admin_save_settings():
    s = SiteSettings.query.first()
    s.site_name = request.form.get("site_name", s.site_name)
    s.tagline = request.form.get("tagline", s.tagline)
    s.hero_title = request.form.get("hero_title", s.hero_title)
    s.hero_subtitle = request.form.get("hero_subtitle", s.hero_subtitle)
    s.about_text = request.form.get("about_text", s.about_text)
    s.footer_rainbow_text = request.form.get("footer_rainbow_text", s.footer_rainbow_text)
    s.contact_email = request.form.get("contact_email", s.contact_email)
    s.contact_phone = request.form.get("contact_phone", s.contact_phone)
    s.facebook_url = request.form.get("facebook_url", s.facebook_url)
    s.liturgical_override_enabled = request.form.get("liturgical_override_enabled") == "on"
    s.liturgical_override_text = request.form.get("liturgical_override_text", s.liturgical_override_text)
    s.liturgical_override_color = request.form.get("liturgical_override_color", s.liturgical_override_color)

    # Music settings
    s.music_enabled = request.form.get("music_enabled") == "on"
    s.music_title = request.form.get("music_title", s.music_title)
    music_url_field = request.form.get("music_url", "").strip()
    if music_url_field:
        s.music_url = music_url_field
    elif "music_file" in request.files and request.files["music_file"].filename:
        url = upload_file(request.files["music_file"])
        if url:
            s.music_url = url

    # Hero image
    hero_img_url = request.form.get("hero_image_url", "").strip()
    if hero_img_url:
        s.hero_image_url = hero_img_url
    elif "hero_image_file" in request.files and request.files["hero_image_file"].filename:
        url = upload_file(request.files["hero_image_file"])
        if url:
            s.hero_image_url = url

    # Legacy background_music_url kept in sync
    s.background_music_url = s.music_url

    db.session.commit()
    flash("Settings saved.", "success")
    return redirect(url_for("admin_dashboard") + "#settings")

# ---------------------------------------------------------------------------
# Admin CRUD — cards
# ---------------------------------------------------------------------------

@app.route("/admin/save/cards", methods=["POST"])
@admin_required
def admin_save_cards():
    card_id = request.form.get("id")
    if card_id:
        c = HomepageInfoCard.query.get(int(card_id))
        if not c:
            flash("Card not found.", "error")
            return redirect(url_for("admin_dashboard") + "#cards")
    else:
        c = HomepageInfoCard()
        db.session.add(c)
    c.title = request.form.get("title", "")
    c.body = request.form.get("body", "")
    c.icon = request.form.get("icon", "✝")
    c.order_index = int(request.form.get("order_index", 0))
    db.session.commit()
    flash("Card saved.", "success")
    return redirect(url_for("admin_dashboard") + "#cards")


@app.route("/admin/delete/cards/<int:item_id>", methods=["POST"])
@admin_required
def admin_delete_card(item_id):
    c = HomepageInfoCard.query.get_or_404(item_id)
    db.session.delete(c)
    db.session.commit()
    flash("Card deleted.", "success")
    return redirect(url_for("admin_dashboard") + "#cards")

# ---------------------------------------------------------------------------
# Admin CRUD — ministries
# ---------------------------------------------------------------------------

@app.route("/admin/save/ministries", methods=["POST"])
@admin_required
def admin_save_ministry():
    mid = request.form.get("id")
    if mid:
        m = Ministry.query.get(int(mid))
        if not m:
            flash("Ministry not found.", "error")
            return redirect(url_for("admin_dashboard") + "#ministries")
    else:
        m = Ministry()
        db.session.add(m)
    m.name = request.form.get("name", "")
    m.description = request.form.get("description", "")
    m.order_index = int(request.form.get("order_index", 0))
    img_url = request.form.get("image_url", "").strip()
    if img_url:
        m.image_url = img_url
    elif "image_file" in request.files and request.files["image_file"].filename:
        url = upload_file(request.files["image_file"])
        if url:
            m.image_url = url
    db.session.commit()
    flash("Ministry saved.", "success")
    return redirect(url_for("admin_dashboard") + "#ministries")


@app.route("/admin/delete/ministries/<int:item_id>", methods=["POST"])
@admin_required
def admin_delete_ministry(item_id):
    m = Ministry.query.get_or_404(item_id)
    db.session.delete(m)
    db.session.commit()
    flash("Ministry deleted.", "success")
    return redirect(url_for("admin_dashboard") + "#ministries")

# ---------------------------------------------------------------------------
# Admin CRUD — schedules
# ---------------------------------------------------------------------------

@app.route("/admin/save/schedules", methods=["POST"])
@admin_required
def admin_save_schedule():
    sid = request.form.get("id")
    if sid:
        s = Schedule.query.get(int(sid))
        if not s:
            flash("Schedule not found.", "error")
            return redirect(url_for("admin_dashboard") + "#schedules")
    else:
        s = Schedule()
        db.session.add(s)
    s.title = request.form.get("title", "")
    s.day_time = request.form.get("day_time", "")
    s.location = request.form.get("location", "")
    s.description = request.form.get("description", "")
    s.order_index = int(request.form.get("order_index", 0))
    db.session.commit()
    flash("Schedule saved.", "success")
    return redirect(url_for("admin_dashboard") + "#schedules")


@app.route("/admin/delete/schedules/<int:item_id>", methods=["POST"])
@admin_required
def admin_delete_schedule(item_id):
    s = Schedule.query.get_or_404(item_id)
    db.session.delete(s)
    db.session.commit()
    flash("Schedule deleted.", "success")
    return redirect(url_for("admin_dashboard") + "#schedules")

# ---------------------------------------------------------------------------
# Admin CRUD — gallery
# ---------------------------------------------------------------------------

@app.route("/admin/save/gallery", methods=["POST"])
@admin_required
def admin_save_gallery():
    gid = request.form.get("id")
    if gid:
        g = GalleryItem.query.get(int(gid))
        if not g:
            flash("Gallery item not found.", "error")
            return redirect(url_for("admin_dashboard") + "#gallery")
    else:
        g = GalleryItem()
        db.session.add(g)
    g.title = request.form.get("title", "")
    g.caption = request.form.get("caption", "")
    g.order_index = int(request.form.get("order_index", 0))
    img_url = request.form.get("image_url", "").strip()
    if img_url:
        g.image_url = img_url
    elif "image_file" in request.files and request.files["image_file"].filename:
        url = upload_file(request.files["image_file"])
        if url:
            g.image_url = url
    db.session.commit()
    flash("Gallery item saved.", "success")
    return redirect(url_for("admin_dashboard") + "#gallery")


@app.route("/admin/delete/gallery/<int:item_id>", methods=["POST"])
@admin_required
def admin_delete_gallery(item_id):
    g = GalleryItem.query.get_or_404(item_id)
    db.session.delete(g)
    db.session.commit()
    flash("Gallery item deleted.", "success")
    return redirect(url_for("admin_dashboard") + "#gallery")

# ---------------------------------------------------------------------------
# Admin CRUD — officers
# ---------------------------------------------------------------------------

@app.route("/admin/save/officers", methods=["POST"])
@admin_required
def admin_save_officer():
    oid = request.form.get("id")
    if oid:
        o = Officer.query.get(int(oid))
        if not o:
            flash("Officer not found.", "error")
            return redirect(url_for("admin_dashboard") + "#officers")
    else:
        o = Officer()
        db.session.add(o)
    o.name = request.form.get("name", "")
    o.position = request.form.get("position", "")
    o.bio = request.form.get("bio", "")
    o.order_index = int(request.form.get("order_index", 0))
    img_url = request.form.get("image_url", "").strip()
    if img_url:
        o.image_url = img_url
    elif "image_file" in request.files and request.files["image_file"].filename:
        url = upload_file(request.files["image_file"])
        if url:
            o.image_url = url
    db.session.commit()
    flash("Officer saved.", "success")
    return redirect(url_for("admin_dashboard") + "#officers")


@app.route("/admin/delete/officers/<int:item_id>", methods=["POST"])
@admin_required
def admin_delete_officer(item_id):
    o = Officer.query.get_or_404(item_id)
    db.session.delete(o)
    db.session.commit()
    flash("Officer deleted.", "success")
    return redirect(url_for("admin_dashboard") + "#officers")

# ---------------------------------------------------------------------------
# Admin CRUD — applications
# ---------------------------------------------------------------------------

@app.route("/admin/save/applications", methods=["POST"])
@admin_required
def admin_save_application():
    aid = request.form.get("id")
    if not aid:
        flash("No application ID.", "error")
        return redirect(url_for("admin_dashboard") + "#applications")
    a = Application.query.get(int(aid))
    if not a:
        flash("Application not found.", "error")
        return redirect(url_for("admin_dashboard") + "#applications")
    a.status = request.form.get("status", a.status)
    db.session.commit()
    flash("Application updated.", "success")
    return redirect(url_for("admin_dashboard") + "#applications")


@app.route("/admin/delete/applications/<int:item_id>", methods=["POST"])
@admin_required
def admin_delete_application(item_id):
    a = Application.query.get_or_404(item_id)
    db.session.delete(a)
    db.session.commit()
    flash("Application deleted.", "success")
    return redirect(url_for("admin_dashboard") + "#applications")

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()
    _safe_migrate()
    seed_database()

_keep_alive_thread = threading.Thread(target=_keep_alive, daemon=True)
_keep_alive_thread.start()

if __name__ == "__main__":
    app.run(debug=True)
