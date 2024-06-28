import os

from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, APIRouter, Path, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from tortoise import Tortoise, connections, fields
from tortoise.models import Model

from trainz_dl.config import settings


class Asset(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=255, null=False)
    kuid = fields.CharField(max_length=255, index=True, unique=True, null=False)
    sha1 = fields.CharField(max_length=40, null=False)
    file_id = fields.CharField(max_length=32, index=True, unique=True, null=False)
    revision = fields.IntField(null=False)
    last_update = fields.DatetimeField(null=False, auto_now_add=True)

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
        alias_generator = to_camel
        populate_by_name = True


class AssetsResponseSchema(BaseModel):
    assets: List[AssetSchema]
    last_revision: int

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class AssetDetailsSchema(BaseModel):
    current_revision: int
    full_bytes: int
    full_human: str
    low_bytes: int
    low_human: str

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def get_size(start_path: str = '.') -> int:
    total_size = 0
    for root_path, dirs, files in os.walk(start_path):
        for f in files:
            file_path = os.path.join(root_path, f)

            # skip if it is symbolic link
            if not os.path.islink(file_path):
                total_size += os.path.getsize(file_path)

    return total_size


def readable_size(size: int) -> str:
    units = ('KB', 'MB', 'GB', 'TB')
    size_list = [f'{int(size):,} B'] + [f'{int(size) / 1024 ** (i + 1):,.1f} {u}' for i, u in enumerate(units)]
    return [size for size in size_list if not size.startswith('0.')][-1]


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_cache_control_header(request: Request, call_next):
        response = await call_next(request)

        if request.url.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"

        return response

    @app.on_event("startup")
    async def startup_event():
        FastAPICache.init(InMemoryBackend())
        await Tortoise.init(db_url=settings.db_url, modules={"models": ["trainz_dl"]})

    @app.on_event("shutdown")
    async def shutdown_event():
        await connections.close_all()

    router = APIRouter(prefix="/api", tags=["assets"])

    @router.get("/assets.json")
    @cache(namespace="assets", expire=5*60)
    async def get_assets(revision: Optional[int] = None, last_update: Optional[datetime] = None) -> AssetsResponseSchema:
        assets = Asset.all()

        if revision is not None:
            assets = Asset.filter(revision__gt=revision)

        if last_update is not None:
            assets = Asset.filter(last_update__gt=last_update)

        assets = await assets.order_by("username")

        if not assets:
            raise HTTPException(status_code=404, detail="No assets found")

        return AssetsResponseSchema(
            assets=[AssetSchema.model_validate(asset, from_attributes=True) for asset in assets],
            last_revision=max(assets, key=lambda h: h.revision).revision,
        )

    @router.get("/assets/by-kuid/{kuid}")
    async def get_asset_by_kuid(kuid: str = Path(regex=r"^(?:kuid:-?\d+:\d+|kuid2:-?\d+:\d+:\d+)$")) -> AssetSchema:
        asset = await Asset.get_or_none(kuid=kuid)

        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")

        return AssetSchema.model_validate(asset, from_attributes=True)

    @router.get("/assets/by-file/{file_id}")
    async def get_asset_by_file(file_id: str = Path(min_length=32, max_length=32)) -> AssetSchema:
        asset = await Asset.get_or_none(file_id=file_id)

        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")

        return AssetSchema.model_validate(asset, from_attributes=True)

    @router.get("/assets/details")
    @cache(namespace="assets-details", expire=5*60)
    async def get_assets_details() -> AssetDetailsSchema:
        latest_asset = await Asset.all().order_by("-revision").first()

        # Calculate the size of the assets folder
        full_bytes = get_size("/var/www/html/assets/full")
        low_bytes = get_size("/var/www/html/assets/low")

        return AssetDetailsSchema(
            current_revision=latest_asset.revision,
            full_bytes=full_bytes,
            full_human=readable_size(full_bytes),
            low_bytes=low_bytes,
            low_human=readable_size(low_bytes),
        )

    app.include_router(router)
    return app


# Create the FastAPI application
app = get_application()
