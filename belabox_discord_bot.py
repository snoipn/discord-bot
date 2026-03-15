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

DISCORD_TOKEN        = os.environ.get("DISCORD_TOKEN", "")
TWITCH_CLIENT_ID     = os.environ.get("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN nicht gesetzt!")
if not TWITCH_CLIENT_ID:
    raise RuntimeError("TWITCH_CLIENT_ID nicht gesetzt!")
if not TWITCH_CLIENT_SECRET:
    raise RuntimeError("TWITCH_CLIENT_SECRET nicht gesetzt!")

# Channel IDs
CHANNEL_CLIPS      = 1307038131668652103
CHANNEL_BB_AUDIO_1 = 1127204481419968613
CHANNEL_BB_AUDIO_2 = 1303959861385625661

TWITCH_CHANNEL = "slumg1"
BELABOX_KEY    = "7DMVJ0mAklNzzjY9ayXzLjde5Hjsul"
BELABOX_WS     = "wss://remote.belabox.net/ws/remote"

CHECK_INTERVAL = 60
SEEN_FILE      = "seen_clips.json"

print(f"✅ DISCORD_TOKEN gesetzt: {bool(DISCORD_TOKEN)}")
print(f"✅ TWITCH_CLIENT_ID gesetzt: {bool(TWITCH_CLIENT_ID)}")
print(f"✅ TWITCH_CLIENT_SECRET gesetzt: {bool(TWITCH_CLIENT_SECRET)}")


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
        # Nur Clips der letzten 10 Minuten – so kommen ALLE neuen Clips, nicht nur populäre
        from datetime import timedelta
        now        = datetime.now(timezone.utc)
        started_at = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ended_at   = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "broadcaster_id": broadcaster_id,
            "first":          first,
            "started_at":     started_at,
            "ended_at":       ended_at
        }
        resp = requests.get(
            "https://api.twitch.tv/helix/clips",
            headers=self._headers(),
            params=params,
            timeout=10)
        if resp.status_code == 401:
            self.get_token()
            resp = requests.get(
                "https://api.twitch.tv/helix/clips",
                headers=self._headers(),
                params=params,
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
        await interaction.followup.send("⏳ Setting Audio Input 1... (not yet implemented)", ephemeral=True)

    @discord.ui.button(label="🎵 Audio Input 2", style=discord.ButtonStyle.primary,  custom_id="bb_audio_2")
    async def audio_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("⏳ Setting Audio Input 2... (not yet implemented)", ephemeral=True)

    @discord.ui.button(label="🔊 Audio Input 3", style=discord.ButtonStyle.primary,  custom_id="bb_audio_3")
    async def audio_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("⏳ Setting Audio Input 3... (not yet implemented)", ephemeral=True)

    @discord.ui.button(label="📊 BB Status", style=discord.ButtonStyle.secondary, custom_id="bb_status")
    async def bb_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("📊 BelaBox Status: coming soon...", ephemeral=True)


# ═══════════════════════════════════════════════════════════ Clip Embed ═══════

def make_clip_embed(clip):
    created = clip.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        ts = f"<t:{int(dt.timestamp())}:R>"
    except:
        ts = created

    embed = discord.Embed(
        title       = clip.get("title", "New Clip"),
        url         = clip.get("url", ""),
        description = f"📺 A new clip was created on **slumg1**! {ts}",
        color       = discord.Color.purple()
    )
    embed.set_image(url=clip.get("thumbnail_url", ""))
    embed.add_field(name="✂️ Clipped by", value=clip.get("creator_name", "?"),   inline=True)
    embed.add_field(name="👁️ Views",      value=str(clip.get("view_count", 0)),  inline=True)
    embed.add_field(name="⏱️ Duration",   value=f"{clip.get('duration', 0)}s",   inline=True)
    embed.set_footer(text="Twitch Clip • slumg1")
    return embed


# ═══════════════════════════════════════════════════════════ Discord Bot ══════

intents          = discord.Intents.default()
intents.messages = True

bot        = discord.Client(intents=intents)
tree       = discord.app_commands.CommandTree(bot)
twitch_api = TwitchAPI()
seen_clips = set()  # Always start fresh – only track clips from now on


@tree.command(name="audio", description="Show the BelaBox audio input control panel")
async def slash_audio(interaction: discord.Interaction):
    embed = discord.Embed(
        title       = "🎙️ BelaBox Audio Control",
        description = "Select the audio input for the BelaBox:",
        color       = discord.Color.orange()
    )
    embed.set_footer(text="Buttons will be active once the BelaBox WebSocket commands are known")
    await interaction.response.send_message(embed=embed, view=AudioInputView())


@tree.command(name="mic", description="Show the BelaBox audio input control panel")
async def slash_mic(interaction: discord.Interaction):
    embed = discord.Embed(
        title       = "🎙️ BelaBox Audio Control",
        description = "Select the audio input for the BelaBox:",
        color       = discord.Color.orange()
    )
    embed.set_footer(text="Buttons will be active once the BelaBox WebSocket commands are known")
    await interaction.response.send_message(embed=embed, view=AudioInputView())


@bot.event
async def on_ready():
    print(f"✅ Bot eingeloggt als {bot.user}")
    print(f"🎬 Clip Channel:    {CHANNEL_CLIPS}")
    print(f"🎙️ BB Audio Ch. 1: {CHANNEL_BB_AUDIO_1}")
    print(f"🎙️ BB Audio Ch. 2: {CHANNEL_BB_AUDIO_2}")

    # Sync slash commands
    await tree.sync()
    print("✅ Slash commands synced: /audio, /mic")

    # Persistent Views registrieren damit Buttons nach Neustart funktionieren
    bot.add_view(AudioInputView())
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

    # Beim ersten Start: nur Clips der letzten 24h als gesehen markieren
    global seen_clips
    if not seen_clips:
        print("📋 First start – marking existing clips as seen...")
        try:
            clips = twitch_api.get_recent_clips(bid)
            for clip in clips:
                seen_clips.add(clip["id"])
            save_seen(seen_clips)
            print(f"   {len(seen_clips)} clips marked as seen")
        except Exception as e:
            print(f"❌ Error: {e}")

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
            print(f"🔍 Checking for new clips... (known: {len(seen_clips)})")
            clips      = twitch_api.get_recent_clips(broadcaster_id)
            print(f"   Twitch returned {len(clips)} clips")
            if clips:
                print(f"   Newest clip: '{clips[0]['title']}' created {clips[0]['created_at']}")
            new_clips  = [c for c in clips if c["id"] not in seen_clips]
            print(f"   New clips: {len(new_clips)}")

            for clip in reversed(new_clips):
                print(f"🎬 New clip: {clip['title']} by {clip['creator_name']}")
                embed = make_clip_embed(clip)
                await channel.send(embed=embed)
                seen_clips.add(clip["id"])

            if new_clips:
                save_seen(seen_clips)

        except Exception as e:
            print(f"❌ Clip-Check error: {e}")


# ═══════════════════════════════════════════════════════════════ Start ════════

if __name__ == "__main__":
    print("🤖 Starte BelaBox Discord Bot...")
    bot.run(DISCORD_TOKEN)
