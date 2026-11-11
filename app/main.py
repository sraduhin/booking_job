from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routers import bookings, events


def _maybe_attach_debugger() -> None:
    settings = get_settings()
    if not settings.debug:
        return

    import pydevd_pycharm

    pydevd_pycharm.settrace(
        settings.debug_host,
        port=settings.debug_port,
        stdoutToServer=True,
        stderrToServer=True,
        suspend=False,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _maybe_attach_debugger()
    yield


app = FastAPI(title="Booking API", version="0.1.0", lifespan=lifespan)
app.include_router(events.router)
app.include_router(bookings.router)
