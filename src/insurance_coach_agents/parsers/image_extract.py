"""从 pptx 课件抽取内嵌图片，供视觉识别（VLM）转写。

课件里的图标、流程图、产品对比表、话术截图等往往承载文字之外的关键信息，
需要交给多模态模型转写。本模块只负责「取图 + 预过滤」，不做任何模型调用：

- 按幻灯片顺序遍历图片（含 group 内嵌套图片）；
- 用 sha256 去重，避免同一张图（如每页页脚 logo）被反复识别；
- 用像素尺寸预过滤掉过小的装饰元素（分隔线、小图标），先省一道模型成本；
- 只保留多模态模型可识别的常见位图格式，矢量图 / 异常格式跳过。
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

# 过小的图（最长边 < 该阈值像素）通常是分隔线、项目符号、小图标等装饰元素，
# 识别价值低且浪费 token，直接预过滤。
DEFAULT_MIN_SIDE_PX = 128

# 多模态模型可识别的常见位图格式。矢量图（wmf/emf）与异常格式不传给模型。
_SUPPORTED_MEDIA_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
# 个别课件里 jpg 的 content_type 写成 image/jpg，归一到标准 image/jpeg。
_MEDIA_TYPE_ALIASES = {"image/jpg": "image/jpeg"}


@dataclass(frozen=True)
class PptxImage:
    """pptx 中的一张内嵌图片（已去重、已通过尺寸预过滤）。"""

    slide_index: int  # 1-based，对应解析文本里的「第 N 页」
    media_type: str  # 归一后的 MIME 类型，如 image/png
    blob: bytes
    width: int  # 像素；0 表示尺寸未知
    height: int
    sha256: str

    @property
    def max_side(self) -> int:
        """最长边像素；尺寸未知时为 0。"""
        return max(self.width, self.height)

    @property
    def base64_data(self) -> str:
        """base64 编码的图片数据，供构造多模态消息块。"""
        return base64.b64encode(self.blob).decode("ascii")


def _iter_picture_shapes(shapes):
    """按顺序产出所有图片形状，递归展开 group。"""
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_picture_shapes(shape.shapes)
        elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            yield shape


def _image_size(image) -> tuple[int, int]:
    """读取图片像素尺寸；python-pptx 取不到时返回 (0, 0)。"""
    try:
        width, height = image.size
        return int(width), int(height)
    except Exception:  # noqa: BLE001 - 矢量图/异常格式拿不到尺寸，按未知处理
        return 0, 0


def extract_pptx_images(
    path: Path, min_side_px: int = DEFAULT_MIN_SIDE_PX
) -> tuple[PptxImage, ...]:
    """抽取 pptx 内嵌图片，按页序返回去重且通过尺寸预过滤的图片。

    解析失败时返回空元组（与解析层「失败不抛、降级返回」的风格一致），
    由上层决定是否记录告警。
    """
    try:
        prs = Presentation(str(path))
    except Exception:  # noqa: BLE001 - 损坏文件不应中断整条流水线
        return ()

    seen: set[str] = set()
    images: list[PptxImage] = []
    for slide_index, slide in enumerate(prs.slides, start=1):
        for shape in _iter_picture_shapes(slide.shapes):
            try:
                image = shape.image
            except Exception:  # noqa: BLE001 - 个别图片对象不可读，跳过
                continue

            media_type = _MEDIA_TYPE_ALIASES.get(
                image.content_type, image.content_type
            )
            if media_type not in _SUPPORTED_MEDIA_TYPES:
                continue

            blob = image.blob
            digest = hashlib.sha256(blob).hexdigest()
            if digest in seen:  # 同图（如统一页脚 logo）只识别一次
                continue

            width, height = _image_size(image)
            max_side = max(width, height)
            if 0 < max_side < min_side_px:  # 尺寸已知且过小 → 装饰元素，预过滤
                continue

            seen.add(digest)
            images.append(
                PptxImage(
                    slide_index=slide_index,
                    media_type=media_type,
                    blob=blob,
                    width=width,
                    height=height,
                    sha256=digest,
                )
            )
    return tuple(images)
