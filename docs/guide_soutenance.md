# Guide de soutenance — Urban Immo
### Comment présenter le projet et justifier les choix d'architecture

---

## Comment aborder la présentation

La soutenance n'est pas une démonstration technique ligne à ligne. C'est une histoire : **un problème métier → des contraintes réelles → des choix justifiés → des preuves que ça marche**.

Le jury cherche à vérifier que vous comprenez *pourquoi* vous avez fait ce que vous avez fait — pas seulement que vous avez su le coder.

---

## Déroulé recommandé (20-25 min)

### Phase 1 — Le contexte (2 min)

> "Urban Immo est une agence immobilière parisienne fictive. Le problème qu'on s'est posé : comment piloter une agence avec de la donnée publique réelle ? Prix au m² par arrondissement, qualité de l'air, accès aux transports, criminalité — toutes ces données existent en open data mais sont dispersées sur des dizaines de sources différentes, dans des formats différents, avec des mises à jour asynchrones."

**Pourquoi commencer comme ça ?**
Parce que ça pose le "pourquoi" avant le "comment". Si vous commencez par "on a fait un pipeline Bronze/Silver/Gold avec Airflow", le jury ne sait pas encore pourquoi.

---

### Phase 2 — L'architecture en une phrase (1 min)

> "Notre réponse, c'est une architecture médaillon : on collecte les données brutes, on les nettoie, on les agrège, et on les expose via une API sécurisée à un frontend React. Tout est orchestré par Airflow et tourne dans Docker."


Montrez le schéma ASCII du README. Pas besoin d'expliquer chaque bloc — juste le flux global. Vous reviendrez sur les détails après.

---

### Phase 3 — La démonstration live (5-7 min)

C'est le moment le plus impactant. Faites-le dans cet ordre :

1. **Ouvrez le site** (http://localhost:8501)
   - Montrez la vitrine publique : "Ça c'est ce qu'un client voit."
   - Connectez-vous en tant qu'employé.
   - Créez un bien avec des caractéristiques variables (ex. `{"etage": 3, "ascenseur": true}`).
   - "Ce bien est écrit dans PostgreSQL pour les données structurées, et dans MongoDB pour les caractéristiques variables — on y reviendra."

2. **Ouvrez l'explorateur de données**
   - Changez d'indicateur : prix/m², qualité de l'air, criminalité.
   - "Chaque couleur est une interpolation sur les données réelles — pas des données inventées."
   - Sur la qualité de l'air : "9 arrondissements ont une vraie station WAQI. Les 11 autres ? On fait une interpolation spatiale IDW depuis les stations connues."

3. **Ouvrez le Swagger** (http://localhost:8000/docs)
   - Montrez un `GET /geo/arrondissements` en direct.
   - "L'API retourne le GeoJSON enrichi — géométries officielles + tous les indicateurs — en moins de 50ms depuis MinIO."

4. **Ouvrez Airflow** (http://localhost:8080)
   - Montrez les 4 DAGs, leur état, un run récent.
   - "Le DAG realtime_stream tourne toutes les 3 minutes — en ce moment il collecte Vélib et qualité de l'air."

5. **Montrez le WebSocket en live** (si possible)
   - Dans le frontend, montrez le widget temps réel qui se met à jour.
   - "Aucun polling côté client — c'est un push via PostgreSQL NOTIFY."

---

### Phase 4 — Les choix d'architecture justifiés (8-10 min)

C'est la partie la plus importante pour le jury. Voici comment cadrer chaque choix.

---

#### Pourquoi MinIO plutôt qu'un filesystem local ?

> "On aurait pu stocker les fichiers en local. Mais ça pose deux problèmes : pas de versioning horodaté, et le code est couplé à un chemin filesystem. MinIO expose une API S3 standard — boto3 est le même client qu'on utiliserait pour AWS S3. Si on déploie en prod, on change une variable d'environnement, pas une ligne de code. Et l'isolation par buckets Bronze / Silver / Gold matérialise physiquement les zones de maturité de la donnée."

---

#### Pourquoi PostgreSQL ET MongoDB ?

C'est probablement la question que le jury posera en premier.

> "On a deux types de données structurellement différents. Les données Gold — prix, population, indicateurs — ont un schéma fixe et connu : c'est exactement le cas d'usage d'une base relationnelle avec des contraintes, des index, des jointures. PostgreSQL est la bonne réponse là-dessus."

> "Mais les biens immobiliers ont des attributs qui varient selon leur type. Un studio, c'est étage + ascenseur. Une maison, c'est jardin_m2 + garage + nb_niveaux. Une liste de 30 colonnes nullable en SQL, c'est une erreur de modélisation — chaque INSERT aurait 25 colonnes à NULL. MongoDB permet un document par bien avec uniquement les clés pertinentes. C'est pour ça qu'on a les deux : PostgreSQL pour ce qui est structuré et prévisible, MongoDB pour ce qui est variable."

Si le jury demande "pourquoi pas JSONB PostgreSQL pour tout ?" :

> "JSONB aurait fonctionné techniquement. On l'utilise d'ailleurs pour les rapports pipeline. Mais MongoDB est une vraie base non-relationnelle dédiée aux documents — c'est le choix qui démontre la compétence C1.2. Et dans un vrai projet avec des milliers de biens aux schémas très différents, un document store est plus adapté qu'une colonne JSONB dans une table relationnelle."

---

#### Pourquoi Airflow plutôt qu'un simple cron ?

> "Un cron shell peut déclencher un script. Mais il ne gère pas les dépendances entre étapes — si Silver échoue, Gold ne doit pas tourner. Il ne fait pas les retries automatiques. Il n'a pas d'interface de supervision. Et surtout, il ne s'intègre pas avec OpenLineage pour la traçabilité. Airflow gère tout ça nativement. Les TriggerDagRunOperator enchaînent Bronze → Silver → Gold automatiquement."

---

#### Pourquoi avoir supprimé Kafka ?

C'est une question piège si vous ne préparez pas la réponse.

> "On avait initialement prévu Kafka. On l'a remplacé pour une raison simple : Kafka est pertinent quand on a des centaines de producteurs/consommateurs et des millions d'événements par seconde. Là on a deux sources — WAQI et Vélib — qui produisent quelques dizaines de lignes toutes les 3 minutes. Kafka aurait été du surdimensionnement pur. À la place, on a deux tâches Airflow parallèles — des sous-processus Python distincts via LocalExecutor. C'est distribué au sens réel du terme : deux processus indépendants, pas d'état partagé, exécution concurrente. Et le streaming, c'est pg_notify → WebSocket — le délai bout-en-bout est le même qu'avec Kafka."

---

#### Pourquoi FastAPI plutôt que Flask ou Django ?

> "Flask aurait fonctionné mais il faut tout câbler manuellement : validation, serialisation, documentation. Django REST Framework est bien mais surdimensionné — on n'utilise pas l'ORM Django, les templates, ni l'admin Django. FastAPI génère la documentation OpenAPI automatiquement depuis les types Python, valide les requêtes avec Pydantic, et gère le WebSocket async nativement. C'est le bon outil pour une API pure sans le poids d'un framework full-stack."

---

#### Pourquoi le schéma en étoile + data marts ?

> "Les tables plates suffiraient pour des requêtes simples. Le schéma en étoile est là pour modéliser explicitement les dimensions analytiques : on peut requêter par arrondissement, par année, par segment de marché — en joignant les dimensions. Les data marts vont plus loin : ce sont des vues matérialisées pré-agrégées. L'API ne recalcule rien au moment de la requête — elle lit des données déjà calculées à la fin du pipeline. C'est la différence entre un datawarehouse et une base opérationnelle."

---

#### Pourquoi Marquez / OpenLineage ?

> "Sans traçabilité, si un indicateur est faux en Gold, on ne sait pas quel fichier Bronze est responsable. Marquez enregistre automatiquement — via le provider Airflow — quels datasets ont été consommés et produits par chaque tâche, à quelle heure, avec quel statut. L'interface graphique montre le graphe Bronze → Silver → Gold. C'est de la gouvernance de données — essentiel en entreprise pour l'auditabilité."

---

#### Pourquoi l'IDW pour la qualité de l'air ?

> "WAQI a 9 stations dans Paris. Si on ne met des données qu'à ces 9 arrondissements, 11 arrondissements ont NULL dans l'explorateur — c'est une mauvaise expérience et une donnée incomplète. L'IDW — Inverse Distance Weighting — est une technique d'interpolation spatiale standard : chaque arrondissement sans station reçoit une valeur pondérée par l'inverse du carré de la distance aux stations connues. Ce n'est pas une valeur exacte, mais c'est une estimation cohérente, et c'est clairement documenté."

---

### Phase 5 — Les bugs réels (2 min)

Ne les cachez pas — montrez-les comme preuve de déploiement réel.

> "Trois bugs ont été détectés et résolus en conditions réelles, pas en sandbox :"

1. **Conflit SQLAlchemy dans Airflow** — "On épinglait une version dans les requirements Airflow, mais Airflow 2.9.3 embarque la sienne et refuse qu'on la remplace. Solution : retirer la contrainte de version."

2. **`pandas.to_sql()` qui ne reconnaît pas l'Engine Airflow** — "Le conteneur Airflow a une configuration Python particulière où pandas ne détecte pas correctement le dialecte PostgreSQL et essaie de faire du SQLite. On a réécrit l'INSERT en psycopg2 brut, ce qui contourne complètement le problème."

3. **DAGs en pause par défaut** — "Airflow met tous les nouveaux DAGs en pause. Un DAG en pause accepte un déclenchement manuel mais le run reste bloqué en `queued` pour toujours. Une variable d'environnement suffit à corriger ça."

> "Ces bugs sont documentés dans le README parce qu'ils montrent que le projet a vraiment tourné — pas juste été codé."

---

### Phase 6 — La correspondance RNCP (2 min)

Allez directement au tableau dans `soutenance.md`. Pour chaque compétence, une phrase suffit — le jury a le document.

L'essentiel à souligner oralement :

- **C1.1** : "PostgreSQL avec contraintes, index, rôle lecture seule et schéma en étoile complet."
- **C1.2** : "MongoDB pour les caractéristiques variables des biens — pas du JSONB à la place."
- **C2.2** : "Deux processus Airflow parallèles + pg_notify + WebSocket. Pas de polling."
- **C3.2** : "La carte est en GeoJSON officiel, les données sont réelles — pas générées."

---

## Questions probables du jury et comment y répondre

**"Vous avez combien de données réelles ?"**
> "DVF Paris : ~50 000 transactions par an sur 5 ans. INSEE, RPLS, SSMSI : des milliers de lignes par commune. WAQI : une mesure toutes les 3 minutes, Vélib : ~1 400 stations mises à jour à la minute. Tout est réel — aucune donnée générée aléatoirement dans la chaîne de production."

**"Qu'est-ce qui se passe si MinIO tombe ?"**
> "L'endpoint `/geo/arrondissements` a un fallback : il sert un GeoJSON de référence local embarqué dans l'image. La carte s'affiche quand même, sans les indicateurs enrichis. C'est documenté et testé dans `tests/test_resilience.sh`."

**"Et si MongoDB tombe ?"**
> "L'upsert MongoDB dans `biens.py` est dans un try/except. Si ça échoue, un warning est loggé mais l'API répond 201 normalement. PostgreSQL a les données structurées — MongoDB n'est que l'enrichissement."

**"Votre système distribué, c'est vraiment distribué ?"**
> "LocalExecutor lance chaque tâche dans un sous-processus Python distinct avec son propre espace mémoire. Les deux tâches — WAQI et Vélib — s'exécutent en parallèle, sans état partagé, sur des sources différentes. C'est la définition d'un système distribué : plusieurs processus indépendants qui collaborent."

**"Pourquoi JWT et pas OAuth ?"**
> "OAuth est pertinent quand on délègue l'authentification à un tiers — Google, GitHub. Là on gère nos propres comptes avec trois rôles métier précis. JWT stateless est la bonne réponse : pas de session serveur, compatible multi-instances, et on peut désactiver un compte immédiatement côté base sans attendre l'expiration du token."

**"Qu'est-ce que vous changeriez si c'était en production ?"**
> "Plusieurs choses : rotation des tokens JWT avec refresh tokens, Redis pour le rate limiting multi-instances, un vrai listener WebSocket interne avec fan-out plutôt qu'une connexion PostgreSQL par client, et probablement S3 réel à la place de MinIO. Mais tout ça est documenté comme limite assumée dans le README — ce sont des choix de dimensionnement, pas des erreurs d'architecture."

---

## Conseils pratiques pour le jour J

- **Ayez tout qui tourne AVANT d'entrer** — vérifiez `docker compose ps` avant la soutenance
- **Déclenchez le pipeline la veille** pour que les données Gold soient peuplées
- **Préparez un onglet par service** : site, Swagger, Airflow, MinIO, Marquez
- **Ne lisez pas les slides** — le document `soutenance.md` est votre filet de sécurité, pas votre script
- **Quand vous ne savez pas**, dites "c'est une limite qu'on a identifiée" ou "c'est un choix de dimensionnement pour ce projet" — c'est toujours mieux que d'inventer
- **Le jury apprécie qu'on explique les bugs** — ça prouve que le projet a vraiment tourné

---

*Ce guide accompagne `docs/soutenance.md` qui contient le détail technique complet.*
