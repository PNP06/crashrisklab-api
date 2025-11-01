# CrashRiskLab Frontend (GitHub Pages)

Page statique HTML/JS/CSS appelant l'API Render CrashRiskLab.

## Configuration

- Ouvrez `frontend/app.js` et remplacez :

```
const API_URL = "https://<TON_SERVICE_RENDER>.onrender.com";
```

par l'URL exacte de votre service Render (ex: `https://crashrisklab.onrender.com`).

## Publication via gh-pages

À la racine du repo, vous pouvez utiliser `gh-pages` :

```
npm install --save-dev gh-pages
npm run deploy
```

Le script `deploy` publie `frontend/` dans la branche `gh-pages`.

Sinon, publiez manuellement avec un worktree:

```
git worktree add -B gh-pages ../crashrisklab-gh-pages
robocopy frontend ..\crashrisklab-gh-pages /E
cd ..\crashrisklab-gh-pages
git add .
git commit -m "Publish frontend to GitHub Pages"
git push -u origin gh-pages
```

Activez ensuite GitHub Pages : Settings → Pages → Branch: `gh-pages` / root.

