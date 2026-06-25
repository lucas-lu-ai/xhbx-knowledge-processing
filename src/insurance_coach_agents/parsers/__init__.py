"""确定性解析工具层：把 docx/pptx/pdf/txt 解析为 ``ParsedFile``。

本层不调用 LLM，纯解析，便于单测与节省 token。
"""

from .docx_parser import parse_docx
from .pdf_parser import parse_pdf
from .pptx_parser import parse_pptx
from .section_loader import load_section
from .txt_parser import parse_txt

__all__ = [
    "parse_docx",
    "parse_pptx",
    "parse_pdf",
    "parse_txt",
    "load_section",
]
