"""
BelaBox Discord Bot
- Postet neue Twitch Clips von slumg1 automatisch als Embed
- BelaBox Audio-Input Steuerung (wird später ergänzt)
Benoetigt: pip install discord.py requests
"""

import discord
import requests
import asyncio
import json
import os
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════ Konfiguration ════
# Alle sensiblen Daten kommen aus Umgebungsvariablen (Railway / .env)

DISCORD_TOKEN      = os.environ["DISCORD_TOKEN"]
TWITCH_CLIENT_ID   = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

# Channel IDs (keine Secrets, können im Code stehen)
CHANNEL_CLIPS      = 1307038131668652103
CHANNEL_BB_AUDIO_1 = 1127204481419968613
CHANNEL_BB_AUDIO_2 = 1303959861385625661

TWITCH_CHANNEL = "slumg1"
BELABOX_KEY    = "7DMVJ0mAklNzzjY9ayXzLjde5Hjsul"
BELABOX_WS     = "wss://remote.belabox.net/ws/remote"

CHECK_INTERVAL = 60
SEEN_FILE      = "seen_clips.json"


# ═══════════════════════════════════════════════════════════ Twitch API ═══════

class TwitchAPI:
    def __init__(self):
        self.access_token   = None
        self.broadcaster_id = None

    def get_token(self):
        resp = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id":     TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type":    "client_credentials"
            }, timeout=10)
        resp.raise_for_status()
        self.access_token = resp.json()["access_token"]

    def _headers(self):
        return {
            "Client-ID":     TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {self.access_token}"
        }

    def get_broadcaster_id(self, username):
        resp = requests.get(
            "https://api.twitch.tv/helix/users",
            headers=self._headers(),
            params={"login": username},
            timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            self.broadcaster_id = data[0]["id"]
            return self.broadcaster_id
        return None

    def get_recent_clips(self, broadcaster_id, first=20):
        resp = requests.get(
            "https://api.twitch.tv/helix/clips",
            headers=self._headers(),
            params={"broadcaster_id": broadcaster_id, "first": first},
            timeout=10)
        if resp.status_code == 401:
            self.get_token()
            resp = requests.get(
                "https://api.twitch.tv/helix/clips",
                headers=self._headers(),
                params={"broadcaster_id": broadcaster_id, "first": first},
                timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])


# ═══════════════════════════════════════════════════════════ Seen Clips ═══════

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except:
            pass
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


# ══════════════════════════════════════════ BelaBox Audio Input Buttons ═══════

class AudioInputView(discord.ui.View):
    """
    Buttons für BelaBox Audio-Input Steuerung.
    Die eigentliche Logik wird später ergänzt sobald die
    WebSocket-Befehle bekannt sind.
    """
    def __init__(self):
        super().__init__(timeout=None)  # Buttons bleiben dauerhaft aktiv

    # ── Platzhalter-Buttons (werden später mit echten Befehlen befüllt)
    @discord.ui.button(label="🎤 Audio Input 1", style=discord.ButtonStyle.primary,  custom_id="bb_audio_1")
    async def audio_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # TODO: BelaBox WebSocket Befehl hier einfügen
        await interaction.followup.send("⏳ Audio Input 1 wird gesetzt... (noch nicht implementiert)", ephemeral=True)

    @discord.ui.button(label="🎵 Audio Input 2", style=discord.ButtonStyle.primary,  custom_id="bb_audio_2")
    async def audio_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # TODO: BelaBox WebSocket Befehl hier einfügen
        await interaction.followup.send("⏳ Audio Input 2 wird gesetzt... (noch nicht implementiert)", ephemeral=True)

    @discord.ui.button(label="🔊 Audio Input 3", style=discord.ButtonStyle.primary,  custom_id="bb_audio_3")
    async def audio_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # TODO: BelaBox WebSocket Befehl hier einfügen
        await interaction.followup.send("⏳ Audio Input 3 wird gesetzt... (noch nicht implementiert)", ephemeral=True)

    @discord.ui.button(label="📊 BB Status", style=discord.ButtonStyle.secondary, custom_id="bb_status")
    async def bb_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("📊 BelaBox Status: wird implementiert...", ephemeral=True)


# ═══════════════════════════════════════════════════════════ Clip Embed ═══════

def make_clip_embed(clip):
    created = clip.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        ts = f"<t:{int(dt.timestamp())}:R>"
    except:
        ts = created

    embed = discord.Embed(
        title       = clip.get("title", "Neuer Clip"),
        url         = clip.get("url", ""),
        description = f"📺 Neuer Clip auf **slumg1**! {ts}",
        color       = discord.Color.purple()
    )
    embed.set_image(url=clip.get("thumbnail_url", ""))
    embed.add_field(name="✂️ Erstellt von", value=clip.get("creator_name", "?"),   inline=True)
    embed.add_field(name="👁️ Views",        value=str(clip.get("view_count", 0)),  inline=True)
    embed.add_field(name="⏱️ Dauer",        value=f"{clip.get('duration', 0)}s",   inline=True)
    embed.set_footer(text="Twitch Clip • slumg1")
    return embed


# ═══════════════════════════════════════════════════════════ Discord Bot ══════

intents    = discord.Intents.default()
bot        = discord.Client(intents=intents)
twitch_api = TwitchAPI()
seen_clips = load_seen()


@bot.event
async def on_ready():
    print(f"✅ Bot eingeloggt als {bot.user}")
    print(f"🎬 Clip Channel:    {CHANNEL_CLIPS}")
    print(f"🎙️ BB Audio Ch. 1: {CHANNEL_BB_AUDIO_1}")
    print(f"🎙️ BB Audio Ch. 2: {CHANNEL_BB_AUDIO_2}")

    # Persistent Views registrieren damit Buttons nach Neustart funktionieren
    bot.add_view(AudioInputView())

    # Twitch Setup
    try:
        twitch_api.get_token()
        bid = twitch_api.get_broadcaster_id(TWITCH_CHANNEL)
        if not bid:
            print(f"❌ Twitch Channel '{TWITCH_CHANNEL}' nicht gefunden!")
            return
        print(f"✅ Twitch Broadcaster ID: {bid}")
    except Exception as e:
        print(f"❌ Twitch API Fehler: {e}")
        return

    # Beim ersten Start: vorhandene Clips als gesehen markieren
    global seen_clips
    if not seen_clips:
        print("📋 Erster Start – markiere vorhandene Clips...")
        try:
            clips = twitch_api.get_recent_clips(bid)
            for clip in clips:
                seen_clips.add(clip["id"])
            save_seen(seen_clips)
            print(f"   {len(seen_clips)} Clips markiert")
        except Exception as e:
            print(f"❌ Fehler: {e}")

    # Audio-Steuerungs-Nachricht in beide Channels schicken
    for ch_id in [CHANNEL_BB_AUDIO_1, CHANNEL_BB_AUDIO_2]:
        ch = bot.get_channel(ch_id)
        if ch:
            try:
                embed = discord.Embed(
                    title       = "🎙️ BelaBox Audio Steuerung",
                    description = "Wähle den Audio-Input für die BelaBox:",
                    color       = discord.Color.orange()
                )
                embed.set_footer(text="Die Buttons werden aktiv sobald die BelaBox WebSocket-Befehle bekannt sind")
                await ch.send(embed=embed, view=AudioInputView())
                print(f"✅ Audio-Steuerung gepostet in Channel {ch_id}")
            except Exception as e:
                print(f"❌ Fehler beim Posten in {ch_id}: {e}")

    # Clip-Check Loop starten
    bot.loop.create_task(clip_check_loop(bid))


async def clip_check_loop(broadcaster_id):
    global seen_clips
    channel = bot.get_channel(CHANNEL_CLIPS)
    if not channel:
        print(f"❌ Clip-Channel {CHANNEL_CLIPS} nicht gefunden!")
        return

    print(f"🔄 Clip-Check alle {CHECK_INTERVAL}s...")

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            clips      = twitch_api.get_recent_clips(broadcaster_id)
            new_clips  = [c for c in clips if c["id"] not in seen_clips]

            for clip in reversed(new_clips):
                print(f"🎬 Neuer Clip: {clip['title']} von {clip['creator_name']}")
                embed = make_clip_embed(clip)
                await channel.send(embed=embed)
                seen_clips.add(clip["id"])

            if new_clips:
                save_seen(seen_clips)

        except Exception as e:
            print(f"❌ Clip-Check Fehler: {e}")


# ═══════════════════════════════════════════════════════════════ Start ════════

if __name__ == "__main__":
    print("🤖 Starte BelaBox Discord Bot...")
    bot.run(DISCORD_TOKEN)
