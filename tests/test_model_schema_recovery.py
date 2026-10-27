"""Strict model-contract and local recovery checks; HTTP is explicitly mocked."""
from __future__ import annotations

import copy
import json

import httpx
import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from teachdesk import model
from teachdesk.model_schema import decode_plan, response_schema
from teachdesk.storage import Store


def wire(workflow):
    result = copy.deepcopy(workflow)
    result["inputs"] = [{"name": key, "description": value} for key, value in workflow["inputs"].items()]
    result["targets"] = [{"id": key, **value} for key, value in workflow["targets"].items()]
    for node in result["nodes"]:
        if node["kind"] == "key":
            node.setdefault("duration", None)
    return result


def endpoint(project, monkeypatch, response, *, finish="stop", refusal=None, status=200):
    store = project[0]
    monkeypatch.setenv("TEACHDESK_MODEL_KEY", "fixture-private-key-not-real")
    # Mimic a pre-0.2.1 config, proving OpenAI's strict default needs no reset.
    (store.root/"model.json").write_text(json.dumps({"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "consent": True, "local_no_key": False}))
    calls = []
    def handle(request):
        calls.append(request)
        if status != 200:
            return httpx.Response(status, text="private provider body fixture-private-key-not-real")
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(200, json={"choices": [{"finish_reason": finish, "message": {"content": response if isinstance(response, str) else json.dumps(response), "refusal": refusal}}],
                                        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "unsafe_note": "fixture-private-key-not-real"}})
    original = httpx.Client
    monkeypatch.setattr(model.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    return calls


def forbid_api(monkeypatch):
    monkeypatch.setattr(model.httpx, "Client", lambda **kw: pytest.fail("Local recovery must never send an API request"))


def test_schema_closes_objects_and_roundtrips_a_real_graph_fixture(project):
    store, task, _, _, _, workflow = project
    demos, frames = model.prepare_evidence(store, task)
    schema = response_schema([d["id"] for d in demos], [f["id"] for f in frames])
    Draft202012Validator.check_schema(schema)
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    result = decode_plan(json.dumps(wire(workflow)), workflow["sources"], [f["id"] for f in frames], True)
    assert result == workflow


def test_actual_request_uses_schema_and_only_creates_an_unreviewed_candidate(project, monkeypatch):
    store, task, train, held, _, workflow = project
    calls = endpoint(project, monkeypatch, wire(workflow))
    candidate = model.generate(store, task)
    assert len(calls) == 1 and held not in calls[0].content.decode()
    schema = json.loads(calls[0].content)["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["sources"]["items"]["enum"] == [train]
    assert store.version(candidate)["workflow"] == workflow
    assert store.version(candidate)["reviewed"] == 0
    assert store.task(task)["active_version"] is None
    reply = store.rows("SELECT * FROM model_replies")[0]
    assert reply["status"] == "accepted"
    assert json.loads(reply["metadata"])["usage"] == {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}


@pytest.mark.parametrize("bad_inputs", [[{"name": "item name", "description": "Text"}], [{"name": "item", "description": {"type": "string"}}], {"item": {"description": "Text"}}])
def test_bad_input_declarations_are_retained_without_retry_or_workflow(project, monkeypatch, bad_inputs):
    store, task, _, _, _, workflow = project
    reply = wire(workflow)
    reply["inputs"] = bad_inputs
    calls = endpoint(project, monkeypatch, reply)
    before = len(store.rows("SELECT * FROM versions"))
    with pytest.raises(ValueError, match="unsupported inputs format"):
        model.generate(store, task)
    assert len(calls) == 1 and len(store.rows("SELECT * FROM versions")) == before
    saved = store.rows("SELECT * FROM model_replies")[0]
    assert saved["status"] == "rejected" and json.loads(saved["content"])["inputs"] == bad_inputs
    assert store.rows("SELECT * FROM audit WHERE kind='model_reply_received'")
    forbid_api(monkeypatch)
    with pytest.raises(ValueError, match="unsupported inputs format"):
        model.recover(store, task)
    assert store.task(task)["active_version"] is None


def test_recover_after_local_failure_works_after_reopen_without_key_or_api(project, monkeypatch):
    import teachdesk.perception as perception
    store, task, _, _, _, workflow = project
    calls = endpoint(project, monkeypatch, wire(workflow))
    original = perception.materialize
    monkeypatch.setattr(perception, "materialize", lambda *a: (_ for _ in ()).throw(ValueError("simulated local validation failure")))
    with pytest.raises(ValueError, match="simulated local validation failure"):
        model.generate(store, task)
    monkeypatch.setattr(perception, "materialize", original)
    assert len(calls) == 1
    forbid_api(monkeypatch)
    monkeypatch.delenv("TEACHDESK_MODEL_KEY")
    candidate = model.recover(Store(store.root), task)
    assert store.version(candidate)["workflow"] == workflow
    assert store.version(candidate)["reviewed"] == 0
    assert store.task(task)["active_version"] is None
    with pytest.raises(ValueError, match="no rejected or pending reply"):
        model.recover(store, task)


@pytest.mark.parametrize("change", ["goal", "excluded_frame", "image_pixels", "answer"])
def test_changed_learning_context_cannot_reuse_a_stale_reply(project, monkeypatch, change):
    store, task, train, _, vid, workflow = project
    reply = wire(workflow)
    reply["inputs"] = [{"name": "bad name", "description": "Text"}]
    endpoint(project, monkeypatch, reply)
    with pytest.raises(ValueError):
        model.generate(store, task)
    if change == "goal":
        store.execute("UPDATE tasks SET description='Different task intent' WHERE id=?", (task,))
    elif change == "excluded_frame":
        metadata = json.loads(store.rows("SELECT metadata FROM demos WHERE id=?", (train,))[0]["metadata"])
        metadata["ignored_ranges"] = [[0, .1, "excluded"]]
        store.execute("UPDATE demos SET metadata=? WHERE id=?", (json.dumps(metadata), train))
    elif change == "image_pixels":
        frame = store.rows("SELECT path FROM frames WHERE demo=? ORDER BY t", (train,))[0]
        Image.new("RGB", (400, 250), "red").save(store.root/frame["path"])
    else:
        workflow["questions"] = [{"id": "q", "text": "Which item?", "blocking": True, "reference": "fixture"}]
        store.execute("UPDATE versions SET workflow=?,answers=? WHERE id=?", (json.dumps(workflow), json.dumps({"q": "New answer"}), vid))
    forbid_api(monkeypatch)
    with pytest.raises(ValueError, match="changed since this reply"):
        model.recover(store, task)


@pytest.mark.parametrize("bad", ["duplicate_inputs", "duplicate_targets", "completion", "crop", "unknown_frame", "unknown_source"])
def test_strict_format_does_not_bypass_semantic_or_evidence_checks(project, monkeypatch, bad):
    store, task, _, held, _, workflow = project
    reply = wire(workflow)
    if bad == "duplicate_inputs":
        reply["inputs"] = [{"name": "item", "description": "Text"}]*2
    elif bad == "duplicate_targets":
        reply["targets"].append(reply["targets"][0])
    elif bad == "completion":
        reply["completion"] = reply["start"]
    elif bad == "crop":
        reply["targets"][0]["bbox"] = [20, 20, 21, 21]
    elif bad == "unknown_frame":
        reply["targets"][0]["frame"] = store.rows("SELECT id FROM frames WHERE demo=?", (held,))[0]["id"]
    else:
        reply["sources"] = [held]
    calls = endpoint(project, monkeypatch, reply)
    before = len(store.rows("SELECT id FROM versions"))
    with pytest.raises(ValueError):
        model.generate(store, task)
    assert len(calls) == 1 and len(store.rows("SELECT id FROM versions")) == before
    assert store.rows("SELECT status FROM model_replies")[0]["status"] == "rejected"


@pytest.mark.parametrize("finish,refusal", [("length", None), ("stop", "Not provided")])
def test_refused_or_truncated_reply_is_never_promoted(project, monkeypatch, finish, refusal):
    store, task, _, _, _, workflow = project
    calls = endpoint(project, monkeypatch, wire(workflow), finish=finish, refusal=refusal)
    with pytest.raises(ValueError, match="refused or did not finish"):
        model.generate(store, task)
    assert len(calls) == 1 and store.task(task)["active_version"] is None


def test_api_credential_echo_is_redacted_and_cannot_be_recovered(project, monkeypatch):
    store, task, _, _, _, workflow = project
    reply = wire(workflow)
    reply["assumptions"] = ["fixture-private-key-not-real"]
    endpoint(project, monkeypatch, reply)
    with pytest.raises(ValueError, match="credential") as error:
        model.generate(store, task)
    assert "fixture-private-key-not-real" not in str(error.value)
    saved = store.rows("SELECT * FROM model_replies")[0]
    assert "fixture-private-key-not-real" not in json.dumps(saved)
    assert "fixture-private-key-not-real" not in json.dumps(store.rows("SELECT * FROM audit"))
    forbid_api(monkeypatch)
    monkeypatch.delenv("TEACHDESK_MODEL_KEY")
    with pytest.raises(ValueError, match="credential"):
        model.recover(store, task)


def test_http_failure_is_not_cached_or_retried(project, monkeypatch):
    store, task, _, _, _, workflow = project
    calls = endpoint(project, monkeypatch, wire(workflow), status=401)
    with pytest.raises(RuntimeError, match="401") as error:
        model.generate(store, task)
    assert len(calls) == 1 and "private provider body" not in str(error.value)
    assert not store.rows("SELECT * FROM model_replies")


@pytest.mark.parametrize("delete", ["demo", "project"])
def test_evidence_deletion_removes_derived_reply_data(project, monkeypatch, delete):
    store, task, train, _, _, workflow = project
    reply = wire(workflow)
    reply["inputs"] = [{"name": "bad name", "description": "Text"}]
    endpoint(project, monkeypatch, reply)
    with pytest.raises(ValueError):
        model.generate(store, task)
    assert store.rows("SELECT * FROM model_replies")
    if delete == "demo":
        store.delete_demo(train)
    else:
        store.delete_task(task)
    assert not store.rows("SELECT * FROM model_replies")


def test_nullable_key_duration_uses_recorded_style_without_inventing_a_hold(project):
    workflow = project[-1]
    workflow["nodes"][0].update(kind="key", keys=["enter"])
    original = copy.deepcopy(workflow)
    result = decode_plan(json.dumps(wire(workflow)), workflow["sources"], [target["frame"] for target in workflow["targets"].values()], True)
    assert result == original and "duration" not in result["nodes"][0]


def test_deleting_old_answer_source_removes_reply_even_without_its_screenshots(project, monkeypatch):
    store, task, train, _, _, workflow = project
    legacy = store.create_demo(task, {"capture_validation": 2})
    store.execute("UPDATE demos SET status='complete' WHERE id=?", (legacy,))
    previous = copy.deepcopy(workflow)
    previous["sources"] = [legacy]
    previous["questions"] = [{"id": "q", "text": "Which item?", "blocking": True, "reference": "fixture"}]
    version = store.add_version(task, previous)
    store.execute("UPDATE versions SET answers=? WHERE id=?", (json.dumps({"q": "Prior private answer"}), version))
    reply = wire(workflow)
    reply["inputs"] = [{"name": "bad name", "description": "Prior private answer"}]
    calls = endpoint(project, monkeypatch, reply)
    with pytest.raises(ValueError):
        model.generate(store, task)
    saved = store.rows("SELECT * FROM model_replies")[0]
    metadata = json.loads(saved["metadata"])
    assert metadata["sources"] == [train] and metadata["answer_sources"] == [legacy]
    assert "Prior private answer" in calls[0].content.decode()
    assert legacy not in calls[0].content.decode()
    store.delete_demo(legacy)
    assert not store.rows("SELECT * FROM model_replies")
    assert store.rows("SELECT id FROM demos WHERE id=?", (train,))


def test_response_mode_is_configurable_without_silent_fallback(project, monkeypatch):
    store = project[0]
    assert model.structured_outputs({"base_url": "https://api.openai.com/v1"})
    assert not model.structured_outputs({"base_url": "http://localhost:8080/v1"})
    config = {"base_url": "https://api.openai.com/v1", "model": "fixture-compatible-vision", "consent": True, "local_no_key": False, "structured_outputs": False}
    model.save_settings(store, config)
    assert not model.settings(store)["structured_outputs"]
    with pytest.raises(ValueError, match="enabled or disabled"):
        model.save_settings(store, {**config, "structured_outputs": "false"})
