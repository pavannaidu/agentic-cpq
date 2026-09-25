from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "src" / "app" / "client"
STATIC = ROOT / "src" / "app" / "static"


def _read(relative: str) -> str:
    return (CLIENT / relative).read_text()


def test_react_appkit_entrypoint_and_hashed_build_exist() -> None:
    package = _read("package.json")
    main = _read("src/main.tsx")
    html = (STATIC / "index.html").read_text()

    assert '"@databricks/appkit-ui": "0.57.0"' in package
    assert 'import "./styles.css"' in main
    assert "createRoot" in main
    assert '<div id="root"></div>' in html

    asset_paths = re.findall(r'(?:src|href)="(/static/assets/[^"]+)"', html)
    assert len(asset_paths) == 2
    assert all((STATIC / path.removeprefix("/static/")).is_file() for path in asset_paths)


def test_single_input_uses_the_in_process_agent_contract() -> None:
    app = _read("src/App.tsx")
    api = _read("src/api.ts")

    assert 'intent: "auto"' in app
    assert "onIntentChange" not in app
    assert "await streamAgent(request" in app
    assert "await api.agentQuery(request" in app
    assert 'fetch("/api/agent/stream"' in api
    assert 'fetchJson<Recommendation |' in api
    assert '"/api/agent/query"' in api
    assert "api.genie" not in app
    assert '"/api/genie/ask"' not in api
    assert "buildAgentProvider" not in app
    assert "agent_provider:" not in app

    copilot = _read("src/components/CopilotPanel.tsx")
    assert "ToggleGroup" not in copilot
    assert "Genie + Web" not in copilot
    assert "Quotes and governed sales answers." not in copilot
    assert "Ask about this quote or request changes." in copilot
    assert "Message Genie" in copilot
    assert "AI deal desk" not in copilot
    assert "What can I help you move forward?" not in copilot
    assert "Suggested workflows" not in copilot
    assert "samplePrompts" not in copilot
    assert "buildCopilotSuggestions" not in copilot


def test_agent_stream_keeps_progress_cancellation_and_blocking_fallback() -> None:
    app = _read("src/App.tsx")
    api = _read("src/api.ts")

    assert "new AbortController()" in app
    assert "controllerRef.current?.abort()" in app
    assert "setStages((current) => updateStages" in app
    assert "if (!received && !controller.signal.aborted)" in app
    assert "await api.agentQuery(request, controller.signal)" in app
    assert 'Accept: "text/event-stream"' in api
    assert "response.body.getReader()" in api


def test_conversational_answers_render_safely_with_ai_trust_controls() -> None:
    copilot = _read("src/components/CopilotPanel.tsx")
    evidence = _read("src/components/EvidencePanel.tsx")

    assert 'role="log"' in copilot
    assert "renderAnswer(message.content" in copilot
    assert "dangerouslySetInnerHTML" not in copilot
    assert copilot.count("AI-generated") == 1
    assert "Agent answer" not in copilot
    assert "> Details</Button>" in copilot
    assert "Answer details" not in evidence
    assert "Details" in evidence
    assert "Uses approved app access." in evidence
    assert "View query details" in evidence
    assert 'title="Sources"' in evidence
    assert 'title="Checks"' in evidence


def test_ui_uses_appkit_responsive_workspace_components() -> None:
    app = _read("src/App.tsx")
    css = _read("src/styles.css")

    assert "ResizablePanelGroup" in app
    assert "TabsTrigger value=\"copilot\"" in app
    assert "TabsTrigger value=\"quote\"" in app
    assert "ProductDialog" in app
    assert "HistoryPanel" in app
    assert "EvidencePanel" in app
    assert "@media (max-width: 390px)" in css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)


def test_recommendation_apply_is_idempotent_and_revision_guarded() -> None:
    app = _read("src/App.tsx")
    api = _read("src/api.ts")

    assert "recommendation.recommendation_id" in app
    assert "recommendation.revision" in app
    assert "api.applyRecommendation" in app
    assert "result.already_applied" in app
    assert "/recommendations/apply" in api
    assert "expected_revision" in api


def test_identity_contract_uses_backend_authorized_view_fields() -> None:
    app = _read("src/App.tsx")
    types = _read("src/types.ts")
    backend = (ROOT / "src" / "app" / "server" / "main.py").read_text()

    assert "allowed_views?: ViewRole[]" in types
    assert "default_view?: ViewRole" in types
    assert "user?.allowed_views" in app
    assert '"allowed_views": list(actor.allowed_views)' in backend
    assert '"default_view": "seller"' in backend
    assert "allowed_view_roles" not in app
