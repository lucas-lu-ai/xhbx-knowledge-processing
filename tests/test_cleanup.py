"""产出清洗函数的单元测试。"""

from __future__ import annotations

from insurance_coach_agents.agents.cleanup import clean_markdown_body, clean_reason


def test_clean_reason_strips_trailing_triple_quotes():
    assert clean_reason("综合评分中等偏上。\"\"\"") == "综合评分中等偏上。"


def test_clean_reason_strips_surrounding_code_fence():
    assert clean_reason("```理由内容```") == "理由内容"


def test_clean_reason_keeps_normal_text():
    text = "该素材包含完整面谈流程，值得入库。"
    assert clean_reason(text) == text


def test_clean_markdown_removes_meta_annotation_line():
    md = (
        "# 标题\n"
        "## 模块\n"
        "正文要点。\n"
        "（注：以下内容基于讲义框架，结合转写稿提炼，未做扩展虚构。）\n"
        "更多正文。"
    )
    result = clean_markdown_body(md)
    assert "讲义框架" not in result
    assert "转写稿" not in result
    assert "正文要点。" in result
    assert "更多正文。" in result


def test_clean_markdown_normalizes_list_marker():
    md = "# 标题\n*   第一点\n*   第二点"
    result = clean_markdown_body(md)
    assert "- 第一点" in result
    assert "- 第二点" in result
    assert "*   " not in result


def test_clean_markdown_does_not_touch_bold():
    md = "# 标题\n**重点**：保险是信息传递。"
    result = clean_markdown_body(md)
    assert "**重点**" in result


def test_clean_markdown_strips_whole_code_fence():
    md = "```markdown\n# 标题\n正文\n```"
    result = clean_markdown_body(md)
    assert result.startswith("# 标题")
    assert "```" not in result


def test_clean_markdown_keeps_legitimate_note():
    # 含"注："但非加工元注释（无加工关键词）→ 保留
    md = "# 标题\n注：保费以保险合同约定为准。"
    result = clean_markdown_body(md)
    assert "保费以保险合同约定为准" in result
