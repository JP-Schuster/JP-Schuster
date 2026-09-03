# Deploy no Vercel

1. Abra: https://vercel.com/new/clone?repository-url=https://github.com/JP-Schuster/github-tier&env=GITHUB_TOKEN&envDescription=GitHub%20PAT%20com%20read%3Auser&project-name=jp-schuster-github-tier
2. Cole um **GitHub PAT** com scope `read:user` no campo `GITHUB_TOKEN`
3. Clique **Deploy**
4. Copie a URL gerada (ex.: `https://jp-schuster-github-tier.vercel.app`)
5. No README do profile, troque o tier SVG local pela URL:

```md
<img src="https://SUA-URL.vercel.app/api/tier?user=JP-Schuster&theme=tokyonight" height="195" />
```

Este fork inclui commits e PRs de repos privados de organizations.
