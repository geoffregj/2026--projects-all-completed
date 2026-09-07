#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          CORTANA v6.0-MINT — Personal AI for Linux        ║
║              Ported from the Termux build                 ║
╠══════════════════════════════════════════════════════════╣
║  Core AI    : Groq llama-3.3-70b-versatile                ║
║  Device     : battery · wifi · storage (via psutil/nmcli) ║
║  Music      : yt-dlp download · mpv playback · stop       ║
║  Movies     : yt-dlp to ~/Videos · browser search          ║
║  Finance    : PDF statement parser (pypdf, password)       ║
║               [live SMS ledger dropped — no SIM on a PC]  ║
║  Instagram  : Selenium-driven real Chrome session          ║
║               unfollow · seed-follow · DM/comment reply    ║
║               story post — see ig_selenium.py              ║
║  Memory     : brain.json · fuzzy match · save_memory       ║
╚══════════════════════════════════════════════════════════╝

CHANGED FROM THE TERMUX VERSION (read this before running):
  - termux-battery-status / termux-wifi-connectioninfo / termux-location
    don't exist on Linux Mint. Battery + WiFi are read via psutil / nmcli.
    GPS location is dropped (no GPS radio on a laptop) — the <<SYS: location>>
    tag has been removed from the toolkit and the prompt.
  - termux-tts-speak -> espeak-ng (sudo apt install espeak-ng)
  - termux-torch / camera -> dropped, no hardware equivalent on a desktop.
  - termux-sms-list (the live M-PESA SMS ledger) -> dropped. Your PC has no
    SIM radio to read SMS from. The PDF statement parser still works
    exactly as before — download your MySafaricom statement and run
    `mpesa pdf <password>`. If you want the live ledger back, the cleanest
    route is pulling SMS off your phone over `adb` (Termux:API isn't
    available on Mint) — say the word and I'll wire that up separately.
  - Instagram automation now drives a real Chrome browser via Selenium
    (ig_selenium.py) instead of hitting the private API with `requests`.
    Same command set (<<SYS: ig_unfollow_N>>, etc.) — different engine
    underneath. Needs: pip install selenium, and chromedriver on PATH.
  - SSL cert path fixed to use the system's default trust store instead
    of Termux's bundled cert.pem.
  - Paths (~/Music, ~/Videos, ~/Downloads) now point at normal Linux
    home-directory locations instead of /storage/emulated/0/...

pip install requests pypdf psutil selenium --break-system-packages
sudo apt install espeak-ng mpv yt-dlp chromium-chromedriver
"""

import json, os, sys, time, difflib, threading, ssl, re
import shutil, subprocess, getpass, random
import urllib.request, urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

os.system("clear")

# ══════════════════════════════════════════════════════════
# PATHS & COLOURS
# ══════════════════════════════════════════════════════════
HOME        = os.path.expanduser("~")
BRAIN_FILE  = os.path.join(HOME, "brain.json")
CONFIG_FILE = os.path.join(HOME, "botconfig.json")

DM_LOG_FILE    = "dm_log.json"
STORY_LOG_FILE = "story_log.json"
COMMENT_LOG    = "comment_log.json"
IG_RESULTS     = "instagram_results.json"
IG_UNFOLLOW    = "unfollow_log.json"
IG_FOLLOW_LOG  = "follow_log.json"

R="\033[0m";  B="\033[1m";   DIM="\033[2m"
CYN="\033[96m"; YLW="\033[93m"; GRN="\033[92m"
RED="\033[91m"; MAG="\033[95m"; WHT="\033[97m"
BLU="\033[94m"; C_GOLD="\033[33m"; C_BLUE="\033[34m"
C_GRAY="\033[90m"
BG_RED="\033[41;1;37m"; BG_GRN="\033[42;1;37m"
BG_BLU="\033[44;1;37m"; BG_YLW="\033[43;1;30m"
BG_MAG="\033[45;1;37m"; BG_CYN="\033[46;1;30m"

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import ig_selenium
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

_ig_driver = None  # cached Selenium session, one browser for the whole run

# ══════════════════════════════════════════════════════════
# STORAGE
# ══════════════════════════════════════════════════════════
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except Exception: pass
    return default

def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(data, f, indent=2)
    os.replace(tmp, path)

def load_config(): return load_json(CONFIG_FILE, {})
def save_config(c): save_json(CONFIG_FILE, c); os.chmod(CONFIG_FILE, 0o600)
def load_brain(): return load_json(BRAIN_FILE, dict(DEFAULT_BRAIN))
def save_brain(b): save_json(BRAIN_FILE, b)

def section(title):
    print(f"\n  {BLU}{'═'*50}{R}\n  {B}{WHT}  {title}{R}\n  {BLU}{'═'*50}{R}\n")

# ══════════════════════════════════════════════════════════
# DEFAULT BRAIN
# ══════════════════════════════════════════════════════════
DEFAULT_BRAIN = {
    "hello"            : "Hey Geoffrey! What do you need?",
    "hi"               : "Hi! What's on your mind?",
    "how are you"      : "Sharp and ready. What about you?",
    "what is your name": "I'm Cortana — Geoffrey's personal AI, now on Mint.",
    "what can you do"  : "Chat, run commands, download music/movies, "
                         "parse M-PESA statements, manage Instagram, and more.",
    "bye"              : "See you later! Stay sharp.",
    "goodbye"          : "Take care! Come back anytime.",
    "thank you"        : "Always happy to help.",
    "thanks"           : "No problem at all!",
    "tell me a joke"   : "Why do programmers prefer dark mode? Because light attracts bugs.",
    "motivate me"      : "Every expert was once a beginner. Keep going.",
    "who made you"     : "Geoffrey built me. I'm Cortana.",
}

# ══════════════════════════════════════════════════════════
# GROQ — DUAL PROMPT SYSTEM
# ══════════════════════════════════════════════════════════
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

def build_system_prompt(cfg, brain):
    name = cfg.get("user_name", "Geoffrey")
    brain_preview = list(brain.items())[-12:]
    memory_str = "\n".join(f"  - {k}: {v}" for k,v in brain_preview) if brain else "  No memories yet."
    return f"""You are Cortana, {name}'s sharp and friendly personal AI, running on his Linux Mint laptop.
You are NOT Microsoft's Cortana — you are Geoffrey's own creation.
Geoffrey's Instagram is @kuromirage. You know this — never say you don't.
Reply in plain text. Be concise and natural — never sound corporate or robotic.

[YOUR TOOLKIT]
Trigger ONE action tag anywhere in your reply. System runs it and feeds you back the result.

Device  (<<SYS: name>>):
  <<SYS: battery>>                      — Battery level.
  <<SYS: wifi>>                         — WiFi + IP.
  <<SYS: storage>>                      — Disk usage.

Music  (<<SYS: name>>):
  <<SYS: list_music>>                   — List songs in ~/Music.
  <<SYS: download_music_[SONG NAME]>>   — Download song. e.g. <<SYS: download_music_happy by pharrell>>
  <<SYS: play_music_[SONG NAME]>>       — Play song. e.g. <<SYS: play_music_blinding lights>>
  <<SYS: stop_music>>                   — Stop playback.

Movies  (<<SYS: name>>):
  <<SYS: download_movie_[TITLE]>>       — Download to ~/Videos. e.g. <<SYS: download_movie_bleach ep 1>>
  <<SYS: browse_movie_[TITLE]>>         — Open browser search. e.g. <<SYS: browse_movie_one piece>>

Finance:
  <<SYS: mpesa_pdf_[PASSWORD]>>         — Parse PDF statement. e.g. <<SYS: mpesa_pdf_438588>>

Instagram — management:
  <<SYS: ig_stats>>                     — Growth stats.
  <<SYS: ig_analyze>>                   — Analyse follower export HTML.
  <<SYS: ig_unfollow_[N]>>              — Unfollow N non-followers.
  <<SYS: ig_grow_[N]_from_[ACCOUNT]>>  — Seed-follow N from account.

Instagram — automation (background threads):
  <<SYS: ig_dm_once>>                   — Check inbox, reply to new DMs once.
  <<SYS: ig_dm_loop>>                   — Start continuous DM loop.
  <<SYS: ig_story_now>>                 — Post next queued story now.
  <<SYS: ig_comments_once>>             — Reply to comments once.
  <<SYS: ig_comments_loop>>             — Continuous comment loop.
  <<SYS: ig_manager_all>>               — Launch all 3 automation modules.
  <<SYS: ig_manager_stats>>             — DM/story/comment activity stats.

TTS  (<<SYS: tts_[MESSAGE]>>):
  Speak a message aloud. Only use when Geoffrey explicitly asks to speak/say/voice.
  e.g. <<SYS: tts_Hello Geoffrey, how are you?>>

Memory:
  <<SYS: save_memory_[KEY]|[VALUE]>>    — Save a fact permanently.

Bash  (<<CMD: command>>):
  Run any Linux command.
  e.g. <<CMD: df -h>>, <<CMD: ls ~/Downloads>>

[MEMORY — last {len(brain_preview)} entries]
{memory_str}

CRITICAL RULES:
  1. ONE tag per response only.
  2. General chat needs no tag — just reply naturally.
  3. NEVER output literal placeholder text like [SONG NAME], [N], [TITLE], [PASSWORD].
     ALWAYS substitute the actual value from the user's message.
  4. After a [SYSTEM OBSERVATION], give a short friendly summary.
  5. NEVER trigger a tool unless the user explicitly asked for that action.
     Do NOT proactively check battery, music, mpesa, IG or anything to fill silence.
  6. Geoffrey's Instagram is @kuromirage. You already know this.
"""

def groq_chat(api_key, messages):
    payload = json.dumps({
        "model": GROQ_MODEL, "messages": messages,
        "max_tokens": 400, "temperature": 0.65,
    }).encode("utf-8")
    req = urllib.request.Request(url=GROQ_URL, data=payload, method="POST")
    req.add_header("Content-Type",  "application/json")
    req.add_header("Authorization", f"Bearer {api_key.strip()}")
    req.add_header("User-Agent",    "Cortana/6.0-Mint")
    # system default trust store — no Termux cert.pem to point at on Linux Mint
    with urllib.request.urlopen(req, timeout=25, context=ssl.create_default_context()) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"].strip()

def groq_ig_reply(api_key, context, message, extra="", history=None):
    persona = (
        "You are Geoffrey (@kuromirage), a young tech content creator from Nairobi, Kenya. "
        "You are chatting casually with friends or followers in Instagram DMs or comments.\n\n"
        "STRICT RULES:\n"
        "1. LANGUAGE: Reply mostly in casual English or simple Swahili. "
        "You understand Sheng but do NOT force it back — sounds robotic. Be chill.\n"
        "2. BREVITY: 1 short sentence, 2 max. Do not yap.\n"
        "3. NO FILLER: Never say 'working on content' unless asked.\n"
        "4. VIBE: Match their energy.\n"
        "5. Never mention being an AI or LLM."
    )
    if extra: persona += f" {extra}"
    messages = [{"role":"system","content":persona}]
    if history: messages.extend(history)
    else: messages.append({"role":"user","content":f"Context: {context}\n\nMessage: {message}"})
    payload = json.dumps({
        "model": GROQ_MODEL, "messages": messages,
        "max_tokens": 120, "temperature": 0.6,
    }).encode("utf-8")
    req = urllib.request.Request(url=GROQ_URL, data=payload, method="POST")
    req.add_header("Content-Type",  "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("User-Agent",    "Cortana/6.0-Mint")
    with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as resp:
        reply = json.loads(resp.read().decode())["choices"][0]["message"]["content"].strip()
    if reply.startswith('"') and reply.endswith('"'): reply = reply[1:-1].strip()
    return reply

AVOID_TOPICS = [
    "my phone number","my address","my location",
    "personal information","private","money","send me",
]
def ig_contains_avoided(text):
    return any(t in text.lower() for t in AVOID_TOPICS)

# ══════════════════════════════════════════════════════════
# COMMAND EXECUTOR
# ══════════════════════════════════════════════════════════
def run_command(cmd):
    cmd = cmd.strip()
    is_bg = any(cmd.startswith(p) for p in ("mpv ","mpg123 ","play "))
    print(f"\n {YLW}⚡ Running:{R} {DIM}{cmd}{R}")
    try:
        if is_bg:
            subprocess.Popen(["bash","-c",cmd],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Started: {cmd}"
        result = subprocess.run(["bash","-c",cmd],
                                capture_output=True, text=True, timeout=120)
        out = (result.stdout + result.stderr).strip()
        return out[:600] if out else "(done)"
    except subprocess.TimeoutExpired: return "Timed out after 120s."
    except Exception as e:           return f"Error: {e}"

def confirm_and_run(cmd):
    print(f"\n {YLW}Cortana wants to run:{R}\n {DIM}{cmd}{R}\n")
    if input(f" {WHT}Allow? (y/n):{R} ").strip().lower() == "y":
        out = run_command(cmd)
        print(f"\n {GRN}✓ {out[:300]}{R}")
        return out
    print(f" {DIM}Cancelled.{R}")
    return "cancelled by user"

# ══════════════════════════════════════════════════════════
# DEVICE TOOLS — Linux Mint versions
# ══════════════════════════════════════════════════════════
def linux_battery():
    if PSUTIL_AVAILABLE:
        b = psutil.sensors_battery()
        if b is None:
            return "No battery detected (desktop PC, or sensor unsupported)."
        state = "Charging" if b.power_plugged else "Discharging"
        return f"Battery: {b.percent}% — {state}"
    # fallback: read /sys directly, works on virtually every laptop
    try:
        base = "/sys/class/power_supply/BAT0"
        if not os.path.exists(base): base = "/sys/class/power_supply/BAT1"
        cap = open(f"{base}/capacity").read().strip()
        status = open(f"{base}/status").read().strip()
        return f"Battery: {cap}% — {status}"
    except Exception:
        return "Battery unavailable (install psutil: pip install psutil)"

def linux_wifi():
    try:
        r = subprocess.run(["nmcli","-t","-f","active,ssid","dev","wifi"],
                           capture_output=True, text=True, timeout=5)
        ssid = "?"
        for line in r.stdout.splitlines():
            if line.startswith("yes:"):
                ssid = line.split(":",1)[1]; break
        ip_r = subprocess.run(["hostname","-I"], capture_output=True, text=True, timeout=5)
        ip = ip_r.stdout.strip().split()[0] if ip_r.stdout.strip() else "?"
        return f"WiFi: {ssid} | IP: {ip}"
    except Exception:
        return "WiFi unavailable (needs NetworkManager / nmcli)"

def disk_usage_summary():
    try:
        st = shutil.disk_usage(HOME)
        return (f"Storage: {st.used/1e9:.1f}GB used / "
                f"{st.total/1e9:.1f}GB total ({st.free/1e9:.1f}GB free)")
    except Exception as e: return f"Storage error: {e}"

def list_music():
    d = os.path.join(HOME,"Music")
    if not os.path.exists(d): return "No ~/Music folder."
    files = [f for f in os.listdir(d)
             if f.endswith((".mp3",".ogg",".wav",".m4a",".webm"))]
    return ("Music:\n" + "\n".join(f" {i+1}. {f}" for i,f in enumerate(files))
            if files else "No music files yet.")

def fetch_webpage(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Cortana/6.0-Mint"})
        with urllib.request.urlopen(req,timeout=10,context=ssl.create_default_context()) as r:
            html = r.read().decode("utf-8",errors="replace")
            text = re.sub(r"<[^>]+"," ",html)
            return re.sub(r"\s+"," ",text).strip()[:1500]
    except Exception as e: return f"Could not fetch: {e}"

# ══════════════════════════════════════════════════════════
# M-PESA PDF STATEMENT PARSER (unchanged logic, Linux paths)
# ══════════════════════════════════════════════════════════
_PDF_RECEIPT_RE = re.compile(
    r'^([A-Z0-9]{8,14})\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.*)')
_PDF_COMPLETE_RE = re.compile(
    r'^(.*?)\s+Completed\s+([-\d,]+\.\d{2})\s+([-\d,]+\.\d{2})\s*$')
_PDF_SKIP = {"receipt no.","disclaimer:","statement verification",
             "for self-help","page ","conditions apply","to verify","prompts to enter"}

_PDF_SAV_VAULTS_KW = [
    "unit trust invest to 4145555","unit trust invest to 4144555",
    "lock savings","goal savings","m-shwari","mshwari","sacco",
]
_PDF_SAV_OUT_KW = [
    "unit trust withdraw from 4145555","unit trust withdraw from 4144555",
    "lock savings unlock","m-shwari withdrawal",
]
_PDF_FULIZA_KW = [
    "overdraft of credit party","od loan repayment",
    "airtime purchase with fuliza","pay bill online fuliza",
    "merchant payment fuliza","customer transfer fuliza",
    "customer withdrawal at agent till with fuliza",
]
_PDF_INCOME_KW = [
    "funds received from","business payment from",
    "deposit of funds at agent till","cash deposit","salary","reversal",
]
_PDF_TRANSFER_KW = [
    "pay bill online to 516600","pay bill online to 247247",
    "pay bill online to 300600","pay bill charge",
    "customer transfer of funds charge","withdrawal charge",
]

def _pdf_classify(details, paid_in, withdrawn):
    d = details.lower()
    if any(k in d for k in _PDF_SAV_OUT_KW):       return "SAVINGS_OUT"
    if d == "overdraft of credit party":            return "FULIZA"
    if "od loan repayment" in d:                   return "FULIZA_REPAY"
    if any(k in d for k in _PDF_FULIZA_KW):
        return "FULIZA" if paid_in > 0 else "EXPENSE"
    if paid_in > 0 and any(k in d for k in _PDF_INCOME_KW): return "INCOME"
    if withdrawn > 0 and any(k in d for k in _PDF_SAV_VAULTS_KW): return "SAVINGS_IN"
    if any(k in d for k in _PDF_TRANSFER_KW):      return "TRANSFER"
    if paid_in > 0:                                 return "INCOME"
    if withdrawn > 0:                               return "EXPENSE"
    return "IGNORE"

def _parse_pdf_amount(s):
    try: return float(s.replace(",",""))
    except: return 0.0

def _read_pdf_text(pdf_path, password):
    if not PDF_AVAILABLE:
        return None, "pypdf not installed. Run: pip install pypdf"
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        if reader.decrypt(str(password)) == 0:
            return None, "Wrong password."
    text = ""
    total = len(reader.pages)
    for i, page in enumerate(reader.pages):
        print(f"\r {DIM}Reading page {i+1}/{total}...{R}", end="", flush=True)
        t = page.extract_text()
        if t: text += t + "\n"
    print(f"\r {GRN}✓ Read {total} pages.{R}          ")
    return text, None

def _extract_pdf_transactions(text):
    rows = []
    cur_receipt = cur_ts = None
    cur_lines   = []
    for raw in text.split('\n'):
        line = raw.strip()
        if not line: continue
        ll = line.lower()
        if any(ll.startswith(s) for s in _PDF_SKIP): continue
        m = _PDF_RECEIPT_RE.match(line)
        if m:
            if cur_receipt: rows.append((cur_receipt, cur_ts, '\n'.join(cur_lines)))
            cur_receipt, cur_ts, cur_lines = m.group(1), m.group(2), [m.group(3)]
        elif cur_receipt:
            cur_lines.append(line)
    if cur_receipt: rows.append((cur_receipt, cur_ts, '\n'.join(cur_lines)))

    transactions = []
    for receipt, ts, body in rows:
        body = re.sub(r'\s+',' ', body).strip()
        m = _PDF_COMPLETE_RE.match(body)
        if not m: continue
        details = re.sub(r'\s*Completed\s*$','', m.group(1)).strip()
        val1      = _parse_pdf_amount(m.group(2))
        balance   = _parse_pdf_amount(m.group(3))
        paid_in   = val1   if val1 > 0 else 0.0
        withdrawn = abs(val1) if val1 < 0 else 0.0
        transactions.append({"receipt":receipt,"ts":ts,"details":details,
                              "paid_in":paid_in,"withdrawn":withdrawn,"balance":balance})
    return transactions

def _dedup_pdf(transactions):
    seen = set()
    result = []
    for tx in transactions:
        key = (tx["receipt"], tx["details"][:40])
        if key not in seen:
            seen.add(key)
            result.append(tx)
    return result

def _print_finance_dashboard(buckets, label):
    CAT_STYLE = {
        "INCOME"      : (GRN, "INCOME  "),
        "EXPENSE"     : (RED, "EXPENSE "),
        "SAVINGS_IN"  : (BLU, "SAVE IN "),
        "SAVINGS_OUT" : (YLW, "SAVE OUT"),
        "TRANSFER"    : (MAG, "TRANSFER"),
        "FULIZA"      : (CYN, "FULIZA  "),
        "FULIZA_REPAY": (RED, "FUL PAY "),
    }
    combined = []
    for cat, rows in buckets.items():
        for row in rows: combined.append((cat, row))
    combined.sort(key=lambda x: x[1]["ts"], reverse=True)
    if not combined:
        print(f" {YLW}No financial transactions found.{R}"); return

    print(f"\n{C_BLUE}┌───────────────────┬──────────┬──────────────────────────────────────────────────┬──────────────┐{R}")
    print(f"{C_BLUE}│{B}{WHT} TIMESTAMP         {C_BLUE}│{B}{WHT} TYPE     {C_BLUE}│{B}{WHT} DETAILS                                          {C_BLUE}│{B}{WHT} AMOUNT       {C_BLUE}│{R}")
    print(f"{C_BLUE}├───────────────────┼──────────┼──────────────────────────────────────────────────┼──────────────┤{R}")
    for cat, row in combined:
        colour, lbl = CAT_STYLE.get(cat, (WHT, cat[:8].ljust(8)))
        print(f"{C_BLUE}│{C_GRAY} {row['ts']:<17} {C_BLUE}│{colour} {lbl} {C_BLUE}│{WHT} {row['detail']:<48} {C_BLUE}│{colour} Ksh {row['amount']:<8,.2f} {C_BLUE}│{R}")
    print(f"{C_BLUE}└───────────────────┴──────────┴──────────────────────────────────────────────────┴──────────────┘{R}")

    def tot(cat): return sum(r["amount"] for r in buckets[cat])
    def cnt(cat): return len(buckets[cat])
    income=tot("INCOME"); expense=tot("EXPENSE")
    sav_in=tot("SAVINGS_IN"); sav_out=tot("SAVINGS_OUT")
    transfer=tot("TRANSFER"); fuliza=tot("FULIZA"); ful_repay=tot("FULIZA_REPAY")
    net_savings=sav_in-sav_out; net_pos=income-expense
    sav_col=GRN if net_savings>=0 else RED
    pos_col=GRN if net_pos>=0 else RED
    pos_lbl="SURPLUS" if net_pos>=0 else "DEFICIT"

    print(f"\n{C_GOLD}┌──────────────────────────────────────────────────────────────────────┐{R}")
    print(f"{C_GOLD}│ {DIM}{label[:68]:<68}{R}{C_GOLD}│{R}")
    print(f"{C_GOLD}│                    {B}{WHT}FINANCIAL OVERVIEW DASHBOARD{R}{C_GOLD}                     │{R}")
    print(f"{C_GOLD}├──────────────────────────────────────────────────────────────────────┤{R}")
    print(f"{C_GOLD}│ {BG_GRN}  INCOME     {R}  Count:{cnt('INCOME'):<4}  Total : {B}{GRN}Ksh {income:>10,.2f}{R}{C_GOLD}             │{R}")
    print(f"{C_GOLD}│ {BG_RED}  EXPENSES   {R}  Count:{cnt('EXPENSE'):<4}  Total : {B}{RED}Ksh {expense:>10,.2f}{R}{C_GOLD}             │{R}")
    print(f"{C_GOLD}│                                                                      │{R}")
    print(f"{C_GOLD}│ {BG_BLU}  SAVINGS    {R}  Deposited  : {B}{GRN}Ksh {sav_in:>9,.2f}{R}{C_GOLD}                        │{R}")
    print(f"{C_GOLD}│              Withdrawn  : {B}{YLW}Ksh {sav_out:>9,.2f}{R}{C_GOLD}                        │{R}")
    print(f"{C_GOLD}│              Net Vault  : {B}{sav_col}Ksh {net_savings:>9,.2f}{R}{C_GOLD}                        │{R}")
    if transfer > 0:
        print(f"{C_GOLD}│                                                                      │{R}")
        print(f"{C_GOLD}│ {BG_MAG}  TRANSFERS  {R}  Count:{cnt('TRANSFER'):<4}  Total : {B}{MAG}Ksh {transfer:>10,.2f}{R}{C_GOLD}  (neutral) │{R}")
    if fuliza > 0 or ful_repay > 0:
        net_ful=fuliza-ful_repay; nf_col=GRN if net_ful<=0 else RED
        print(f"{C_GOLD}│                                                                      │{R}")
        print(f"{C_GOLD}│ {BG_CYN}  FULIZA     {R}  Borrowed   : {B}{CYN}Ksh {fuliza:>9,.2f}{R}{C_GOLD}                        │{R}")
        print(f"{C_GOLD}│              Repaid    : {B}{RED}Ksh {ful_repay:>9,.2f}{R}{C_GOLD}                        │{R}")
        print(f"{C_GOLD}│              Net Debt  : {B}{nf_col}Ksh {net_ful:>9,.2f}{R}{C_GOLD}                        │{R}")
    print(f"{C_GOLD}│                                                                      │{R}")
    print(f"{C_GOLD}│  NET POSITION ({pos_lbl})  : {B}{pos_col}Ksh {net_pos:>10,.2f}{R}{C_GOLD}                     │{R}")
    print(f"{C_GOLD}└──────────────────────────────────────────────────────────────────────┘\n{R}")

def run_pdf_finance_engine(password):
    """Parse the most recent MPESA PDF statement found in ~/Downloads."""
    search_dirs = [Path(HOME) / "Downloads"]
    pdfs = []
    for d in search_dirs:
        if d.exists():
            for pat in ("MPESA_Statement*.pdf","mpesa*.pdf","M-PESA*.pdf"):
                pdfs.extend(d.glob(pat))

    if not pdfs:
        print(f" {YLW}No M-PESA PDFs found in ~/Downloads.{R}")
        return "No PDF found. Download your statement from MySafaricom first."

    pdf_path = max(set(pdfs), key=lambda p: p.stat().st_mtime)
    print(f"\n {CYN}Processing:{R} {B}{pdf_path.name}{R}")

    text, err = _read_pdf_text(pdf_path, password)
    if err: return f"PDF error: {err}"

    transactions = _extract_pdf_transactions(text)
    if not transactions:
        return "Could not parse PDF rows."

    before = len(transactions)
    transactions = _dedup_pdf(transactions)
    removed = before - len(transactions)
    if removed: print(f" {GRN}✓ Removed {removed} duplicate rows{R}")

    for tx in transactions:
        tx["category"] = _pdf_classify(tx["details"], tx["paid_in"], tx["withdrawn"])

    buckets = defaultdict(list)
    for tx in transactions:
        if tx["category"] == "IGNORE": continue
        amount = tx["withdrawn"] if tx["withdrawn"] > 0 else tx["paid_in"]
        buckets[tx["category"]].append({
            "ts": tx["ts"][:16],
            "amount": amount,
            "detail": (tx["details"][:48] if len(tx["details"])<=48
                       else tx["details"][:45]+"..."),
        })

    _print_finance_dashboard(buckets, pdf_path.name)
    return f"PDF parsed: {len(transactions)} transactions from {pdf_path.name}."

# ══════════════════════════════════════════════════════════
# INSTAGRAM — HTML PARSER (export analysis, unchanged)
# ══════════════════════════════════════════════════════════
from html.parser import HTMLParser
import glob

class _IGParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.usernames=set(); self._in_link=False
    def handle_starttag(self,tag,attrs):
        if tag!="a": return
        href=dict(attrs).get("href","")
        if "instagram.com/" in href and not any(s in href for s in
                ("/explore/","/reels/","/p/","/stories/","/tv/")):
            self._in_link=True
    def handle_data(self,data):
        if not self._in_link: return
        u=data.strip()
        if "instagram.com" in u: u=u.rstrip("/").split("/")[-1]
        if u and 1<=len(u)<=30: self.usernames.add(u.lower())
    def handle_endtag(self,tag):
        if tag=="a": self._in_link=False

def _parse_html(path):
    if not os.path.exists(path): return set()
    p=_IGParser()
    with open(path,"r",encoding="utf-8") as f: p.feed(f.read())
    return p.usernames

def ig_parse_export():
    following = _parse_html("following.html")
    if not following: return None,"following.html not found."
    files=sorted(glob.glob("followers_*.html"))
    followers=set()
    for f in files: followers.update(_parse_html(f))
    if not followers: return None,"No followers_*.html found."
    res = {
        "not_following_back": sorted(following-followers),
        "you_dont_follow":    sorted(followers-following),
        "mutual":             sorted(following&followers),
        "following_count":    len(following),
        "followers_count":    len(followers),
    }
    save_json(IG_RESULTS, {**res,"generated_at":datetime.now().isoformat()})
    return res,None

def ig_show_stats():
    results=load_json(IG_RESULTS,{}); follow_log=load_json(IG_FOLLOW_LOG,{})
    unfollow=load_json(IG_UNFOLLOW,[])
    out=[f"\n {BLU}{'═'*48}{R}",f" {B}{WHT} INSTAGRAM STATS — @kuromirage{R}",f" {BLU}{'═'*48}{R}"]
    if results:
        nfb=len(results.get("not_following_back",[])); ydf=len(results.get("you_dont_follow",[]))
        mu=len(results.get("mutual",[])); gen=results.get("generated_at","?")[:10]
        out+=[f" {DIM}Export: {gen}{R}",
              f" You follow         : {results.get('following_count',0)}",
              f" Follow you         : {results.get('followers_count',0)}",
              f" Mutual             : {mu}",
              f" Not following back : {nfb}",
              f" You don't follow   : {ydf}"]
    else: out.append(f" {YLW}No analysis yet.{R}")
    if follow_log:
        fb=sum(1 for v in follow_log.values() if v.get("followed_back") is True)
        no=sum(1 for v in follow_log.values() if v.get("followed_back") is False)
        pen=sum(1 for v in follow_log.values() if v.get("followed_back") is None)
        rate=f"{fb/max(fb+no,1)*100:.0f}%" if (fb+no)>0 else "N/A"
        today=datetime.now().strftime("%Y-%m-%d")
        td=sum(1 for v in follow_log.values() if v.get("followed_at","").startswith(today))
        out+=[f" {BLU}{'─'*48}{R}",
              f" Followed via script : {len(follow_log)}",
              f" Follow-back rate    : {rate}",
              f" Followed today      : {td}/25",
              f" Pending             : {pen}"]
    if unfollow:
        today_uf=sum(1 for e in unfollow
                     if e.get("timestamp","").startswith(datetime.now().strftime("%Y-%m-%d"))
                     and e.get("status")=="unfollowed")
        out.append(f" Unfollowed today    : {today_uf}")
    out.append(f" {BLU}{'═'*48}{R}")
    return "\n".join(out)

def ig_manager_stats():
    section("INSTAGRAM MANAGER STATS")
    dm_log=load_json(DM_LOG_FILE,{}); comment_log=load_json(COMMENT_LOG,{})
    today=datetime.now().strftime("%Y-%m-%d")
    dm_sent=sum(1 for v in dm_log.values() if v.get("status")=="sent")
    dm_today=sum(1 for v in dm_log.values() if v.get("sent_at","").startswith(today) and v.get("status")=="sent")
    c_sent=sum(1 for v in comment_log.values() if v.get("status")=="sent")
    c_today=sum(1 for v in comment_log.values() if v.get("sent_at","").startswith(today) and v.get("status")=="sent")
    print(f"  {WHT}DMs:{R}       Total {dm_sent}  Today {dm_today}")
    print(f"  {WHT}Comments:{R}  Total {c_sent}  Today {c_today}")
    return f"DM:{dm_sent} Comments:{c_sent}"

# ══════════════════════════════════════════════════════════
# INSTAGRAM — SELENIUM SESSION HELPERS
# ══════════════════════════════════════════════════════════
def _get_ig_driver():
    """One shared browser for the whole Cortana session — logging in twice
    per run is annoying and slower than just keeping the tab open."""
    global _ig_driver
    if not SELENIUM_AVAILABLE:
        return None
    if _ig_driver is not None:
        try:
            _ = _ig_driver.title  # still alive?
            return _ig_driver
        except Exception:
            _ig_driver = None
    _ig_driver = ig_selenium.login()
    return _ig_driver

# ══════════════════════════════════════════════════════════
# INTERNAL MODULE RUNNER — <<SYS: ...>> dispatcher
# ══════════════════════════════════════════════════════════
def run_internal_module(cmd, cfg):
    cmd = cmd.strip()

    # Device
    if cmd=="battery":  return linux_battery()
    if cmd=="wifi":     return linux_wifi()
    if cmd=="storage":  return disk_usage_summary()

    # Music
    if cmd=="list_music": return list_music()
    if cmd=="stop_music":
        subprocess.Popen(["pkill","-f","mpv"],
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return "Music stopped."
    if cmd.startswith("download_music_"):
        query=cmd[15:].replace("_"," ").strip()
        if not query: return "No song name."
        os.makedirs(os.path.join(HOME,"Music"), exist_ok=True)
        subprocess.Popen(["bash","-c",
            f"yt-dlp -x --audio-format mp3 'ytsearch1:{query}'"
            f" -o '{HOME}/Music/%(title)s.%(ext)s' --restrict-filenames --no-playlist"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return f"Downloading '{query}' to ~/Music."
    if cmd.startswith("play_music_"):
        query=cmd[11:].strip()
        music_dir=os.path.join(HOME,"Music")
        if not os.path.exists(music_dir): return "No ~/Music folder."
        all_files=[f for f in os.listdir(music_dir)
                   if f.endswith((".mp3",".ogg",".wav",".m4a",".webm"))]
        qspace=query.replace("_"," ").lower()
        qunder=query.replace(" ","_").lower()
        matches=(
            [f for f in all_files if f==query] or
            [f for f in all_files if f.lower()==query.lower()] or
            [f for f in all_files if qspace in f.lower()] or
            [f for f in all_files if qunder in f.lower()]
        )
        if matches:
            subprocess.Popen(["mpv",os.path.join(music_dir,matches[0])],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return f"Now playing: {matches[0]}"
        return f"No match for '{query}'. Available: {', '.join(all_files[:4])}"

    # Movies
    if cmd.startswith("download_movie_"):
        query=cmd[15:].replace("_"," ").strip()
        if not query: return "No title."
        videos_dir=os.path.join(HOME,"Videos"); os.makedirs(videos_dir,exist_ok=True)
        subprocess.Popen(["bash","-c",
            f"yt-dlp 'ytsearch1:{query}' -o '{videos_dir}/%(title)s.%(ext)s'"
            f" --restrict-filenames --no-playlist"
            f" -f 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return f"Downloading '{query}' to ~/Videos."
    if cmd.startswith("browse_movie_"):
        query=cmd[13:].replace("_","+").strip()
        url=f"https://www.google.com/search?q={query}+watch+online"
        subprocess.Popen(["xdg-open",url],
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return f"Opened browser search for '{query.replace('+', ' ')}'."

    # Finance — PDF only (see header notes re: dropped live SMS ledger)
    if cmd.startswith("mpesa_pdf_"):
        password=cmd[10:].strip()
        if not password:
            password=getpass.getpass(" PDF password: ")
        return run_pdf_finance_engine(password)
    if cmd=="mpesa":
        return ("Live SMS ledger isn't available on a desktop — no SIM radio. "
                "Use 'mpesa pdf <password>' with your MySafaricom statement instead.")

    # Instagram — follower management
    if not SELENIUM_AVAILABLE and cmd.startswith("ig_"):
        return "Selenium not installed. Run: pip install selenium --break-system-packages"

    if cmd=="ig_stats":   return ig_show_stats()
    if cmd=="ig_analyze":
        res,err=ig_parse_export()
        if err: return err
        return (f"Analysis done. Following:{res['following_count']} "
                f"Followers:{res['followers_count']} "
                f"Not following back:{len(res['not_following_back'])}")
    if cmd.startswith("ig_unfollow_"):
        parts=cmd.split("_"); batch=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 20
        targets=load_json(IG_RESULTS,{}).get("not_following_back",[])
        if not targets: return "No targets — run ig_analyze first."
        driver=_get_ig_driver()
        if not driver: return "IG login failed."
        my_username=cfg.get("ig_username","")
        if not my_username:
            my_username=ig_selenium.clean_username(input(" Your IG username (for the following-list page): "))
            cfg["ig_username"]=my_username; save_config(cfg)
        done,skipped,errors=ig_selenium.unfollow_batch(driver,my_username,targets,batch,IG_UNFOLLOW)
        return f"Done. Unfollowed:{done} Skipped:{skipped} Errors:{errors}"
    if cmd.startswith("ig_grow_"):
        m=re.match(r"ig_grow_(\d+)_from_(.+)",cmd)
        count=int(m.group(1)) if m else 20
        seed=m.group(2).replace("_"," ").strip() if m else cfg.get("ig_seed","kuromirage")
        driver=_get_ig_driver()
        if not driver: return "IG login failed."
        return f"Followed {ig_selenium.seed_follow(driver,seed,count,IG_FOLLOW_LOG)} accounts from @{seed}."

    api_key=cfg.get("groq_api_key","")
    def _reply_fn(context, message, history):
        return groq_ig_reply(api_key, context, message, history=history)

    if cmd=="ig_dm_once" or cmd=="ig_dm_loop":
        driver=_get_ig_driver()
        if not driver: return "IG login failed."
        once = (cmd=="ig_dm_once")
        def _loop():
            while True:
                ig_selenium.dm_check_and_reply(driver, _reply_fn, ig_contains_avoided, DM_LOG_FILE)
                if once: break
                time.sleep(60)
        threading.Thread(target=_loop, daemon=True).start()
        return "Checking DMs once — background." if once else "DM loop started in background."

    if cmd=="ig_comments_once" or cmd=="ig_comments_loop":
        driver=_get_ig_driver()
        if not driver: return "IG login failed."
        once = (cmd=="ig_comments_once")
        my_username=cfg.get("ig_username","kuromirage")
        def _loop():
            while True:
                ig_selenium.reply_to_comments(driver, my_username, _reply_fn, ig_contains_avoided, COMMENT_LOG)
                if once: break
                time.sleep(300)
        threading.Thread(target=_loop, daemon=True).start()
        return "Checking comments once — background." if once else "Comment loop started in background."

    if cmd=="ig_manager_all":
        driver=_get_ig_driver()
        if not driver: return "IG login failed."
        my_username=cfg.get("ig_username","kuromirage")
        threading.Thread(target=lambda: ig_selenium.dm_check_and_reply(
            driver,_reply_fn,ig_contains_avoided,DM_LOG_FILE), daemon=True).start()
        threading.Thread(target=lambda: ig_selenium.reply_to_comments(
            driver,my_username,_reply_fn,ig_contains_avoided,COMMENT_LOG), daemon=True).start()
        return "DM + comment automation launched. (Story posting: use 'ig story <path> <caption>' directly.)"
    if cmd=="ig_manager_stats": return ig_manager_stats()

    if cmd.startswith("ig_story_"):
        rest = cmd[len("ig_story_"):]
        parts = rest.split("|", 1)
        path = parts[0].strip()
        caption = parts[1].strip() if len(parts) > 1 else ""
        driver=_get_ig_driver()
        if not driver: return "IG login failed."
        ok,msg = ig_selenium.post_story(driver, path, caption)
        return msg

    # TTS — espeak-ng instead of termux-tts-speak
    if cmd.startswith("tts_"):
        message=cmd[4:].strip()
        if not message: return "Nothing to say."
        safe=message.replace("'","\\'")
        subprocess.Popen(["bash","-c",f"espeak-ng '{safe}'"],
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return f"Speaking: {message[:80]}"

    # Memory
    if cmd.startswith("save_memory_"):
        try:
            payload=cmd[12:]; k,v=payload.split("|",1)
            brain=load_brain(); brain[k.strip().lower()]=v.strip(); save_brain(brain)
            return f"Saved: {k.strip()} = {v.strip()}"
        except Exception: return "Format: save_memory_key|value"

    return f"Unknown module: '{cmd}'"

# ══════════════════════════════════════════════════════════
# SMART RULES — instant, always local
# ══════════════════════════════════════════════════════════
_BLOCKED_NAMES = {
    "Ok","Fine","Good","Bad","Here","Back","Ready","Done","Sure",
    "Tired","Bored","Happy","Sad","Free","Busy","Lost","Lazy","Sick",
    "Well","Hungry","Thirsty","Angry","Scared","Excited",
    "Nervous","Anxious","Stressed","Lonely","Confused",
    "Serious","Joking","Playing","Working","Sleeping","Awake","Home",
    "Outside","Late","Early","Cold","Hot","Sober",
    "Sorry","Wrong","Right","Correct","Real","Fake","New","Old",
}

def apply_smart_rules(text, cfg):
    t,lower=text.strip(),text.strip().lower()
    for prefix in ("my name is ","call me ","i'm called ","people call me "):
        if lower.startswith(prefix):
            name=t[len(prefix):].strip().split()[0].title()
            cfg["user_name"]=name; save_config(cfg)
            return f"Got it! I'll call you {name}."
    m=re.match(r"^(?:i am|i'm|am)\s+([A-Za-z][a-z]{1,20})$",t.strip())
    if m:
        candidate=m.group(1).title()
        if candidate not in _BLOCKED_NAMES:
            cfg["user_name"]=candidate; save_config(cfg)
            return f"Nice to meet you, {candidate}!"
    if any(p in lower for p in ("forget my name","clear my name","remove my name")):
        cfg.pop("user_name",None); save_config(cfg); return "Done — forgotten."
    if any(p in lower for p in ("what time","current time","the time")):
        return f"It's {datetime.now().strftime('%H:%M:%S')} on {datetime.now().strftime('%A, %B %d %Y')}."
    if any(p in lower for p in ("what day","today's date","what date")):
        return f"Today is {datetime.now().strftime('%A, %B %d %Y')}."
    if lower in ("show brain","what do you know","list memory"):
        brain=load_brain()
        return f"I know {len(brain)} things: {', '.join(list(brain.keys())[:15])}..."
    return None

# ══════════════════════════════════════════════════════════
# HARD-ROUTE DETECTOR — deterministic / heavy ops, length-guarded
# ══════════════════════════════════════════════════════════
def detect_hard_intent(lower, cfg):
    is_cmd = len(lower) < 120

    if is_cmd and any(p in lower for p in
            ("instagram stats","ig stats","my instagram","follower stats","show stats","growth stats")):
        return ig_show_stats(),None

    if is_cmd and any(p in lower for p in
            ("analyse instagram","analyze instagram","parse instagram",
             "check followers","who doesn't follow","who doesnt follow")):
        print(f" {DIM}Parsing export files...{R}")
        res,err=ig_parse_export()
        if err: return err,None
        return (f"Done! Following:{res['following_count']} Followers:{res['followers_count']}\n"
                f" Not following back:{len(res['not_following_back'])}"),None

    if is_cmd and lower in ("ls music","list music","show music","my music","music files"):
        return list_music(),None

    m=re.search(r"(?:fetch|browse|read)\s+(https?://\S+)",lower)
    if m: return f"From {m.group(1)}:\n{fetch_webpage(m.group(1))[:600]}",None

    m=re.search(r"(?:read|show|open|cat)\s+(?:file\s+)?['\"]?([~/\w.\-]+)['\"]?",lower)
    if m:
        path=os.path.expanduser(m.group(1).strip())
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path,"r",errors="replace") as f:
                    return f"Contents of {path}:\n{f.read(1000)}",None
            except Exception as e: return f"Could not read: {e}",None

    return None,None

# ══════════════════════════════════════════════════════════
# ACTION GATE — blocks uninstructed tool calls at Python level
# ══════════════════════════════════════════════════════════
_ACTION_KW = {
    "battery"       : ["battery","charge","power","percent"],
    "wifi"          : ["wifi","wi-fi","network","ip","internet","connection"],
    "storage"       : ["storage","disk","space","free","memory","how much"],
    "list_music"    : ["list","show","music","songs","tracks","what songs"],
    "download_music": ["download","get me","grab","fetch","save music","get song","get track"],
    "play_music"    : ["play","listen","hear","put on","start","music","song","track","audio"],
    "stop_music"    : ["stop","pause","quiet","silence","mute","kill"],
    "download_movie": ["download","get me","grab","fetch","save","get movie","get film","get anime","get episode"],
    "browse_movie"  : ["browse","search","find","open","movie","film","anime","watch"],
    "mpesa"         : ["mpesa","m-pesa","ledger","finance","expense","saving","spending","money","transaction"],
    "ig_stats"      : ["stats","instagram","ig","follower","growth","account"],
    "ig_analyze"    : ["analys","instagram","follower","who","check","export"],
    "ig_unfollow"   : ["unfollow","remove","clean"],
    "ig_grow"       : ["grow","follow","seed","gain"],
    "ig_dm"         : ["dm","message","inbox","reply","direct"],
    "ig_story"      : ["story","stories","post","upload","queue"],
    "ig_comments"   : ["comment","reply","post"],
    "ig_manager"    : ["manager","all","module","automation"],
    "tts"           : ["speak","say","voice","talk","read","tts","out loud","aloud"],
}

def action_requested(user_lower, sys_cmd):
    if sys_cmd.startswith("save_memory"): return True
    for family, keywords in _ACTION_KW.items():
        if sys_cmd.startswith(family):
            return any(kw in user_lower for kw in keywords)
    return True

# ══════════════════════════════════════════════════════════
# OFFLINE FALLBACK ENGINE
# ══════════════════════════════════════════════════════════
_OFFLINE_PATTERNS = [
    (r"\b(hi|hey|hello|habari|sup|hii)\b",
     ["Hey! I'm in offline mode — Groq is cooling down.",
      "Hi! Running locally for a moment. Back online soon."]),
    (r"\b(how are you|how r u|u good)\b",
     ["Sharp and running locally. Groq back shortly.",
      "Good — just offline for a breather."]),
    (r"\b(joke|funny|laugh|lol)\b",
     ["Why do Java devs wear glasses? Because they don't C#.",
      "A SQL query walks into a bar and asks two tables: 'Can I join you?'",
      "Why did the programmer quit? Because he didn't get arrays."]),
    (r"\b(time|clock|what time)\b",
     [lambda: f"It's {datetime.now().strftime('%H:%M')} — offline mode active."]),
    (r"\b(music|song|play|listen)\b",
     ["Music still works offline! Say 'play [song name]'."]),
    (r"\b(bored|blank|nothing|idk)\b",
     ["Tell me something while we wait.",
      "Say 'show brain' to see what I remember."]),
]
_OFFLINE_DEFAULTS = [
    "Offline mode — Groq cooling down. Back in under a minute.",
    "Still here, running locally. Groq resumes soon.",
    "Offline mode active. Device commands and music still work.",
    "Rate limit cooldown. Ask me something simple.",
]
_offline_turn = 0

def fuzzy_find(text, brain, threshold=0.75):
    best_key,best_score=None,0.0; inp=text.lower().strip()
    for key in brain:
        score=difflib.SequenceMatcher(None,inp,key).ratio()
        if score>best_score: best_score,best_key=score,key
    return best_key if best_score>=threshold else None

def offline_reply(user_input, brain):
    global _offline_turn
    lower = user_input.lower().strip()
    if lower in brain: return brain[lower]
    fkey = fuzzy_find(lower, brain)
    if fkey: return brain[fkey]
    for pattern, responses in _OFFLINE_PATTERNS:
        if re.search(pattern, lower):
            r = random.choice(responses)
            return r() if callable(r) else r
    msg = _OFFLINE_DEFAULTS[_offline_turn % len(_OFFLINE_DEFAULTS)]
    _offline_turn += 1
    return msg

def spinner_while(fn, *args, **kwargs):
    result,error,done=[None],[None],threading.Event()
    frames="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    def _run():
        try:    result[0]=fn(*args,**kwargs)
        except Exception as e: error[0]=e
        finally: done.set()
    threading.Thread(target=_run,daemon=True).start()
    i=0
    while not done.wait(0.1):
        print(f" {DIM}{frames[i%len(frames)]} Thinking...{R}",end="\r",flush=True); i+=1
    print(f" {' '*25}\r",end="")
    if error[0]: raise error[0]
    return result[0]

# ══════════════════════════════════════════════════════════
# PRINT HELPERS & SETUP
# ══════════════════════════════════════════════════════════
def bot_say(text, colour=MAG, source="Cortana"):
    print(f"\n {colour}{B}{source}:{R} ",end="")
    words,line,first=text.split(),"",True
    for w in words:
        if len(line)+len(w)+1>66:
            print(("" if first else " ")+line); line,first=w,False
        else: line=(line+" "+w).strip()
    if line: print(("" if first else " ")+line)
    print()

def divider(): print(f" {DIM}{'─'*54}{R}")

def setup_groq_key():
    os.system("clear")
    print(f"\n{CYN}{'═'*52}{R}\n{B}{WHT} CORTANA — GROQ SETUP{R}\n{CYN}{'═'*52}{R}\n")
    print(f" 1. Open: {CYN}https://console.groq.com{R}\n 2. API Keys → Create Key\n")
    key=input(f" {WHT}Paste Groq key:{R} ").strip()
    if not key: return None
    print(f"\n {DIM}Validating...{R}",end="",flush=True)
    try:
        reply=groq_chat(key,[{"role":"system","content":"test"},
                             {"role":"user","content":"Say OK"}])
        if reply:
            print(f"\r {GRN}✓ Connected!{R}\n")
            cfg=load_config(); cfg["groq_api_key"]=key; save_config(cfg)
            time.sleep(1); return key
    except Exception as ex: print(f"\r {RED}{ex}{R}"); time.sleep(2)
    return None

# ══════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════
def main():
    brain   = load_brain()
    cfg     = load_config()
    groq_key= cfg.get("groq_api_key","").strip()

    print(f"\n{CYN}{'═'*54}{R}")
    print(f"{B}{WHT} CORTANA v6.0-MINT — Personal AI{R}")
    print(f"{CYN}{'═'*54}{R}")
    print(f" {GRN+'Groq ✓'+R if groq_key else YLW+'Offline'+R}"
          f" | {'PDF ✓' if PDF_AVAILABLE else YLW+'pip install pypdf'+R}"
          f" | {'Selenium ✓' if SELENIUM_AVAILABLE else YLW+'pip install selenium'+R}")
    print(f" {DIM}Brain:{len(brain)} entries | Model:{GROQ_MODEL}{R}")
    print(f"{CYN}{'═'*54}{R}\n")
    print(f" {DIM}Chat    : just talk naturally{R}")
    print(f" {DIM}Device  : battery · wifi · storage{R}")
    print(f" {DIM}Music   : play/download/stop a song{R}")
    print(f" {DIM}Movies  : download movie [title] · browse movie [title]{R}")
    print(f" {DIM}Finance : mpesa pdf [password]{R}")
    print(f" {BLU}IG Mgmt : analyse instagram · unfollow 30 · ig stats{R}")
    print(f" {BLU}IG Auto : start dm loop · comments{R}\n")

    if cfg.get("user_name"): bot_say(f"Welcome back, {cfg['user_name']}! What do you need?")
    else: bot_say("Hey! I'm Cortana. What should I call you?")

    if not groq_key and input(f" {DIM}Set up Groq? (y/n):{R} ").strip().lower()=="y":
        groq_key=setup_groq_key() or ""
        os.system("clear")

    system_msg={"role":"system","content":build_system_prompt(cfg,brain)}
    history=[system_msg]

    while True:
        divider()
        try: user_input=input(f" {CYN}You:{R} ").strip()
        except (EOFError,KeyboardInterrupt): bot_say("Catch you later!",GRN); break
        if not user_input: continue
        lower=user_input.lower().strip()

        if lower in ("quit","exit","q"):   bot_say("See you later, Geoffrey!",GRN); break
        if lower=="setup groq":            groq_key=setup_groq_key() or groq_key; os.system("clear"); continue
        if lower=="clear":
            system_msg={"role":"system","content":build_system_prompt(cfg,load_brain())}
            history=[system_msg]; bot_say("Conversation cleared.",DIM); continue
        if lower=="clear brain":
            if input(f" {RED}Reset brain? (yes/no):{R} ").strip().lower()=="yes":
                brain=dict(DEFAULT_BRAIN); save_brain(brain); bot_say("Brain reset.",YLW)
            continue

        rule=apply_smart_rules(user_input,cfg)
        if rule: bot_say(rule); continue

        reply,_=detect_hard_intent(lower,cfg)
        if reply is not None: bot_say(reply); continue

        if not groq_key:
            if lower in brain: bot_say(brain[lower],MAG,"Cortana (memory)"); continue
            fkey=fuzzy_find(lower,brain)
            if fkey: bot_say(brain[fkey],MAG,f"Cortana (matched '{fkey}')"); continue
            print(f" {YLW}I don't know that, and I'm offline.{R}")
            teach=input(f" {DIM}Teach me (or Enter to skip):{R} ").strip()
            if teach: brain[lower]=teach; save_brain(brain); print(f" {GRN}Saved!{R}")
            continue

        history.append({"role":"user","content":user_input})
        history[0]={"role":"system","content":build_system_prompt(cfg,load_brain())}

        for turn in range(2):
            try:
                raw=spinner_while(groq_chat,groq_key,history)
                history.append({"role":"assistant","content":raw})

                sys_match=re.search(r"<<SYS:\s*(.*?)>>",raw,re.DOTALL)
                cmd_match=re.search(r"<<CMD:\s*(.*?)>>",raw,re.DOTALL)
                clean_reply=re.sub(r"<<.*?>>","",raw,flags=re.DOTALL).strip()

                if clean_reply: bot_say(clean_reply,MAG,"Cortana")

                if not sys_match and not cmd_match:
                    if turn==0 and clean_reply:
                        if input(f" {DIM}Save to memory? (y/n):{R} ").strip().lower()=="y":
                            brain[lower]=clean_reply; save_brain(brain)
                            print(f" {GRN}Saved.{R}")
                    break

                out_text=""
                if sys_match:
                    sys_cmd=sys_match.group(1).strip()
                    if not action_requested(lower, sys_cmd):
                        print(f" {YLW}⚠ Blocked uninstructed: {sys_cmd}{R}")
                        break
                    print(f" {CYN}Module:{R} {DIM}{sys_cmd}{R}")
                    out_text=run_internal_module(sys_cmd,cfg)
                    brain=load_brain()
                elif cmd_match:
                    out_text=confirm_and_run(cmd_match.group(1).strip())

                if turn==0:
                    history.append({"role":"user",
                                    "content":f"[SYSTEM OBSERVATION]\n{out_text}\n(Summarise briefly.)"})
                    history[0]={"role":"system","content":build_system_prompt(cfg,load_brain())}
                else:
                    if out_text and "ledger printed" not in out_text and "printed." not in out_text:
                        print(f"\n {DIM}[Result: {str(out_text)[:150]}]{R}")

            except urllib.error.HTTPError as e:
                if e.code==429:
                    COOLDOWN=60
                    cooldown_end=time.time()+COOLDOWN
                    bot_say(f"Rate limit hit — offline mode for ~{COOLDOWN}s.",YLW)
                    bot_say(offline_reply(user_input,load_brain()),DIM,"Cortana (offline)")
                    while time.time()<cooldown_end:
                        remaining=int(cooldown_end-time.time())
                        print(f" {DIM}{'─'*54}{R}")
                        print(f" {DIM}[Offline — Groq back in ~{remaining}s]{R}")
                        try: next_input=input(f" {CYN}You:{R} ").strip()
                        except (EOFError,KeyboardInterrupt): bot_say("Catch you later!",GRN); return
                        if not next_input: continue
                        next_lower=next_input.lower().strip()
                        if next_lower in ("quit","exit","q"): bot_say("See you later!",GRN); return
                        rule=apply_smart_rules(next_input,cfg)
                        if rule: bot_say(rule,MAG,"Cortana (offline)"); continue
                        hard,_=detect_hard_intent(next_lower,cfg)
                        if hard: bot_say(hard,MAG,"Cortana (offline)"); continue
                        bot_say(offline_reply(next_input,load_brain()),DIM,"Cortana (offline)")
                    print(f"\n {GRN}✓ Groq back online.{R}\n")
                elif e.code==401:
                    bot_say("Key rejected — type 'setup groq'.",RED); groq_key=""
                else:
                    bot_say(f"Groq error {e.code}.",YLW)
                break
            except Exception as ex:
                bot_say(f"Connection issue: {ex}",YLW); break

        if len(history)>13: history=[history[0]]+history[-12:]

    if _ig_driver is not None:
        try: _ig_driver.quit()
        except Exception: pass

    print(f"\n {DIM}Session ended. Brain:{len(brain)} entries.{R}\n")

if __name__=="__main__":
    main()
