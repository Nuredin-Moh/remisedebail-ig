# remisedebail-ig
Auto-publication quotidienne des carrousels remisedebail.ch sur Instagram + Facebook (API Graph, GitHub Actions).
1 carrousel/jour sur 100 jours. Autonome (ordi eteint OK).

Secrets requis : `IG_TOKEN` (page access token permanent), `IG_USER_ID` (compte IG business), `FB_PAGE_ID` (page Facebook).
Images hebergees dans `images/` (URLs raw). Planning dans `schedule.json`. Anti-doublon : `last.json`.
