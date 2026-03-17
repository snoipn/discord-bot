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
import time
import threading
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════ Konfiguration ════

DISCORD_TOKEN        = os.environ.get("DISCORD_TOKEN", "")
TWITCH_CLIENT_ID     = os.environ.get("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")
BELABOX_KEY          = os.environ.get("BELABOX_KEY", "")
TG_TOKEN             = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID           = os.environ.get("TG_CHAT_ID", "")

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

    HEADERS = {
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://kick.com/",
        "Origin":          "https://kick.com",
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "sec-ch-ua":       '"Chromium";v="122", "Not(A:Brand";v="24"',
        "sec-ch-ua-mobile":"?0",
        "sec-fetch-dest":  "empty",
        "sec-fetch-mode":  "cors",
        "sec-fetch-site":  "same-origin",
    }

    def get_recent_clips(self, username):
        from datetime import timedelta
        resp = requests.get(
            f"https://kick.com/api/v2/channels/{username}/clips",
            headers=self.HEADERS,
            params={"sort": "date", "time": "day"},
            timeout=10)
        resp.raise_for_status()
        data  = resp.json()
        clips = data.get("clips", data.get("data", []))
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        recent = []
        for clip in clips:
            created = clip.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if dt >= cutoff:
                    recent.append(clip)
            except:
                recent.append(clip)
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

BELABOX_WS_URL   = "wss://remote.belabox.net/ws/remote"
BELABOX_PIPELINE = "f1ade4e52502e56a5d94b4786360838c719dfd49"
BELABOX_CONFIG   = {
    "acodec":          "opus",
    "delay":           0,
    "max_br":          5000,
    "srt_latency":     3500,
    "bitrate_overlay": False,
    "relay_server":    "6",
    "relay_account":   "8130"
}
AUDIO_INPUTS = {
    "osmo":  "OsmoAction4",
    "usb":   "USB audio"
}


def belabox_switch_audio(asrc: str, log_fn=None, done_fn=None):
    """
    Stops encoder, switches audio input, restarts encoder.
    Runs in a background thread.
    """
    import websocket as ws_lib

    def _do():
        try:
            if log_fn: log_fn(f"BelaBox: Connecting...")
            ws = ws_lib.create_connection(
                BELABOX_WS_URL,
                header={"Origin": "https://remote.belabox.net",
                        "User-Agent": "Mozilla/5.0"},
                timeout=10)
            if log_fn: log_fn("BelaBox: Connected ✅")

            # Auth
            auth_msg = json.dumps({
                "remote": {"auth/key": {"key": BELABOX_KEY, "version": 6}}
            })
            ws.send(auth_msg)
            if log_fn: log_fn("BelaBox: Auth sent, waiting for response...")

            # Wait for auth confirmation
            for i in range(15):
                raw = ws.recv()
                msg = json.loads(raw)
                if log_fn: log_fn(f"BelaBox: Received: {raw[:80]}")
                if "remote" in msg:
                    if log_fn: log_fn("BelaBox: Auth confirmed ✅")
                    break

            # Stop encoder
            if log_fn: log_fn("BelaBox: Sending stop...")
            ws.send(json.dumps({"stop": 0}))
            time.sleep(1)

            # Start with new audio input
            start_cmd = {"start": {**{"pipeline": BELABOX_PIPELINE, "asrc": asrc}, **BELABOX_CONFIG}}
            if log_fn: log_fn(f"BelaBox: Sending start with asrc='{asrc}'...")
            ws.send(json.dumps(start_cmd))
            time.sleep(1)

            ws.close()
            if log_fn: log_fn(f"BelaBox: Done ✅ Audio = '{asrc}'")
            if done_fn: done_fn(True, asrc)

        except Exception as e:
            if log_fn: log_fn(f"BelaBox: ERROR – {type(e).__name__}: {e}")
            if done_fn: done_fn(False, str(e))

    threading.Thread(target=_do, daemon=True).start()


class AudioInputView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📷 DJI Cam", style=discord.ButtonStyle.primary, custom_id="bb_audio_osmo")
    async def audio_osmo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("⏳ Switching to **DJI Cam**...", ephemeral=True)
        belabox_switch_audio(AUDIO_INPUTS["osmo"], log_fn=lambda m: print(m))

    @discord.ui.button(label="🎙️ Microphone", style=discord.ButtonStyle.primary, custom_id="bb_audio_usb")
    async def audio_usb(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("⏳ Switching to **Microphone**...", ephemeral=True)
        belabox_switch_audio(AUDIO_INPUTS["usb"], log_fn=lambda m: print(m))


# ═══════════════════════════════════════════════════════════ Clip Embed ═══════

def make_clip_embed(clip):
    created = clip.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        unix_ts = int(dt.timestamp())
        ts = f"<t:{unix_ts}:f>"
    except:
        ts = created

    clip_url = clip.get("url", "")

    embed = discord.Embed(
        title       = clip.get("title", "New Clip"),
        url         = clip_url,
        description = f"**{clip.get('creator_name', '?')}** clipped",
        color       = 0x9146FF
    )
    embed.set_image(url=clip.get("thumbnail_url", ""))
    embed.set_footer(text=f"🕐 {created[:16].replace('T', ' ')} UTC")
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
        description = "Switch the BelaBox encoder audio input:",
        color       = discord.Color.orange()
    )
    embed.add_field(name="📷 DJI Cam",    value="Camera audio input", inline=True)
    embed.add_field(name="🎙️ Microphone", value="USB microphone",     inline=True)
    embed.set_footer(text="Encoder will stop → switch audio → restart automatically")
    await interaction.response.send_message(embed=embed, view=AudioInputView())


@tree.command(name="mic", description="Show the BelaBox audio input control panel")
async def slash_mic(interaction: discord.Interaction):
    embed = discord.Embed(
        title       = "🎙️ BelaBox Audio Control",
        description = "Switch the BelaBox encoder audio input:",
        color       = discord.Color.orange()
    )
    embed.add_field(name="📷 DJI Cam",    value="Camera audio input", inline=True)
    embed.add_field(name="🎙️ Microphone", value="USB microphone",     inline=True)
    embed.set_footer(text="Encoder will stop → switch audio → restart automatically")
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
        print(f"⚠️ Kick initial check failed (will retry): {e}")

    kick_fail_count = 0
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            clips = kick_api.get_recent_clips(KICK_CHANNEL)
            kick_fail_count = 0
            new_clips = [c for c in clips if c.get("id", c.get("clip_url", "")) not in seen_kick_clips]
            print(f"🔍 Kick: {len(clips)} clips, {len(new_clips)} new")

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
            kick_fail_count += 1
            if kick_fail_count <= 3:
                print(f"⚠️ Kick error ({kick_fail_count}/3): {e}")
            elif kick_fail_count == 4:
                print(f"⚠️ Kick API repeatedly failing – will keep trying silently")


# ═══════════════════════════════════════════════════════════════ Start ════════

if __name__ == "__main__":
    import time
    print("🤖 Starte BelaBox Discord Bot...")
    time.sleep(5)  # Kurze Pause beim Start um Rate Limits zu vermeiden
    bot.run(DISCORD_TOKEN)
