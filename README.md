# Publication automatique — @penserresonner

Une file d'attente de posts Instagram, publiée automatiquement par GitHub Actions
via l'API officielle d'Instagram. Gratuit, sans serveur.

## Fonctionnement

1. Chaque post est un dossier dans `file/` : un `post.json` et ses médias.
2. Toutes les 30 minutes (à HH:07 et HH:37), le workflow **Publier sur Instagram** publie
   le plus ancien post dont la date est passée — un seul par passage.
3. Le dossier publié part dans `publies/` avec le lien du post dans `.etat.json`.
   Après 3 échecs, il part dans `erreurs/` et GitHub t'envoie un mail.

Les médias sont servis par GitHub Pages, car Instagram exige une adresse publique
pour chaque fichier. **Ce dépôt est donc public** : ne mets rien ici qui ne soit
destiné à être publié.

## Format d'un post

`file/2026-11-20-titre-court/post.json`

```json
{
  "publier_le": "2026-11-20T18:30:00+01:00",
  "type": "reel",
  "legende": "Texte de la légende.\n\n#penserresonner",
  "medias": ["video.mp4"],
  "couverture": "couverture.jpg",
  "partager_dans_le_fil": true
}
```

| Type | Médias | Contraintes |
|---|---|---|
| `image` | 1 JPEG | ratio entre 4:5 et 1.91:1, 8 Mo max |
| `carrousel` | 2 à 10 JPEG ou MP4 | même ratio pour toutes les images |
| `reel` | 1 MP4 (H.264, AAC) | 9:16 conseillé, 3 s à 15 min ; `couverture` (JPEG) facultative |

Légende : 2 200 caractères et 30 hashtags au maximum. Une date sans fuseau est
lue à l'heure de Bruxelles. Avec un passage toutes les 30 minutes, un post part au plus tard
une demi-heure après l'heure prévue (parfois un peu plus : GitHub retarde les tâches
planifiées aux heures chargées).

## Installation (une seule fois)

### 1. Instagram
Le compte doit être **Professionnel** ou **Créateur**
(Instagram → Paramètres → Type de compte et outils).

### 2. Application Meta et jeton
Application : **Penser Resonner Publication** (portefeuille Nectart), cas
d'utilisation *API Instagram*, configuration « connexion unifiée ».

1. @penserresonner est ajouté comme *Testeur(se) Instagram* (Rôles dans
   l'application) ; l'invitation s'accepte sur
   <https://www.instagram.com/accounts/manage_access/> → *Invitations de testeur*.
2. Cas d'utilisation → API Instagram → *API setup with Unified login* →
   **2. Générez des tokens d'accès** → *Ajouter un compte*, puis générer le jeton.

Le jeton de connexion unifiée (`EAA…`) **n'expire pas**. Le script accepte aussi
un jeton « connexion Instagram » (`IGAA…`, 60 jours) ; seul ce dernier a besoin
du workflow de renouvellement et du secret `GH_PAT`.

L'application peut rester en mode *Développement* : tu publies sur ton propre
compte, aucune validation de Meta n'est nécessaire.

### 3. Secrets GitHub
Dépôt → Settings → Secrets and variables → Actions :

- secret `IG_ACCESS_TOKEN` : le jeton Meta.
- variable `IG_USER_ID` (facultative) : l'identifiant du compte Instagram, si le
  script ne le trouve pas tout seul (il l'affiche avec l'action `verifier`).
- secret `GH_PAT` : seulement pour un jeton `IGAA…` (voir ci-dessus).

### 4. Vérifier
Actions → *Publier sur Instagram* → *Run workflow* → action `verifier`.
Le journal doit afficher `✅ Jeton valide : @penserresonner`.

## Commandes locales

```bash
python3 publish.py valider            # contrôle les post.json de file/
python3 publish.py publier --essai    # montre ce qui partirait maintenant
```

## Bon à savoir
- Limite Instagram : 100 publications par 24 h — très au-delà d'un post par jour.
- GitHub désactive les tâches planifiées d'un dépôt public après 60 jours sans
  activité ; chaque publication crée un commit, ce qui suffit à l'éviter.
- Pour annuler un post programmé, supprime son dossier de `file/`.
