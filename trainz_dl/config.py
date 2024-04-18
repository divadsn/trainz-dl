from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    debug: bool = False
    db_url: str = "sqlite:///db.sqlite3"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
