from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Request
from pydantic import BaseModel

from tortoise import Tortoise, connections, fields
from tortoise.models import Model

from trainz_dl.config import settings


class Asset(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=255, null=False)
    kuid = fields.CharField(max_length=255, null=False)
    sha1 = fields.CharField(max_length=40, null=False)
    file_id = fields.CharField(max_length=32, null=False)
    revision = fields.IntField(null=False)
    last_update = fields.DatetimeField(null=False, auto_now=True)

    def __str__(self):
        return f"{self.username} <{self.kuid}>"

    class Meta:
        table = "assets"


class AssetSchema(BaseModel):
    username: str
    kuid: str
    sha1: str
    file_id: str
    revision: int

    class Config:
        from_attributes = True


def get_application() -> FastAPI:
    app = FastAPI(
        debug=settings.debug,
        title="Trainz-DL",
        description="A simple API to download updates for Trainz assets from SVN repositories",
        version="1.0",
        license_info={
            "name": "GPLv3 License",
            "url": "https://github.com/divadsn/trainz-dl/blob/master/LICENSE",
        },
        docs_url="/docs/",
        redoc_url="/redoc/",
        openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def add_cache_control_header(request: Request, call_next):
        response = await call_next(request)

        if request.url.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"

        return response

    @app.on_event("startup")
    async def startup_event():
        await Tortoise.init(db_url=settings.db_url, modules={"models": ["trainz_dl"]})

    @app.on_event("shutdown")
    async def shutdown_event():
        await connections.close_all()

    router = APIRouter(prefix="/api", tags=["assets"])

    @router.get("/assets.json")
    async def get_assets(revision: Optional[int] = None, last_update: Optional[datetime] = None) -> List[AssetSchema]:
        assets = Asset.all()

        if revision is not None:
            assets = Asset.filter(revision__gte=revision)

        if last_update is not None:
            assets = Asset.filter(last_update__gte=last_update)

        assets = await assets.order_by("username")
        return [AssetSchema.model_validate(asset) for asset in assets]

    @router.get("/assets/by-kuid/{kuid}")
    async def get_asset_by_kuid(kuid: str) -> AssetSchema:
        asset = await Asset.get_or_none(kuid=kuid)

        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")

        return AssetSchema.model_validate(asset)

    @router.get("/assets/by-file/{file_id}")
    async def get_asset_by_file(file_id: str) -> AssetSchema:
        asset = await Asset.get_or_none(file_id=file_id)

        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")

        return AssetSchema.model_validate(asset)

    app.include_router(router)
    return app


# Create the FastAPI application
app = get_application()
