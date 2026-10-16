from typing import Literal

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class ConfigModel(BaseModel):
    proxy: str | None = Field(default=None, repr=False)
    akinator_proxy: str | None = Field(default=None, repr=False)
    akinator_child_mode: bool = True
    akinator_language: str = "cn"
    akinator_text_mode: bool = False
    akinator_operation_timeout: int = Field(default=120, ge=5, le=600)
    akinator_request_timeout: float = Field(default=20, ge=1, le=120)
    akinator_start_timeout: float = Field(default=60, ge=5, le=180)
    akinator_client_type: Literal["auto", "httpx", "playwright"] = "auto"
    akinator_base_url_template: str = "https://{}.akinator.com"
    akinator_browser_headless: bool = True
    akinator_virtual_display: bool = False
    akinator_browser_executable: str | None = None
    akinator_max_sessions: int = Field(default=4, ge=1, le=30)
    akinator_request_concurrency: int = Field(default=2, ge=1, le=10)
    akinator_admission_timeout: float = Field(default=3, ge=0.1, le=30)
    akinator_session_lifetime: int = Field(default=1200, ge=60, le=3600)
    akinator_host_integration: bool = True
    akinator_recall_previous: bool = False


config = get_plugin_config(ConfigModel)
