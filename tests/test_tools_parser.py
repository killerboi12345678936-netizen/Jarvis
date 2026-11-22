
from backend.tools.parser import ToolStreamFilter


def feed_all(text, chunk_size=7):
    stream_filter = ToolStreamFilter()

    visible = ""

    for start in range(0, len(text), chunk_size):
        visible += stream_filter.feed(text[start:start + chunk_size])

    return visible + stream_filter.finish(), stream_filter


def test_correct_marker_stripped_and_registered():
    visible, stream_filter = feed_all(
        'Hello. <<TOOL:{"name": "get_time", "arguments": {}}>>'
    )

    assert visible.strip() == "Hello."
    assert stream_filter.tool_calls == [("get_time", {})]
    assert stream_filter.invalid_blocks == []


def test_marker_split_across_chunk_boundaries():
    text = 'A <<TOOL:{"name": "system_info", "arguments": {}}>> B'

    for chunk_size in range(1, 12):
        visible, stream_filter = feed_all(text, chunk_size)

        assert visible == "A  B", chunk_size
        assert stream_filter.tool_calls == [
            ("system_info", {})
        ], chunk_size


def test_single_bracket_marker():
    visible, stream_filter = feed_all(
        'Hi. <TOOL:{"name": "get_time", "arguments": {}}>'
    )

    assert visible.strip() == "Hi."
    assert stream_filter.tool_calls == [("get_time", {})]


def test_bare_tool_name_marker():
    visible, stream_filter = feed_all("<<TOOL:get_time>>")

    assert visible == ""
    assert stream_filter.tool_calls == [("get_time", {})]


def test_invalid_json_block_hidden_and_collected():
    # Unparseable markup must never reach the user; the chat loop
    # uses invalid_blocks to give the model a corrective round.
    text = 'Before <<TOOL:not_json_at_all>> after'

    visible, stream_filter = feed_all(text)

    assert visible == "Before  after"
    assert stream_filter.tool_calls == []
    assert stream_filter.invalid_blocks == ["not_json_at_all"]


def test_json_with_inner_gt_character():
    text = (
        '<<TOOL:{"name": "create_note", "arguments": '
        '{"filename": "a.txt", "content": "1 > 0"}}>>'
    )

    visible, stream_filter = feed_all(text)

    assert visible == ""
    assert stream_filter.tool_calls == [
        ("create_note", {"filename": "a.txt", "content": "1 > 0"})
    ]


def test_unknown_bare_word_hidden_and_collected():
    # A bare word that is neither JSON nor a registered zero-argument
    # tool is unparseable; it stays hidden and triggers a corrective
    # round via invalid_blocks.
    _, stream_filter = feed_all("<<TOOL:destroy_everything>>")

    assert stream_filter.tool_calls == []
    assert stream_filter.invalid_blocks == ["destroy_everything"]


def test_unknown_name_in_valid_json_registered_for_feedback():
    # Valid JSON with an unregistered name is still registered and
    # hidden; the dispatcher reports the unknown name back to the
    # model so it can retry with a real tool.
    _, stream_filter = feed_all(
        '<<TOOL:{"name": "time_machine", "arguments": {}}>>'
    )

    assert stream_filter.tool_calls == [("time_machine", {})]
    assert stream_filter.invalid_blocks == []


def test_text_without_markers_passes_through():
    text = "Plain answer with 3.14 decimals and no tools."

    visible, stream_filter = feed_all(text)

    assert visible == text
    assert stream_filter.tool_calls == []


def test_multiple_tool_calls():
    text = (
        '<<TOOL:{"name": "get_time", "arguments": {}}>>'
        '<<TOOL:{"name": "system_info", "arguments": {}}>>'
    )

    _, stream_filter = feed_all(text)

    assert stream_filter.tool_calls == [
        ("get_time", {}),
        ("system_info", {}),
    ]


def test_extra_closing_brace_is_tolerated():
    text = '<<TOOL:{"name": "get_time", "arguments": {}}}>>'

    visible, stream_filter = feed_all(text)

    assert visible == ""
    assert stream_filter.tool_calls == [("get_time", {})]
    assert stream_filter.invalid_blocks == []

    for chunk_size in range(1, 12):
        visible, stream_filter = feed_all(text, chunk_size)

        assert visible == "", chunk_size
        assert stream_filter.tool_calls == [("get_time", {})], chunk_size


def test_single_bracket_with_extra_brace():
    text = '<TOOL:{"name": "get_time", "arguments": {}}}>'

    visible, stream_filter = feed_all(text)

    assert visible == ""
    assert stream_filter.tool_calls == [("get_time", {})]


def test_unterminated_marker_with_complete_body_is_salvaged():
    text = 'Hi <<TOOL:{"name": "get_time", "arguments": {}}}'

    for chunk_size in (3, 7, 40):
        visible, stream_filter = feed_all(text, chunk_size)

        assert visible.strip() == "Hi", chunk_size
        assert stream_filter.tool_calls == [("get_time", {})], chunk_size


def test_unterminated_marker_with_garbage_stays_visible():
    visible, stream_filter = feed_all(
        'Answer <<TOOL:{"name": "get_ti',
    )

    assert visible.startswith("Answer ")
    assert stream_filter.tool_calls == []


def test_unterminated_marker_at_stream_end():
    visible, stream_filter = feed_all("Answer <<TOOL:{\"name\": \"get_ti")

    assert visible.startswith("Answer ")
    assert stream_filter.tool_calls == []
