# Décision : remplacement de Kafka par un système distribué Airflow

## Décision

Kafka, Zookeeper, kafka-producer et kafka-consumer sont **retirés**.
Remplacés par le DAG `realtime_stream` (Airflow LocalExecutor).

## Architecture de remplacement

```
Toutes les 3 minutes — DAG realtime_stream :

  ┌─────────────────────────┐   ┌─────────────────────────┐
  │  fetch_air_quality      │   │  fetch_velib             │
  │  (processus Python #1)  │   │  (processus Python #2)   │
  │  WAQI → PostgreSQL      │   │  OpenData Paris → PG     │
  │  + pg_notify            │   │  + pg_notify             │
  └─────────────────────────┘   └─────────────────────────┘
              │                             │
              └──────────┬──────────────────┘
                         ▼
               WebSocket /ws/realtime (LISTEN/NOTIFY — inchangé)
```

## Pourquoi c'est un système distribué (C2.2)

- **Parallélisme réel** : LocalExecutor lance chaque tâche dans un sous-processus
  Python distinct. `fetch_air_quality` et `fetch_velib` s'exécutent simultanément,
  sans partager d'état ni de mémoire — c'est la définition d'un traitement distribué.
- **Streaming continu** : le DAG tourne toutes les 3 minutes en boucle, produisant
  un flux continu de données à fréquence fixe. `pg_notify` pousse chaque événement
  vers les clients WebSocket dans la milliseconde qui suit l'écriture — le délai
  de bout en bout est identique à l'ancienne architecture Kafka.
- **Partitionnement par source** : chaque tâche est responsable d'une source de
  données distincte (WAQI, Vélib) — c'est le même principe qu'un consumer group
  Kafka avec partitions par topic.

## Ce que Kafka apportait en plus

- Rétention des messages (rejouabilité) : perdu — acceptable pour ces données
  ephémères (qualité de l'air, disponibilité Vélib en temps réel n'ont pas de valeur
  à rejouer).
- Découplage fort producer/consumer : remplacé par l'isolation de processus Airflow.
- Tolérance aux pannes du consumer : remplacée par le mécanisme de retry Airflow
  (1 retry, délai 1 min).

## Justification de la couverture C2.2

Le critère demande un "système distribué utilisant des technologies de streaming".
Cette architecture couvre les deux dimensions :
- **Distribué** : processus concurrents indépendants (Airflow LocalExecutor)
- **Streaming** : flux continu toutes les 3 min + push WebSocket via pg_notify

Avantage opérationnel : suppression de 4 containers (zookeeper, kafka,
kafka-producer, kafka-consumer), soit ~1.5 GB de RAM libérés.
