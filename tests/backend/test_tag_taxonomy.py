from core.tags import derive_tag_categories, infer_tag_category
from core.domain.models import Event


def test_infer_tag_category_for_common_specific_tags() -> None:
    assert infer_tag_category("明日方舟十四章") == "游戏"
    assert infer_tag_category("卫戍协议") == "游戏"
    assert infer_tag_category("大五人格") == "知识"
    assert infer_tag_category("记忆系统") == "技术"
    assert infer_tag_category("示好告白") == "情感"


def test_derive_tag_categories_keeps_one_category_per_tag() -> None:
    result = derive_tag_categories(["明日方舟十四章", "大五人格", "记忆系统"])

    assert result == {
        "明日方舟十四章": "游戏",
        "大五人格": "知识",
        "记忆系统": "技术",
    }


def test_event_web_dict_includes_derived_tag_categories() -> None:
    event = Event(
        event_id="e1",
        chat_content_tags=["明日方舟十四章", "记忆系统"],
    )

    data = event.to_web_dict()

    assert data["tag_categories"] == {
        "明日方舟十四章": "游戏",
        "记忆系统": "技术",
    }
