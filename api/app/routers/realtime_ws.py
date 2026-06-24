"""
api/app/routers/realtime_ws.py
---------------------------------
Endpoint WebSocket /ws/realtime : relaie en temps réel les événements publiés
par le consumer Kafka (disponibilité Vélib + mesures de qualité de
l'air), SANS scrutation périodique (polling) de la base.

Mécanisme : le consumer (streaming/consumer_to_gold.py) appelle `pg_notify()`
juste après chaque insertion. Ici, on ouvre une connexion asyncpg dédiée par
client WebSocket et on s'abonne (`LISTEN`) au même canal PostgreSQL. Dès
qu'une notification arrive, elle est immédiatement relayée au client — c'est
un vrai push, le délai entre l'événement Kafka et son affichage côté
navigateur est de l'ordre de la milliseconde (latence réseau + DB), pas d'un
intervalle de scrutation fixe.

Limite : une connexion PostgreSQL dédiée par client WebSocket. À fort trafic,
un fan-out interne serait préférable — acceptable pour l'échelle de ce projet.
"""
import asyncio
import os

import asyncpg
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

NOTIFY_CHANNEL = "realtime_channel"


def _build_dsn() -> str:
    host = os.environ.get("POSTGRES_GOLD_HOST", "postgres-gold")
    db = os.environ.get("POSTGRES_GOLD_DB", "gold")
    user = os.environ.get("POSTGRES_GOLD_USER", "gold_user")
    pwd = os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass")
    return f"postgresql://{user}:{pwd}@{host}:5432/{db}"


@router.websocket("/ws/realtime")
async def realtime_feed(websocket: WebSocket):
    await websocket.accept()

    queue: asyncio.Queue[str] = asyncio.Queue()

    def on_notify(connection, pid, channel, payload):
        queue.put_nowait(payload)

    conn = None
    try:
        conn = await asyncpg.connect(dsn=_build_dsn())
        await conn.add_listener(NOTIFY_CHANNEL, on_notify)

        while True:
            payload = await queue.get()
            await websocket.send_text(payload)

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_text(f'{{"error": "{exc}"}}')
        except Exception:
            pass
    finally:
        if conn is not None:
            try:
                await conn.remove_listener(NOTIFY_CHANNEL, on_notify)
            except Exception:
                pass
            await conn.close()
