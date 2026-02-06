"""MCP Server — exposes vibe_* tools for Claude Code."""
from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from vibe_linter.engine import Executor

mcp = FastMCP("vibe-linter")


def _get_executor() -> Executor:
    return Executor(os.path.join(os.getcwd(), ".vibe"))


@mcp.tool()
def vibe_get_status() -> str:
    """Get current workflow status, step, and allowed actions."""
    executor = _get_executor()
    try:
        st = executor.get_status()
        st["reminder"] = st["summary"]
        return json.dumps(st, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    finally:
        executor.close()


@mcp.tool()
def vibe_get_context(key: str | None = None) -> str:
    """Get workflow data/context, optionally filtered by key."""
    executor = _get_executor()
    try:
        data = executor.get_data()
        result = {key: data.get(key)} if key else data
        st = executor.get_status()
        return json.dumps({
            "data": result,
            "reminder": f'Current step: {st["current_step"]}',
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    finally:
        executor.close()


@mcp.tool()
def vibe_get_history(limit: int = 20) -> str:
    """Get workflow execution history."""
    executor = _get_executor()
    try:
        return json.dumps(executor.get_history(limit), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    finally:
        executor.close()


@mcp.tool()
def vibe_submit_output(data: dict) -> str:
    """Submit output data for the current workflow step."""
    executor = _get_executor()
    try:
        result = executor.submit(data)
        msg = result.message
        try:
            st = executor.get_status()
            msg += f'\n\n[Reminder] {st["summary"]}'
        except Exception:
            pass
        return msg
    except Exception as e:
        return f"Submit failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_skip_current(reason: str | None = None) -> str:
    """Skip the current workflow step."""
    executor = _get_executor()
    try:
        return executor.skip(reason).message
    except Exception as e:
        return f"Skip failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_retry_current() -> str:
    """Retry the current workflow step."""
    executor = _get_executor()
    try:
        return executor.retry().message
    except Exception as e:
        return f"Retry failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_goto(target: str) -> str:
    """Jump to a specific workflow step by name."""
    executor = _get_executor()
    try:
        return executor.goto(target).message
    except Exception as e:
        return f"Goto failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_approve(data: dict | None = None) -> str:
    """Approve the current waiting step."""
    executor = _get_executor()
    try:
        return executor.approve(data).message
    except Exception as e:
        return f"Approve failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_reject(reason: str | None = None) -> str:
    """Reject the current waiting step."""
    executor = _get_executor()
    try:
        return executor.reject(reason).message
    except Exception as e:
        return f"Reject failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_stop() -> str:
    """Stop the current workflow."""
    executor = _get_executor()
    try:
        return executor.stop().message
    except Exception as e:
        return f"Stop failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_resume() -> str:
    """Resume a stopped workflow."""
    executor = _get_executor()
    try:
        return executor.resume().message
    except Exception as e:
        return f"Resume failed: {e}"
    finally:
        executor.close()


@mcp.tool()
def vibe_back() -> str:
    """Go back to the previous workflow step."""
    executor = _get_executor()
    try:
        return executor.back().message
    except Exception as e:
        return f"Back failed: {e}"
    finally:
        executor.close()


def run_server():
    mcp.run(transport="stdio")
