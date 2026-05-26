"""Tests for route_command_handler (PR-4 + PR-11 fix)."""
import pytest
from core.command_registry import route_command_handler


def test_route_command_no_omniroute(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_BASE_URL", raising=False)
    result = route_command_handler([])
    assert result["success"] is False
    assert "OmniRoute not active" in result["message"]
    assert result["env_updates"] == {}


def test_route_command_list(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_BASE_URL", "https://or.example.com")
    monkeypatch.setenv("ECOSYSTEM_OMNIROUTE_COMBO_SLUGS", "auto,priority,p2c")
    result = route_command_handler(["--list"])
    assert result["success"] is True
    assert "auto" in result["message"]
    assert "auto-free" in result["message"]  # builtin
    assert "priority" in result["message"]
    assert result["env_updates"] == {}


def test_route_command_valid_slug(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_BASE_URL", "https://or.example.com")
    monkeypatch.setenv("ECOSYSTEM_OMNIROUTE_COMBO_SLUGS", "auto,priority")
    result = route_command_handler(["priority"])
    assert result["success"] is True
    assert result["env_updates"] == {"OMNIROUTE_COMBO": "priority"}


def test_route_command_unknown_slug(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_BASE_URL", "https://or.example.com")
    monkeypatch.setenv("ECOSYSTEM_OMNIROUTE_COMBO_SLUGS", "auto")
    result = route_command_handler(["nonexistent"])
    assert result["success"] is False
    assert "Unknown combo" in result["message"]
    assert result["env_updates"] == {}


def test_route_command_none_clears(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_BASE_URL", "https://or.example.com")
    monkeypatch.setenv("OMNIROUTE_COMBO", "auto")
    result = route_command_handler(["none"])
    assert result["success"] is True
    assert result["env_updates"]["OMNIROUTE_COMBO"] is None
