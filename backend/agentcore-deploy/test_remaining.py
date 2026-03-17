#!/usr/bin/env python3
"""Quick test for the 4 agents that failed due to port timing."""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8080

AGENTS = [
    {
        "name": "event-planner",
        "display_name": "活动策划助手",
        "system_prompt": "你是一位游戏活动策划专家。你擅长设计游戏内活动、奖励机制和限时活动。请根据玩家画像和游戏类型提供创意方案。回答时请使用中文。",
        "test_prompt": "请用一句话介绍你自己",
    },
    {
        "name": "ad-optimizer",
        "display_name": "广告投放优化师",
        "system_prompt": "你是一位数字广告投放优化专家。你擅长Facebook、Google、TikTok等平台的广告投放策略，能够分析广告数据并提供优化建议。回答时请使用中文。",
        "test_prompt": "请用一句话介绍你自己",
    },
    {
        "name": "seo-optimizer",
        "display_name": "SEO优化助手",
        "system_prompt": "你是一位SEO优化专家。你擅长网站SEO分析、关键词优化、meta标签生成和内容策略制定。回答时请使用中文。",
        "test_prompt": "请用一句话介绍你自己",
    },
    {
        "name": "it-support",
        "display_name": "IT Support Agent",
        "system_prompt": "You are an IT support agent helping users with technical issues.",
        "test_prompt": "Say hi in one sentence",
    },
]


def wait_port_free(port, timeout=30):
    for _ in range(timeout):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return True
        time.sleep(1)
    return False


def wait_for_server(port, timeout=45):
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(
                f"http://localhost:{port}/invocations",
                data=b'{"prompt":"ping"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            time.sleep(1)
    return False


def test_agent(agent_def):
    name = agent_def["name"]
    display = agent_def["display_name"]
    print(f"\n{'='*60}")
    print(f"🧪 Testing: {display} ({name})")
    print(f"{'='*60}")

    # Ensure port is free
    if not wait_port_free(PORT, 15):
        print(f"  ❌ Port {PORT} still in use")
        return False

    env = os.environ.copy()
    env["AGENT_SYSTEM_PROMPT"] = agent_def["system_prompt"]
    env["MODEL_ID"] = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    env["AWS_REGION"] = "us-east-1"

    proc = subprocess.Popen(
        ["agentcore", "dev", "--port", str(PORT)],
        cwd=SCRIPT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    try:
        print(f"  ⏳ Waiting for server...")
        if not wait_for_server(PORT):
            print(f"  ❌ Server failed to start")
            return False

        print(f"  ✅ Server ready, invoking...")
        payload = json.dumps({"prompt": agent_def["test_prompt"]}).encode()
        req = urllib.request.Request(
            f"http://localhost:{PORT}/invocations",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120)
        body = json.loads(resp.read().decode())
        text = body.get("result", "")

        if text and len(text) > 10:
            preview = text[:120].replace("\n", " ")
            print(f"  ✅ Response ({len(text)} chars): {preview}...")
            return True
        else:
            print(f"  ❌ Bad response: {text}")
            return False

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        # Wait for port release
        wait_port_free(PORT, 15)
        time.sleep(1)


def main():
    results = {}
    for agent_def in AGENTS:
        ok = test_agent(agent_def)
        results[agent_def["name"]] = ok

    print(f"\n{'='*60}")
    print("📋 Results")
    print(f"{'='*60}")
    for a in AGENTS:
        emoji = "✅" if results[a["name"]] else "❌"
        print(f"  {emoji} {a['display_name']}")

    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{len(AGENTS)} passed")


if __name__ == "__main__":
    main()
