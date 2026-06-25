"""全局配置：路径、文件类型映射、模型环境设置。

路径常量与文件类型映射在 M1（解析层）即被使用；``ModelSettings`` 供 M2 起
构造模型时读取 ``.env`` 中的第三方平台凭证。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .models import FileType

# ---- 路径 ----
# config.py 位于 src/insurance_coach_agents/，向上三级到项目根。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "数据"
CASES_DIR = DATA_DIR / "绩优案例"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ---- 文件类型映射 ----
# 扩展名（小写，含点）→ FileType。仅这些类型进入解析层。
EXTENSION_TO_TYPE: dict[str, FileType] = {
    ".docx": FileType.DOCX,
    ".pptx": FileType.PPTX,
    ".pdf": FileType.PDF,
    ".txt": FileType.TXT,
}

# 音视频等媒体扩展名：本期跳过（已有 txt 转写，不做 ASR）。
MEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".mp4", ".mov", ".m4a", ".ts", ".wav", ".avi"}
)


@dataclass(frozen=True)
class ModelSettings:
    """第三方 OpenAI 兼容平台的模型设置（来自环境变量）。"""

    api_key: str
    base_url: str
    model_name: str

    def __repr__(self) -> str:  # 避免在日志/异常中泄露密钥
        return (
            f"ModelSettings(base_url={self.base_url!r}, "
            f"model_name={self.model_name!r}, api_key=***)"
        )


def load_model_settings(dotenv_path: Path | None = None) -> ModelSettings:
    """从 ``.env`` / 环境变量加载模型设置。

    缺少必需变量时快速失败并给出清晰提示（遵循"系统边界验证"原则）。
    """
    load_dotenv(dotenv_path or (PROJECT_ROOT / ".env"))

    api_key = os.environ.get("QWEN_API_KEY", "").strip()
    base_url = os.environ.get("QWEN_BASE_URL", "").strip()
    model_name = os.environ.get("QWEN_MODEL_NAME", "").strip()

    missing = [
        name
        for name, value in (
            ("QWEN_API_KEY", api_key),
            ("QWEN_BASE_URL", base_url),
            ("QWEN_MODEL_NAME", model_name),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"缺少必需的环境变量：{', '.join(missing)}。"
            f"请参考 .env.example 在项目根创建 .env 文件。"
        )

    return ModelSettings(api_key=api_key, base_url=base_url, model_name=model_name)
