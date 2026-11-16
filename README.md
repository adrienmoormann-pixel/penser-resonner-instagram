# Publication automatique — @penserresonner

Une file d'attente de posts Instagram, publiée automatiquement par GitHub Actions
via l'API officielle d'Instagram. Gratuit, sans serveur.

## Fonctionnement

1. Chaque post est un dossier dans `file/` : un `post.json` et ses médias.
2. Toutes les heures (à HH:17 UTC), le workflow **Publier sur Instagram** publie
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
lue à l'heure de Bruxelles. Avec un passage par heure, un post part au plus tard
une heure après l'heure prévue (parfois un peu plus : GitHub retarde les tâches
planifiées aux heures chargées).

## Installation (une seule fois)

### 1. Instagram
Le compte doit être **Professionnel** ou **Créateur**
(Instagram → Paramètres → Type de compte et outils).

### 2. Application Meta et jeton
1. Sur <https://developers.facebook.com/apps>, crée une application de type
   **Entreprise**, puis ajoute le produit **Instagram** → *API avec connexion Instagram*.
2. Dans *Générer des jetons d'accès*, ajoute le compte @penserresonner
   (il faut l'ajouter comme testeur Instagram et accepter l'invitation dans
   l'app Instagram : Paramètres → Apps et sites web → Invitations de testeur).
3. Clique **Générer le jeton** et copie-le (il commence par `IGAA…`).
   C'est un jeton longue durée de 60 jours ; le workflow de renouvellement le
   prolonge automatiquement.

L'application peut rester en mode *Développement* : tu publies sur ton propre
compte, aucune validation de Meta n'est nécessaire.

### 3. Secrets GitHub
Dépôt → Settings → Secrets and variables → Actions → *New repository secret* :

- `IG_ACCESS_TOKEN` : le jeton Instagram.
- `GH_PAT` : un jeton GitHub *fine-grained*
  (<https://github.com/settings/personal-access-tokens/new>), limité à ce dépôt,
  permission **Secrets : Read and write**, durée maximale. Il sert uniquement
  au renouvellement automatique du jeton Instagram.

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
