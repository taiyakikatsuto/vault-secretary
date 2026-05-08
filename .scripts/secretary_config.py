"""vault-secretary の設定読み込みユーティリティ

ルート直下の `secretary.config.yml` から個人化設定を読み込む。
ファイルが無い場合・キーが欠けている場合はデフォルト値を返す。
"""

from pathlib import Path

VAULT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = VAULT_ROOT / "secretary.config.yml"

DEFAULTS = {
    "user_name": "ユーザー",
}


def _load_yaml(text):
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        # PyYAML が無くても動くように、最小限の `key: value` 1行パーサーで代替
        result = {}
        for line in text.splitlines():
            line = line.split("#", 1)[0].rstrip()
            if not line or line.startswith(" ") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
        return result


def load_config():
    config = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        data = _load_yaml(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                if v is not None:
                    config[k] = v
    return config


def user_name():
    return load_config().get("user_name", DEFAULTS["user_name"])
