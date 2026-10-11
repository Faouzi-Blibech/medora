import asyncio
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import errors
from app.config import check_secrets, get_settings
from app.db import engine
from app.iot import publisher
from app.routers import access, ai, alerts, appointments, auth, devices, doses, exams, handover, health_events, healthwatch, integrations, patients, prescriptions, staff, users
from app.ws import relay
from app.ws import router as ws_router
from app.ws.hub import hub



@asynccontextmanager
async def lifespan(_: FastAPI):
    check_secrets(get_settings())
    hub.loop = asyncio.get_running_loop()
    client = relay.start()
    publisher.use(client)  # publish on the client that connected at startup
    yield
    client.loop_stop()
    client.disconnect()


app = FastAPI(title="Ward API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().web_origin.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
errors.install(app)
app.include_router(auth.router)
app.include_router(access.router)
app.include_router(patients.router)
app.include_router(alerts.router)
app.include_router(prescriptions.router)
app.include_router(devices.router)
app.include_router(doses.router)
app.include_router(staff.router)
app.include_router(users.router)
app.include_router(appointments.router)
app.include_router(integrations.router)
app.include_router(ai.router)
app.include_router(exams.router)
app.include_router(handover.router)
app.include_router(health_events.router)
app.include_router(healthwatch.router)
app.include_router(ws_router.router)


def _db_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _mqtt_ok() -> bool:
    s = get_settings()
    try:
        with socket.create_connection((s.mqtt_host, s.mqtt_port), timeout=1):
            return True
    except OSError:
        return False


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "db": _db_ok(), "mqtt": _mqtt_ok()}
