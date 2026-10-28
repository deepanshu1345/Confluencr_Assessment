import os
from pathlib import Path


class Settings:
    PROJECT_NAME: str = "Transaction Ledger API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql://postgres@localhost:5432/app_db"

    def __init__(self):
        # Read .env file if it exists
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if hasattr(self, key):
                        if isinstance(getattr(self, key), bool):
                            setattr(self, key, val.lower() in ("true", "1", "yes"))
                        elif isinstance(getattr(self, key), int):
                            setattr(self, key, int(val))
                        else:
                            setattr(self, key, val)

        # Allow environment variables to override .env
        for key in list(self.__class__.__dict__.keys()):
            if not key.startswith("_") and key in os.environ:
                val = os.environ[key]
                attr = getattr(self, key)
                if isinstance(attr, bool):
                    setattr(self, key, val.lower() in ("true", "1", "yes"))
                elif isinstance(attr, int):
                    setattr(self, key, int(val))
                else:
                    setattr(self, key, val)


settings = Settings()
