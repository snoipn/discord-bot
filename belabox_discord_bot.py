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
CHANNEL_CLIPS        = 1307038131668652103   # Twitch clips
CHANNEL_KICK_CLIPS   = 1307038156905910302   # Kick clips
CHANNEL_BB_AUDIO_1   = 1127204481419968613
CHANNEL_BB_AUDIO_2   = 1303959861385625661

TWITCH_CHANNEL = "slumg1"
KICK_CHANNEL   = "slumg"
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


# ═══════════════════════════════════════════════════════════════ Kick API ══════

class KickAPI:
    """Kick has no official API – uses the public unofficial endpoint."""

    def get_channel_id(self, username):
        resp = requests.get(
            f"https://kick.com/api/v1/channels/{username}",
            headers={"Accept": "application/json",
                     "User-Agent": "Mozilla/5.0"},
            timeout=10)
        resp.raise_for_status()
        return resp.json().get("id")

    def get_recent_clips(self, username, cursor=None):
        from datetime import timedelta
        params = {"sort": "date", "time": "day"}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            f"https://kick.com/api/v2/channels/{username}/clips",
            headers={"Accept": "application/json",
                     "User-Agent": "Mozilla/5.0"},
            params=params,
            timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # API returns {"clips": [...], "nextCursor": ...}
        clips = data.get("clips", data.get("data", []))
        # Filter to last 10 minutes
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        recent = []
        for clip in clips:
            created = clip.get("created_at", clip.get("clip_url", ""))
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if dt >= cutoff:
                    recent.append(clip)
            except:
                recent.append(clip)  # include if can't parse date
        return recent


def make_kick_embed(clip):
    created = clip.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        ts = f"<t:{int(dt.timestamp())}:f>"
    except:
        ts = created

    creator  = clip.get("creator", {})
    creator_name = creator.get("username", clip.get("channel", {}).get("username", "?")) if isinstance(creator, dict) else str(creator)
    title    = clip.get("title", "New Clip")
    clip_url = clip.get("clip_url", clip.get("url", "https://kick.com"))
    thumb    = clip.get("thumbnail_url", clip.get("thumbnail", ""))

    embed = discord.Embed(
        description = f"**{creator_name}** clipped\n## {title}",
        url         = clip_url,
        color       = 0x53FC18  # Kick green
    )
    if thumb:
        embed.set_image(url=thumb)
    embed.set_footer(text=ts)
    return embed


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
        ts = f"<t:{int(dt.timestamp())}:f>"  # full date + time, e.g. "March 15, 2026 11:29 PM"
    except:
        ts = created

    embed = discord.Embed(
        description = f"**{clip.get('creator_name', '?')}** clipped\n## {clip.get('title', 'New Clip')}",
        url         = clip.get("url", ""),
        color       = 0x9146FF  # Twitch purple
    )
    embed.set_image(url=clip.get("thumbnail_url", ""))
    embed.set_footer(text=ts)
    return embed


# ═══════════════════════════════════════════════════════════ Discord Bot ══════

intents          = discord.Intents.default()
intents.messages = True

bot        = discord.Client(intents=intents)
tree       = discord.app_commands.CommandTree(bot)
twitch_api = TwitchAPI()
kick_api   = KickAPI()
seen_clips      = set()
seen_kick_clips = set()


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
    print(f"🎬 Twitch Clip Channel: {CHANNEL_CLIPS}")
    print(f"🎬 Kick Clip Channel:   {CHANNEL_KICK_CLIPS}")
    print(f"🎙️ BB Audio Ch. 1:     {CHANNEL_BB_AUDIO_1}")
    print(f"🎙️ BB Audio Ch. 2:     {CHANNEL_BB_AUDIO_2}")

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

    # Start both clip check loops
    bot.loop.create_task(clip_check_loop(bid))
    bot.loop.create_task(kick_clip_check_loop())


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


async def kick_clip_check_loop():
    global seen_kick_clips
    channel = bot.get_channel(CHANNEL_KICK_CLIPS)
    if not channel:
        print(f"❌ Kick Clip Channel {CHANNEL_KICK_CLIPS} not found!")
        return

    print(f"🔄 Kick Clip-Check every {CHECK_INTERVAL}s...")

    # Mark existing clips as seen on first run
    try:
        clips = kick_api.get_recent_clips(KICK_CHANNEL)
        for clip in clips:
            seen_kick_clips.add(clip.get("id", clip.get("clip_url", "")))
        print(f"   {len(seen_kick_clips)} Kick clips marked as seen")
    except Exception as e:
        print(f"❌ Kick initial check error: {e}")

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            print(f"🔍 Checking Kick clips... (known: {len(seen_kick_clips)})")
            clips = kick_api.get_recent_clips(KICK_CHANNEL)
            print(f"   Kick returned {len(clips)} clips")
            new_clips = [c for c in clips if c.get("id", c.get("clip_url", "")) not in seen_kick_clips]
            print(f"   New Kick clips: {len(new_clips)}")

            for clip in reversed(new_clips):
                clip_id = clip.get("id", clip.get("clip_url", ""))
                title   = clip.get("title", "New Clip")
                creator = clip.get("creator", {})
                name    = creator.get("username", "?") if isinstance(creator, dict) else str(creator)
                print(f"🎬 New Kick clip: {title} by {name}")
                embed = make_kick_embed(clip)
                await channel.send(embed=embed)
                seen_kick_clips.add(clip_id)

        except Exception as e:
            print(f"❌ Kick Clip-Check error: {e}")


# ═══════════════════════════════════════════════════════════════ Start ════════

if __name__ == "__main__":
    print("🤖 Starte BelaBox Discord Bot...")
    bot.run(DISCORD_TOKEN)
