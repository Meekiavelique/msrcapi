from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    debug: bool = False

    database_path: Path = Path("./data/minecraft_api.sqlite3")

    data_dir: Path = Path("./data/minecraft")
    decompiler_jar: Path = Path("./MinecraftDecompiler.jar")

    cache_ttl: int = 3600  # 1 hour
    file_cache_size: int = 1000
    enable_compression: bool = True

    min_version: str = "1.13"
    max_version: str = "1.21"

    decompiler_type: str = "fernflower"
    regenerate_variables: bool = True
    threads: int = 8

    @property
    def minecraft_manifest_url(self) -> str:
        return "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


settings = Settings()
