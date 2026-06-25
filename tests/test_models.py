"""``models`` 数据契约的单元测试。"""

from __future__ import annotations

from insurance_coach_agents.models import FileType, ParsedFile, RawSection


def _section(*files: ParsedFile) -> RawSection:
    return RawSection(
        case_name="案例X",
        section_name="第1节",
        section_dir="案例X/第1节",
        files=files,
    )


def test_char_count_derives_from_text_length():
    # Arrange
    parsed = ParsedFile(file_type=FileType.TXT, filename="a.txt", text="你好世界")

    # Act / Assert
    assert parsed.char_count == 4
    assert parsed.is_empty is False


def test_empty_text_is_reported_as_empty():
    parsed = ParsedFile(file_type=FileType.TXT, filename="a.txt", text="")
    assert parsed.is_empty is True
    assert parsed.char_count == 0


def test_primary_text_prefers_docx_over_other_types():
    # Arrange: txt 在前、docx 在后，仍应优先返回 docx
    txt = ParsedFile(file_type=FileType.TXT, filename="t.txt", text="转写")
    docx = ParsedFile(file_type=FileType.DOCX, filename="d.docx", text="讲义")
    section = _section(txt, docx)

    # Act / Assert
    assert section.primary_text == "讲义"


def test_primary_text_falls_back_when_docx_absent():
    pptx = ParsedFile(file_type=FileType.PPTX, filename="p.pptx", text="课件")
    txt = ParsedFile(file_type=FileType.TXT, filename="t.txt", text="转写")
    section = _section(pptx, txt)

    # docx/pdf 缺失 → 回退到 pptx（优先级高于 txt）
    assert section.primary_text == "课件"


def test_primary_text_skips_empty_docx():
    empty_docx = ParsedFile(file_type=FileType.DOCX, filename="d.docx", text="")
    txt = ParsedFile(file_type=FileType.TXT, filename="t.txt", text="转写")
    section = _section(empty_docx, txt)

    # 空 docx 被跳过 → 回退到 txt
    assert section.primary_text == "转写"


def test_primary_text_is_none_when_no_content():
    assert _section().primary_text is None


def test_first_text_of_returns_none_for_missing_type():
    section = _section(
        ParsedFile(file_type=FileType.TXT, filename="t.txt", text="转写")
    )
    assert section.first_text_of(FileType.PDF) is None


def test_total_chars_sums_all_files():
    section = _section(
        ParsedFile(file_type=FileType.DOCX, filename="d.docx", text="12345"),
        ParsedFile(file_type=FileType.TXT, filename="t.txt", text="678"),
    )
    assert section.total_chars == 8
