#!/usr/bin/env python3
"""Publication automatique sur Instagram (API Instagram avec connexion Instagram).

Chaque post est un dossier dans file/ contenant un post.json et ses médias.
Le workflow GitHub Actions lance ce script toutes les heures : il publie le plus
ancien post arrivé à échéance, puis déplace son dossier dans publies/ (ou dans
erreurs/ après 3 échecs).

Commandes :
  python publish.py publier            publie le post dû le plus ancien (au plus un)
  python publish.py publier --essai    montre ce qui serait publié, sans rien envoyer
  python publish.py verifier           vérifie le jeton et affiche le compte connecté
  python publish.py valider            vérifie tous les post.json de file/ (hors ligne)
  python publish.py renouveler         renouvelle le jeton et l'écrit sur la sortie

Variables d'environnement :
  IG_ACCESS_TOKEN   jeton longue durée (secret GitHub)
  PAGES_BASE_URL    ex. https://utilisateur.github.io/depot
  IG_API_VERSION    version de l'API Graph (défaut v24.0)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent
FILE = RACINE / "file"
PUBLIES = RACINE / "publies"
ERREURS = RACINE / "erreurs"
FUSEAU = ZoneInfo("Europe/Brussels")
VERSION = os.environ.get("IG_API_VERSION", "v24.0")


def jeton_instagram() -> bool:
    """Jeton « connexion Instagram » (IGAA…) ou jeton Facebook (EAA…, connexion unifiée)."""
    return os.environ.get("IG_ACCESS_TOKEN", "").startswith("IG")


def api_base() -> str:
    hote = "graph.instagram.com" if jeton_instagram() else "graph.facebook.com"
    return f"https://{hote}/{VERSION}"
MAX_TENTATIVES = 3
LEGENDE_MAX = 2200
HASHTAGS_MAX = 30

EXT_IMAGE = {".jpg", ".jpeg"}
EXT_VIDEO = {".mp4", ".mov"}


class ErreurPost(Exception):
    """Post mal formé : inutile de réessayer."""


class ErreurAPI(Exception):
    """Erreur renvoyée par Instagram : on peut réessayer à l'heure suivante."""


# --------------------------------------------------------------------------- #
# Lecture et validation des posts
# --------------------------------------------------------------------------- #

def lire_date(valeur: str) -> datetime:
    dt = datetime.fromisoformat(valeur)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=FUSEAU)
    return dt


def charger_post(dossier: Path) -> dict:
    fichier = dossier / "post.json"
    if not fichier.exists():
        raise ErreurPost(f"{dossier.name} : post.json manquant")
    try:
        post = json.loads(fichier.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ErreurPost(f"{dossier.name} : post.json illisible ({e})")

    type_ = post.get("type")
    if type_ not in {"image", "carrousel", "reel"}:
        raise ErreurPost(f"{dossier.name} : type doit être image, carrousel ou reel")

    if "publier_le" not in post:
        raise ErreurPost(f"{dossier.name} : publier_le manquant")
    try:
        post["_date"] = lire_date(post["publier_le"])
    except ValueError:
        raise ErreurPost(f"{dossier.name} : publier_le n'est pas une date ISO valide")

    legende = post.get("legende", "")
    if len(legende) > LEGENDE_MAX:
        raise ErreurPost(f"{dossier.name} : légende trop longue ({len(legende)} > {LEGENDE_MAX})")
    if legende.count("#") > HASHTAGS_MAX:
        raise ErreurPost(f"{dossier.name} : plus de {HASHTAGS_MAX} hashtags")

    medias = post.get("medias") or []
    if not medias:
        raise ErreurPost(f"{dossier.name} : aucun média")
    for nom in medias + ([post["couverture"]] if post.get("couverture") else []):
        if not (dossier / nom).exists():
            raise ErreurPost(f"{dossier.name} : fichier introuvable {nom}")

    exts = [Path(m).suffix.lower() for m in medias]
    if type_ == "image":
        if len(medias) != 1 or exts[0] not in EXT_IMAGE:
            raise ErreurPost(f"{dossier.name} : un post image = exactement 1 fichier JPEG")
    elif type_ == "reel":
        if len(medias) != 1 or exts[0] not in EXT_VIDEO:
            raise ErreurPost(f"{dossier.name} : un reel = exactement 1 fichier MP4/MOV")
        if post.get("couverture") and Path(post["couverture"]).suffix.lower() not in EXT_IMAGE:
            raise ErreurPost(f"{dossier.name} : la couverture doit être un JPEG")
    else:
        if not 2 <= len(medias) <= 10:
            raise ErreurPost(f"{dossier.name} : un carrousel = 2 à 10 médias")
        for e in exts:
            if e not in EXT_IMAGE | EXT_VIDEO:
                raise ErreurPost(f"{dossier.name} : format non pris en charge {e} (JPEG ou MP4)")
    return post


def lire_etat(dossier: Path) -> dict:
    f = dossier / ".etat.json"
    return json.loads(f.read_text()) if f.exists() else {"tentatives": 0}


def ecrire_etat(dossier: Path, etat: dict) -> None:
    (dossier / ".etat.json").write_text(json.dumps(etat, ensure_ascii=False, indent=2))


def posts_dus(maintenant: datetime) -> tuple[list[tuple[Path, dict]], list[str]]:
    dus, invalides = [], []
    for dossier in sorted(p for p in FILE.iterdir() if p.is_dir()):
        try:
            post = charger_post(dossier)
        except ErreurPost as e:
            invalides.append(str(e))
            continue
        if post["_date"] <= maintenant:
            dus.append((dossier, post))
    dus.sort(key=lambda x: x[1]["_date"])
    return dus, invalides


# --------------------------------------------------------------------------- #
# Appels à l'API
# --------------------------------------------------------------------------- #

def appel(methode: str, chemin: str, params: dict | None = None, base: str | None = None) -> dict:
    base = base or api_base()
    params = dict(params or {})
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    url = f"{base}/{chemin}"
    donnees = None
    if methode == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        donnees = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=donnees, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        corps = e.read().decode(errors="replace")
        try:
            msg = json.loads(corps)["error"]["message"]
        except Exception:
            msg = corps[:300]
        raise ErreurAPI(f"{methode} {chemin} → HTTP {e.code} : {msg}") from None


def url_accessible(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def attendre_conteneur(conteneur_id: str, limite_s: int = 900) -> None:
    debut = time.time()
    while True:
        etat = appel("GET", conteneur_id, {"fields": "status_code,status"})
        code = etat.get("status_code")
        if code == "FINISHED":
            return
        if code in {"ERROR", "EXPIRED"}:
            raise ErreurAPI(f"traitement du média refusé par Instagram : {etat.get('status')}")
        if time.time() - debut > limite_s:
            raise ErreurAPI("traitement du média trop long (plus de 15 min)")
        time.sleep(10)


def id_utilisateur() -> str:
    """Identifiant du compte Instagram professionnel à publier."""
    if os.environ.get("IG_USER_ID"):
        return os.environ["IG_USER_ID"]
    if jeton_instagram():
        return appel("GET", "me", {"fields": "user_id,username"})["user_id"]
    # Jeton Facebook (connexion unifiée) : on cherche le compte parmi ceux accessibles.
    voulu = os.environ.get("IG_USERNAME", "penserresonner").lower()
    trouves = []
    for chemin, champ in (("me/accounts", "instagram_business_account{id,username}"),
                          ("me/instagram_accounts", "id,username")):
        try:
            data = appel("GET", chemin, {"fields": champ, "limit": "100"}).get("data", [])
        except ErreurAPI:
            continue
        for d in data:
            compte = d.get("instagram_business_account", d)
            if compte.get("id"):
                trouves.append(compte)
    for c in trouves:
        if c.get("username", "").lower() == voulu:
            return c["id"]
    noms = ", ".join(f"@{c.get('username')} ({c['id']})" for c in trouves) or "aucun"
    raise ErreurAPI(f"compte @{voulu} introuvable avec ce jeton (comptes vus : {noms}). "
                    f"Ajoute la variable IG_USER_ID.")


def creer_conteneur(uid: str, url_media: str, est_video: bool, extra: dict) -> str:
    params = dict(extra)
    if est_video:
        params.setdefault("media_type", "VIDEO")
        params["video_url"] = url_media
    else:
        params["image_url"] = url_media
    return appel("POST", f"{uid}/media", params)["id"]


def publier_post(dossier: Path, post: dict, base_url: str) -> dict:
    url = lambda nom: f"{base_url}/file/{urllib.parse.quote(dossier.name)}/{urllib.parse.quote(nom)}"
    for nom in post["medias"] + ([post["couverture"]] if post.get("couverture") else []):
        if not url_accessible(url(nom)):
            raise ErreurAPI(f"média pas encore en ligne sur GitHub Pages : {url(nom)}")

    uid = id_utilisateur()
    legende = post.get("legende", "")
    type_ = post["type"]

    if type_ == "image":
        cid = creer_conteneur(uid, url(post["medias"][0]), False, {"caption": legende})
        attendre_conteneur(cid)
    elif type_ == "reel":
        extra = {
            "media_type": "REELS",
            "caption": legende,
            "share_to_feed": "true" if post.get("partager_dans_le_fil", True) else "false",
        }
        if post.get("couverture"):
            extra["cover_url"] = url(post["couverture"])
        elif "image_couverture_ms" in post:
            extra["thumb_offset"] = str(int(post["image_couverture_ms"]))
        cid = creer_conteneur(uid, url(post["medias"][0]), True, extra)
        attendre_conteneur(cid)
    else:
        enfants = []
        for nom in post["medias"]:
            video = Path(nom).suffix.lower() in EXT_VIDEO
            e = creer_conteneur(uid, url(nom), video, {"is_carousel_item": "true"})
            attendre_conteneur(e)
            enfants.append(e)
        cid = appel("POST", f"{uid}/media", {
            "media_type": "CAROUSEL", "children": ",".join(enfants), "caption": legende,
        })["id"]
        attendre_conteneur(cid)

    media_id = appel("POST", f"{uid}/media_publish", {"creation_id": cid})["id"]
    try:
        lien = appel("GET", media_id, {"fields": "permalink"}).get("permalink")
    except ErreurAPI:
        lien = None
    return {"media_id": media_id, "lien": lien}


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #

def deplacer(dossier: Path, cible: Path) -> Path:
    dest = cible / dossier.name
    if dest.exists():
        dest = cible / f"{dossier.name}-{int(time.time())}"
    shutil.move(str(dossier), str(dest))
    return dest


def cmd_publier(essai: bool) -> int:
    maintenant = datetime.now(timezone.utc)
    dus, invalides = posts_dus(maintenant)
    for e in invalides:
        print(f"❌ Post ignoré (à corriger) : {e}")
    code_invalides = 1 if invalides else 0
    if not dus:
        print("Rien à publier pour l'instant.")
        return code_invalides

    dossier, post = dus[0]
    print(f"Post dû : {dossier.name} ({post['type']}, prévu le {post['publier_le']})")
    if len(dus) > 1:
        print(f"  ({len(dus) - 1} autre(s) en attente, publiés aux prochaines heures)")
    if essai:
        print("Mode essai : rien n'est envoyé.")
        return code_invalides

    base_url = os.environ["PAGES_BASE_URL"].rstrip("/")
    etat = lire_etat(dossier)
    try:
        resultat = publier_post(dossier, post, base_url)
    except ErreurAPI as e:
        etat["tentatives"] += 1
        etat["derniere_erreur"] = str(e)
        etat["derniere_tentative"] = maintenant.isoformat()
        ecrire_etat(dossier, etat)
        print(f"❌ Échec ({etat['tentatives']}/{MAX_TENTATIVES}) : {e}")
        if etat["tentatives"] >= MAX_TENTATIVES:
            dest = deplacer(dossier, ERREURS)
            print(f"   Abandon : déplacé dans {dest.relative_to(RACINE)}")
        return 1

    etat.update(resultat, publie_le=maintenant.isoformat())
    ecrire_etat(dossier, etat)
    dest = deplacer(dossier, PUBLIES)
    print(f"✅ Publié : {resultat.get('lien') or resultat['media_id']}")
    print(f"   Dossier archivé dans {dest.relative_to(RACINE)}")
    return code_invalides


def cmd_verifier() -> int:
    print(f"Type de jeton : {'connexion Instagram' if jeton_instagram() else 'connexion unifiée (Facebook)'}")
    uid = id_utilisateur()
    moi = appel("GET", uid, {"fields": "username,media_count"})
    print(f"✅ Jeton valide : @{moi.get('username')}, {moi.get('media_count')} publications, id {uid}")
    try:
        quota = appel("GET", f"{uid}/content_publishing_limit",
                      {"fields": "quota_usage,config"})
        print(f"   Quota de publication : {json.dumps(quota.get('data', quota))}")
    except ErreurAPI as e:
        print(f"   (quota non lisible : {e})")
    return 0


def cmd_valider() -> int:
    erreurs = 0
    dossiers = sorted(p for p in FILE.iterdir() if p.is_dir())
    for dossier in dossiers:
        try:
            post = charger_post(dossier)
            print(f"✅ {dossier.name} : {post['type']}, {len(post['medias'])} média(s), "
                  f"{post['_date'].astimezone(FUSEAU):%a %d/%m %H:%M}")
        except ErreurPost as e:
            erreurs += 1
            print(f"❌ {e}")
    if not dossiers:
        print("File vide.")
    return 1 if erreurs else 0


def cmd_renouveler() -> int:
    if not jeton_instagram():
        print("Jeton de connexion unifiée : il n'expire pas, rien à renouveler.", file=sys.stderr)
        return 3
    r = appel("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"},
              base="https://graph.instagram.com")
    jours = int(r.get("expires_in", 0)) // 86400
    print(f"Jeton renouvelé, valable {jours} jours.", file=sys.stderr)
    print(r["access_token"])
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"publier", "verifier", "valider", "renouveler"}:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "valider":
        return cmd_valider()
    if "IG_ACCESS_TOKEN" not in os.environ and not (cmd == "publier" and "--essai" in argv):
        print("❌ IG_ACCESS_TOKEN absent.")
        return 2
    try:
        if cmd == "publier":
            return cmd_publier("--essai" in argv)
        if cmd == "verifier":
            return cmd_verifier()
        return cmd_renouveler()
    except ErreurAPI as e:
        print(f"❌ {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
