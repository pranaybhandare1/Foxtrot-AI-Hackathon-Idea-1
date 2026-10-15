"""Ontology Manager: JSON API under /api and the built web app (web/dist) at /.

Run:  make om      -> http://127.0.0.1:8770   (binds to localhost only: this is health data)
Docs: http://127.0.0.1:8770/api/docs
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from om_api import actions, agent, management, objects, ontology_routes, sql, workflows

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="Ontology Manager API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(GZipMiddleware, minimum_size=2048)

    @app.middleware("http")
    async def local_writes(request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and urlsplit(origin).netloc != request.url.netloc:
            return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
        return await call_next(request)

    # profile must be registered before /objects/{type}/{pk} so "profile" isn't read as a primary key
    for module in (ontology_routes, objects, sql, actions, agent, workflows, management):
        app.include_router(module.router, prefix="/api")

    if WEB_DIST.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = WEB_DIST / path
            if path and candidate.is_file() and WEB_DIST in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(WEB_DIST / "index.html")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("om_api.main:app", host="127.0.0.1", port=int(os.environ.get("OM_PORT", "8770")),
                reload=bool(os.environ.get("OM_RELOAD")))  # fmt: skip
