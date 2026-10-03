#!/usr/bin/env python3
# Publie / programme les reels remisedebail sur Facebook ET Instagram, avec image de couverture.
#
#   python publish_reels.py schedule-fb   -> programme cote Facebook (scheduled_publish_time)
#   python publish_reels.py publish-ig    -> publie sur Instagram les reels du jour (IG ne se programme pas)
#
# Etat dans reels_state.json : {"<cle>": {"fb": "<video_id>", "fb_etat": "SCHEDULED|PUBLISHED",
#                                          "ig": "<media_id>"}} -> idempotent par canal.
import json, os, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta, timezone

TOKEN = os.environ["IG_TOKEN"]            # page access token permanent (sert IG + FB)
IG_ID = os.environ["IG_USER_ID"]
FB_PAGE = os.environ["FB_PAGE_ID"]
V = "v21.0"
BASE = f"https://graph.facebook.com/{V}/"
RAW = "https://raw.githubusercontent.com/Nuredin-Moh/remisedebail-ig/main/"
ETAT = "reels_state.json"

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Zurich")
except Exception:
    TZ = timezone(timedelta(hours=2))


def post(path, params, base=BASE):
    params = dict(params)
    params["access_token"] = TOKEN
    req = urllib.request.Request(base + path, data=urllib.parse.urlencode(params).encode())
    try:
        return json.load(urllib.request.urlopen(req, timeout=120)), None
    except urllib.error.HTTPError as e:
        return None, e.read().decode()[:500]


def get(path, params):
    params = dict(params)
    params["access_token"] = TOKEN
    try:
        return json.load(urllib.request.urlopen(BASE + path + "?" + urllib.parse.urlencode(params), timeout=60)), None
    except urllib.error.HTTPError as e:
        return None, e.read().decode()[:500]


def envoyer_fichier(video_id, chemin):
    """Phase upload : envoi binaire vers rupload.facebook.com."""
    taille = os.path.getsize(chemin)
    url = f"https://rupload.facebook.com/video-upload/{V}/{video_id}"
    with open(chemin, "rb") as f:
        data = f.read()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", "OAuth " + TOKEN)
    req.add_header("offset", "0")
    req.add_header("file_size", str(taille))
    req.add_header("Content-Type", "application/octet-stream")
    try:
        return json.load(urllib.request.urlopen(req, timeout=600)), None
    except urllib.error.HTTPError as e:
        return None, e.read().decode()[:500]


def poser_couverture(video_id, chemin):
    """Image de couverture personnalisee du reel : POST /{video_id}/thumbnails (multipart)."""
    limite = "----remisedebail" + str(int(time.time()))
    with open(chemin, "rb") as f:
        img = f.read()
    corps = b""
    for cle, val in (("access_token", TOKEN), ("is_preferred", "true")):
        corps += ("--" + limite + "\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (cle, val)).encode()
    corps += ("--" + limite + "\r\nContent-Disposition: form-data; name=\"source\"; filename=\"cover.jpg\"\r\n"
              "Content-Type: image/jpeg\r\n\r\n").encode() + img + b"\r\n"
    corps += ("--" + limite + "--\r\n").encode()
    req = urllib.request.Request(BASE + video_id + "/thumbnails", data=corps, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + limite)
    try:
        return json.load(urllib.request.urlopen(req, timeout=120)), None
    except urllib.error.HTTPError as e:
        return None, e.read().decode()[:500]


def charger_etat():
    if os.path.exists(ETAT):
        try:
            return json.load(open(ETAT))
        except Exception:
            return {}
    return {}


def ecrire_etat(etat):
    json.dump(etat, open(ETAT, "w"), indent=1, ensure_ascii=False)


def horaire(entree):
    h, m = entree.get("heure", "18:00").split(":")
    d = datetime.strptime(entree["date"], "%Y-%m-%d")
    return datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=TZ)


def facebook(entree, etat, programmer):
    cle = entree["cle"]
    fiche = etat.setdefault(cle, {})
    if fiche.get("fb"):
        print(f"  FB deja fait ({fiche.get('fb_etat')}) : {fiche['fb']}")
        return []
    erreurs = []
    r, err = post(f"{FB_PAGE}/video_reels", {"upload_phase": "start"})
    if err:
        return [f"FB start : {err}"]
    video_id = r["video_id"]
    print(f"  FB video_id {video_id}")
    r, err = envoyer_fichier(video_id, entree["video"])
    if err:
        return [f"FB upload : {err}"]
    params = {"video_id": video_id, "upload_phase": "finish", "description": entree["caption"]}
    if programmer:
        params["video_state"] = "SCHEDULED"
        params["scheduled_publish_time"] = str(int(horaire(entree).timestamp()))
    else:
        params["video_state"] = "PUBLISHED"
    r, err = post(f"{FB_PAGE}/video_reels", params)
    if err:
        return [f"FB finish : {err}"]
    fiche["fb"] = video_id
    fiche["fb_etat"] = "SCHEDULED" if programmer else "PUBLISHED"
    print(f"  FB {fiche['fb_etat']} OK")
    r, err = poser_couverture(video_id, entree["cover"])
    if err:
        erreurs.append(f"FB couverture : {err}")
    else:
        fiche["fb_cover"] = True
        print("  FB couverture posee")
    return erreurs


def instagram(entree, etat):
    cle = entree["cle"]
    fiche = etat.setdefault(cle, {})
    if fiche.get("ig"):
        print(f"  IG deja publie : {fiche['ig']}")
        return []
    r, err = post(f"{IG_ID}/media", {
        "media_type": "REELS",
        "video_url": RAW + entree["video"],
        "cover_url": RAW + entree["cover"],
        "caption": entree["caption"],
        "share_to_feed": "true",
    })
    if err:
        return [f"IG conteneur : {err}"]
    cid = r["id"]
    print(f"  IG conteneur {cid}")
    for essai in range(40):
        time.sleep(15)
        s, err = get(cid, {"fields": "status_code,status"})
        if err:
            return [f"IG statut : {err}"]
        code = s.get("status_code")
        print(f"   statut {code}")
        if code == "FINISHED":
            break
        if code == "ERROR":
            return [f"IG traitement ERROR : {s.get('status')}"]
    else:
        return ["IG : conteneur jamais FINISHED"]
    r, err = post(f"{IG_ID}/media_publish", {"creation_id": cid})
    if err:
        return [f"IG publication : {err}"]
    fiche["ig"] = r["id"]
    print(f"  IG publie {r['id']}")
    return []


def story_facebook(entree, etat):
    """Partage en story de la Page (regle : toujours partager en story Facebook)."""
    fiche = etat.setdefault(entree["cle"], {})
    if fiche.get("fb_story"):
        print(f"  Story FB deja faite : {fiche['fb_story']}")
        return []
    r, err = post(f"{FB_PAGE}/video_stories", {"upload_phase": "start"})
    if err:
        return [f"Story start : {err}"]
    video_id = r["video_id"]
    taille = os.path.getsize(entree["video"])
    with open(entree["video"], "rb") as f:
        data = f.read()
    req = urllib.request.Request(r.get("upload_url") or f"https://rupload.facebook.com/video-upload/{V}/{video_id}",
                                 data=data, method="POST")
    req.add_header("Authorization", "OAuth " + TOKEN)
    req.add_header("offset", "0")
    req.add_header("file_size", str(taille))
    req.add_header("Content-Type", "application/octet-stream")
    try:
        json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        return [f"Story upload : {e.read().decode()[:500]}"]
    r, err = post(f"{FB_PAGE}/video_stories", {"upload_phase": "finish", "video_id": video_id})
    if err:
        return [f"Story finish : {err}"]
    fiche["fb_story"] = r.get("post_id") or video_id
    print(f"  Story FB publiee {fiche['fb_story']}")
    return []


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "publish-ig"
    entrees = json.load(open("reels.json", encoding="utf-8"))
    etat = charger_etat()
    maintenant = datetime.now(TZ)
    erreurs = []
    for e in entrees:
        quand = horaire(e)
        if mode == "schedule-fb":
            if quand < maintenant + timedelta(minutes=11):
                print(f"{e['cle']} : trop proche pour une programmation FB, saute")
                continue
            print(f"{e['cle']} : programmation Facebook pour {quand:%d.%m.%Y %H:%M}")
            erreurs += facebook(e, etat, programmer=True)
        else:
            if e["date"] != maintenant.strftime("%Y-%m-%d"):
                continue
            if maintenant < quand - timedelta(minutes=20):
                print(f"{e['cle']} : prevu a {quand:%H:%M}, trop tot")
                continue
            print(f"{e['cle']} : publication du jour")
            erreurs += instagram(e, etat)
            fiche = etat.get(e["cle"], {})
            if not fiche.get("fb"):
                erreurs += facebook(e, etat, programmer=False)
            erreurs += story_facebook(e, etat)
    ecrire_etat(etat)
    print("ETAT:", json.dumps(etat, ensure_ascii=False))
    if erreurs:
        print("ERREURS:")
        for x in erreurs:
            print(" -", x)
        raise SystemExit(1)
    print("OK")


if __name__ == "__main__":
    main()
