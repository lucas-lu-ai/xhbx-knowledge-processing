"""ImageDescriber：用多模态大模型把课件配图转写为可入库的文字。

成本与健壮性是关键：
- 装饰图（logo/背景/分隔线）识别后丢弃，不落地、不污染知识库；
- 识别结果按图片 sha256 落盘缓存，重跑 / 跨节同图直接命中，避免重复计费；
- 单张图识别失败（网络抖动等）降级返回 None，不缓存、不中断整条流水线。
"""

from __future__ import annotations

import logging
from pathlib import Path

from agentscope.message import Base64Source, DataBlock, SystemMsg, TextBlock, UserMsg
from agentscope.model import OpenAIChatModel

from ..parsers.image_extract import SourceImage
from .factory import response_text
from .prompts import VISION_SYSTEM_PROMPT

_logger = logging.getLogger(__name__)

# 模型对装饰图的约定回复是「装饰图」三字；留少量余量容忍多余标点。
_DECORATIVE_MARK = "装饰图"
_DECORATIVE_MAX_LEN = 8
# 有效转写至少应有的字符数：过短（如标语口号、模型异常输出"三个字"）
# 没有知识价值，按无效处理，避免碎片污染知识库。
_MIN_USEFUL_LEN = 12

_USER_HINT = "请识别这张保险培训课件配图，并按系统要求输出。"


def _is_decorative(text: str) -> bool:
    """判断模型回复是否表示「这是装饰图」。"""
    stripped = text.strip()
    return _DECORATIVE_MARK in stripped and len(stripped) <= _DECORATIVE_MAX_LEN


def _is_useless(text: str) -> bool:
    """判断识别结果是否无入库价值（空 / 装饰图 / 过短碎片）。"""
    stripped = text.strip()
    return (
        not stripped
        or _is_decorative(stripped)
        or len(stripped) < _MIN_USEFUL_LEN
    )


def _atomic_write_text(path: Path, text: str) -> None:
    """原子写文本：先写临时文件再 rename，避免并发/中断产生半截缓存。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class ImageDescriber:
    """课件配图视觉识别器（带磁盘缓存）。"""

    def __init__(
        self, model: OpenAIChatModel, cache_dir: Path | None = None
    ) -> None:
        self._model = model
        self._cache_dir = cache_dir
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, sha256: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{sha256}.txt"

    async def describe(self, image: SourceImage) -> str | None:
        """识别单张图片。

        返回值：
        - 信息图 → 转写后的 Markdown 文本；
        - 装饰图 → None（已缓存，不再重复识别）；
        - 识别失败 → None（不缓存，下次可重试）。
        """
        cache_path = self._cache_path(image.sha256)
        if cache_path is not None and cache_path.exists():
            cached = cache_path.read_text(encoding="utf-8")
            return cached or None  # 空缓存代表装饰图

        messages = [
            SystemMsg(name="system", content=VISION_SYSTEM_PROMPT),
            UserMsg(
                name="user",
                content=[
                    TextBlock(type="text", text=_USER_HINT),
                    DataBlock(
                        type="data",
                        id=image.sha256,
                        source=Base64Source(
                            type="base64",
                            media_type=image.media_type,
                            data=image.base64_data,
                        ),
                        name=f"{image.sha256[:12]}.{image.media_type.split('/')[-1]}",
                    ),
                ],
            ),
        ]
        try:
            response = await self._model(messages)
        except Exception as exc:  # noqa: BLE001 - 单图失败降级，不中断流水线
            # 记录可见告警：若所选模型不支持视觉（如把 qwen 误配为视觉模型），
            # 会在此处持续报错，避免被静默吞掉、误以为全是装饰图。
            _logger.warning(
                "配图识别失败（sha=%s）：%r", image.sha256[:12], exc
            )
            return None

        text = response_text(response)
        if _is_useless(text):
            if cache_path is not None:
                _atomic_write_text(cache_path, "")  # 缓存为装饰图/无价值
            return None

        if cache_path is not None:
            _atomic_write_text(cache_path, text)
        return text
