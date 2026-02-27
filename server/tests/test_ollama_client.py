"""Tests for Ollama client configuration (tools, system prompt)."""

from ollama_client import TOOLS, SYSTEM_PROMPT, CONTEXT_WINDOW_SIZE, _build_ollama_messages


class TestToolDefinitions:
    """Verify tool definitions are well-formed for Ollama."""

    def test_tools_is_list(self):
        assert isinstance(TOOLS, list)
        assert len(TOOLS) == 2

    def test_web_search_tool_structure(self):
        tool = TOOLS[0]
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] == "web_search"
        assert "description" in fn
        assert fn["parameters"]["type"] == "object"
        assert "query" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["query"]

    def test_run_python_tool_structure(self):
        tool = TOOLS[1]
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] == "run_python"
        assert "description" in fn
        assert fn["parameters"]["type"] == "object"
        assert "code" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["code"]

    def test_run_python_description_mentions_packages(self):
        desc = TOOLS[1]["function"]["description"]
        for pkg in ["numpy", "pandas", "matplotlib", "yfinance"]:
            assert pkg in desc


class TestSystemPrompt:

    def test_contains_date(self):
        # The prompt includes a formatted date
        assert "202" in SYSTEM_PROMPT  # year

    def test_mentions_web_search(self):
        assert "web_search" in SYSTEM_PROMPT

    def test_mentions_run_python(self):
        assert "run_python" in SYSTEM_PROMPT

    def test_mentions_plt_show(self):
        assert "plt.show()" in SYSTEM_PROMPT


class TestBuildOllamaMessages:

    def test_basic_message_building(self):
        db_msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = _build_ollama_messages(db_msgs, new_user_message="how are you?")
        # system + 2 db msgs + 1 new user msg
        assert len(result) == 4
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == "how are you?"

    def test_empty_history(self):
        result = _build_ollama_messages([], new_user_message="first message")
        assert len(result) == 2  # system + user
        assert result[1]["content"] == "first message"

    def test_no_new_message(self):
        db_msgs = [{"role": "user", "content": "hello"}]
        result = _build_ollama_messages(db_msgs)
        assert len(result) == 2  # system + 1 db msg

    def test_sliding_window_with_summary(self):
        # Create more messages than CONTEXT_WINDOW_SIZE
        db_msgs = [
            {"role": "user", "content": f"msg {i}"}
            for i in range(CONTEXT_WINDOW_SIZE + 10)
        ]
        result = _build_ollama_messages(
            db_msgs,
            new_user_message="latest",
            summary="Previous conversation about testing.",
        )
        # system + summary system msg + last CONTEXT_WINDOW_SIZE msgs + new user
        assert len(result) == 2 + CONTEXT_WINDOW_SIZE + 1
        assert "Summary" in result[1]["content"] or "summary" in result[1]["content"].lower()
        assert result[-1]["content"] == "latest"

    def test_short_conversation_no_summary(self):
        """Summary should be ignored when conversation is short."""
        db_msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = _build_ollama_messages(
            db_msgs,
            summary="Some old summary",
        )
        # system + 2 db msgs, no summary injected
        assert len(result) == 3
        assert all("Summary" not in m.get("content", "") for m in result[1:])
