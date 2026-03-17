#!/usr/bin/env python3
"""
Test all 8 agents locally using agentcore dev.
Starts each agent on port 8080, sends a test prompt, verifies response, then stops.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8080
TIMEOUT_STARTUP = 45  # seconds to wait for server to start
TIMEOUT_INVOKE = 120  # seconds to wait for agent response

AGENTS = [
    {
        "name": "player-analyst",
        "display_name": "玩家数据分析师",
        "system_prompt": "你是一位专业的游戏数据分析师。你擅长分析玩家行为数据、留存率、付费转化率和LTV。请用数据驱动的方式提供运营建议。回答时请使用中文。",
        "test_prompt": "请简单介绍你的能力",
    },
    {
        "name": "event-planner",
        "display_name": "活动策划助手",
        "system_prompt": "你是一位游戏活动策划专家。你擅长设计游戏内活动、奖励机制和限时活动。请根据玩家画像和游戏类型提供创意方案。回答时请使用中文。",
        "test_prompt": "请简单介绍你的能力",
    },
    {
        "name": "content-localizer",
        "display_name": "多语言内容生成器",
        "system_prompt": "你是一位出海营销内容专家。你精通多语言内容创作和本地化，了解不同市场的文化差异和用户偏好。支持英语、日语、韩语、东南亚语言等。回答时请使用中文，但生成的营销内容请使用目标语言。",
        "test_prompt": "请简单介绍你的能力",
    },
    {
        "name": "ad-optimizer",
        "display_name": "广告投放优化师",
        "system_prompt": "你是一位数字广告投放优化专家。你擅长Facebook、Google、TikTok等平台的广告投放策略，能够分析广告数据并提供优化建议。回答时请使用中文。",
        "test_prompt": "请简单介绍你的能力",
    },
    {
        "name": "site-generator",
        "display_name": "AI建站助手",
        "system_prompt": "你是一位AI网站生成专家。你能根据用户的自然语言描述生成完整的网站代码，包括HTML、CSS和JavaScript。生成的网站应该是响应式的、美观的、符合现代设计标准的。回答时请使用中文。",
        "test_prompt": "请简单介绍你的能力",
    },
    {
        "name": "seo-optimizer",
        "display_name": "SEO优化助手",
        "system_prompt": "你是一位SEO优化专家。你擅长网站SEO分析、关键词优化、meta标签生成和内容策略制定。回答时请使用中文。",
        "test_prompt": "请简单介绍你的能力",
    },
    {
        "name": "hr-assistant",
        "display_name": "HR Assistant",
        "system_prompt": "You are an HR assistant specialized in recruitment and onboarding processes.",
        "test_prompt": "Briefly introduce yourself",
    },
    {
        "name": "it-support",
        "display_name": "IT Support Agent",
        "system_prompt": "You are an IT support agent helping users with technical issues.",
        "test_prompt": "Briefly introduce yourself",
    },
    {
        "name": "global-marketer",
        "display_name": "出海营销专家",
        "system_prompt": "你是一位资深的出海营销专家。你精通全球市场营销策略制定、多语言内容创作、社交媒体矩阵运营、KOL网红合作管理、广告投放优化、市场本地化和竞品分析。回答时请使用中文。",
        "test_prompt": "请简单介绍你的能力，特别是浏览器数据采集方面",
    },
]


def wait_for_server(port, timeout=TIMEOUT_STARTUP):
    """Wait for the dev server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(f"http://localhost:{port}/invocations",
                                         data=b'{"prompt":"ping"}',
                                         headers={"Content-Type": "application/json"},
                                         method="POST")
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            time.sleep(1)
    return False


def invoke_agent(port, prompt, timeout=TIMEOUT_INVOKE):
    """Send a prompt to the agent and return the response."""
    payload = json.dumps({"prompt": prompt}).encode()
    req = urllib.request.Request(
        f"http://localhost:{port}/invocations",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode())
    return body


def test_agent(agent_def, port=PORT):
    """Test a single agent: start dev server, invoke, stop."""
    name = agent_def["name"]
    display = agent_def["display_name"]
    print(f"\n{'='*60}")
    print(f"🧪 Testing: {display} ({name})")
    print(f"{'='*60}")

    env = os.environ.copy()
    env["AGENT_SYSTEM_PROMPT"] = agent_def["system_prompt"]
    env["MODEL_ID"] = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    env["AWS_REGION"] = "us-east-1"

    # Start agentcore dev
    proc = subprocess.Popen(
        ["agentcore", "dev", "--port", str(port)],
        cwd=SCRIPT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    try:
        print(f"  ⏳ Waiting for server on port {port}...")
        if not wait_for_server(port):
            print(f"  ❌ Server failed to start within {TIMEOUT_STARTUP}s")
            return False

        print(f"  ✅ Server ready, sending test prompt: {agent_def['test_prompt']}")
        result = invoke_agent(port, agent_def["test_prompt"])
        response_text = result.get("result", "")

        if response_text and len(response_text) > 10:
            # Show first 150 chars of response
            preview = response_text[:150].replace("\n", " ")
            print(f"  ✅ Response ({len(response_text)} chars): {preview}...")
            return True
        else:
            print(f"  ❌ Empty or too short response: {response_text}")
            return False

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

    finally:
        # Kill the process group
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
        # Wait for port to be released
        import socket
        for _ in range(30):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", port)) != 0:
                    break
            time.sleep(1)
        else:
            print(f"  ⚠️  Port {port} still in use after 30s")
        time.sleep(1)


def main():
    print("🚀 AgentCore Local Test — Testing all 8 agents")
    print(f"   Port: {PORT}")
    print(f"   Working dir: {SCRIPT_DIR}")

    results = {}
    for agent_def in AGENTS:
        ok = test_agent(agent_def)
        results[agent_def["name"]] = ok

    # Summary
    print(f"\n{'='*60}")
    print("📋 Test Results Summary")
    print(f"{'='*60}")
    passed = 0
    for agent_def in AGENTS:
        name = agent_def["name"]
        ok = results[name]
        emoji = "✅" if ok else "❌"
        print(f"  {emoji} {agent_def['display_name']:20s} ({name})")
        if ok:
            passed += 1

    print(f"\n  Total: {passed}/{len(AGENTS)} passed")

    if passed == len(AGENTS):
        print("\n🎉 All agents passed local testing!")
    else:
        print(f"\n⚠️  {len(AGENTS) - passed} agent(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
