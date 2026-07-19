#!/usr/bin/env python3
# Publie le carrousel remisedebail du jour sur Instagram ET Facebook (API Graph).
# Idempotent par canal (1x/jour/canal) via last.json {"ig":date,"fb":date}.
import json, os, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

TOKEN = os.environ["IG_TOKEN"]          # page access token (sert IG + FB)
IGID  = os.environ.get("IG_USER_ID","") # IG business account id
FBID  = os.environ.get("FB_PAGE_ID","") # Facebook page id
V = "v21.0"; BASE = f"https://graph.facebook.com/{V}/"

def post(path, params):
    params = dict(params); params["access_token"] = TOKEN
    req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(params).encode())
    try: return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e: raise SystemExit("ERREUR API POST "+path+": "+e.read().decode()[:600])

def get(path, params):
    params = dict(params); params["access_token"] = TOKEN
    return json.load(urllib.request.urlopen(BASE + path + "?" + urllib.parse.urlencode(params)))

try:
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%d")
except Exception:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

state = {}
if os.path.exists("last.json"):
    try: state = json.load(open("last.json"))
    except Exception: state = {}

posts = json.load(open("schedule.json", encoding="utf-8"))
todays = [p for p in posts if p["date"] == today]
if not todays:
    print("Aucun post prevu pour", today); raise SystemExit(0)
p = todays[0]; imgs = p["images"]; cap = p["caption"]
print(f"Jour {p['jour']} ({p.get('slug','')}) - {len(imgs)} image(s) - {today}")

# ---------- Instagram ----------
if IGID and state.get("ig") != today:
    try:
        if len(imgs) == 1:
            cid = post(f"{IGID}/media", {"image_url": imgs[0], "caption": cap})["id"]
        else:
            children = []
            for u in imgs:
                children.append(post(f"{IGID}/media", {"image_url": u, "is_carousel_item": "true"})["id"]); time.sleep(2)
            cid = post(f"{IGID}/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": cap})["id"]
        for _ in range(24):
            st = get(cid, {"fields": "status_code"}).get("status_code", "")
            if st == "FINISHED": break
            if st == "ERROR": raise SystemExit("IG conteneur ERREUR")
            time.sleep(5)
        print("IG publie:", post(f"{IGID}/media_publish", {"creation_id": cid}))
        state["ig"] = today
    except SystemExit as e:
        print("IG echec:", e)
else:
    print("IG: saute (deja publie ou pas d'IG_USER_ID)")

# ---------- Facebook ----------
if FBID and state.get("fb") != today:
    try:
        media = []
        for u in imgs:
            pid = post(f"{FBID}/photos", {"url": u, "published": "false"})["id"]; media.append({"media_fbid": pid}); time.sleep(1)
        params = {"message": cap}
        for i, m in enumerate(media): params[f"attached_media[{i}]"] = json.dumps(m)
        print("FB publie:", post(f"{FBID}/feed", params))
        state["fb"] = today
    except SystemExit as e:
        print("FB echec:", e)
else:
    print("FB: saute (deja publie ou pas de FB_PAGE_ID)")

json.dump(state, open("last.json", "w"))
print("etat:", state)
