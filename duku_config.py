import json
import os
from pathlib import Path


def get_config_dir():
    override = os.environ.get("DUKU_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".duku"


def get_config_path():
    return get_config_dir() / "config.json"


def normalize_satoken(value):
    if value is None:
        return None

    token = value.strip()
    if not token:
        return None
    if token.startswith("satoken="):
        token = token.split("satoken=", 1)[1]
    if ";" in token:
        token = token.split(";", 1)[0]
    token = token.strip()
    return token or None


def load_config():
    config_path = get_config_path()
    if not config_path.exists():
        return {}

    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config):
    config_dir = get_config_dir()
    config_path = get_config_path()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def save_satoken(satoken):
    token = normalize_satoken(satoken)
    if not token:
        raise ValueError("satoken 不能为空")

    config = load_config()
    config["satoken"] = token
    return save_config(config)


def resolve_satoken(explicit=None):
    candidates = [
        explicit,
        os.environ.get("DUKU_SATOKEN"),
        load_config().get("satoken"),
    ]
    for candidate in candidates:
        token = normalize_satoken(candidate)
        if token:
            return token
    return None


def require_satoken(explicit=None):
    token = resolve_satoken(explicit)
    if token:
        return token

    config_path = get_config_path()
    raise RuntimeError(
        "未找到 satoken。请先运行 `duku login --satoken <你的 token>`，"
        "或设置环境变量 `DUKU_SATOKEN`。"
        f" 配置文件位置：{config_path}"
    )
