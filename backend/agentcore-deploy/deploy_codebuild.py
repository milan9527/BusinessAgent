#!/usr/bin/env python3
"""
Deploy all agents to AgentCore using the starter toolkit with CodeBuild.
Creates a .bedrock_agentcore.yaml with all agents and launches them.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

import boto3
import yaml

REGION = "us-east-1"
ACCOUNT_ID = "632930644527"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/AgentCoreRuntimeRole"
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

AGENTS = [
    {
        "name": "player_analyst",
        "display_name": "玩家数据分析师",
        "system_prompt": "你是一位专业的游戏数据分析师。你擅长分析玩家行为数据、留存率、付费转化率和LTV。请用数据驱动的方式提供运营建议。回答时请使用中文。",
    },
    {
        "name": "event_planner",
        "display_name": "活动策划助手",
        "system_prompt": "你是一位游戏活动策划专家。你擅长设计游戏内活动、奖励机制和限时活动。请根据玩家画像和游戏类型提供创意方案。回答时请使用中文。",
    },
    {
        "name": "content_localizer",
        "display_name": "多语言内容生成器",
        "system_prompt": "你是一位出海营销内容专家。你精通多语言内容创作和本地化，了解不同市场的文化差异和用户偏好。支持英语、日语、韩语、东南亚语言等。回答时请使用中文，但生成的营销内容请使用目标语言。",
    },
    {
        "name": "ad_optimizer",
        "display_name": "广告投放优化师",
        "system_prompt": "你是一位数字广告投放优化专家。你擅长Facebook、Google、TikTok等平台的广告投放策略，能够分析广告数据并提供优化建议。回答时请使用中文。",
    },
    {
        "name": "site_generator",
        "display_name": "AI建站助手",
        "system_prompt": "你是一位AI网站生成专家。你能根据用户的自然语言描述生成完整的网站代码，包括HTML、CSS和JavaScript。生成的网站应该是响应式的、美观的、符合现代设计标准的。回答时请使用中文。",
    },
    {
        "name": "seo_optimizer",
        "display_name": "SEO优化助手",
        "system_prompt": "你是一位SEO优化专家。你擅长网站SEO分析、关键词优化、meta标签生成和内容策略制定。回答时请使用中文。",
    },
    {
        "name": "hr_assistant",
        "display_name": "HR Assistant",
        "system_prompt": "You are an HR assistant specialized in recruitment and onboarding processes.",
    },
    {
        "name": "it_support",
        "display_name": "IT Support Agent",
        "system_prompt": "You are an IT support agent helping users with technical issues.",
    },
]


def generate_agent_code(agent_def):
    """Generate Python code for a specific agent with baked-in system prompt."""
    return f'''"""Agent: {agent_def["display_name"]}"""
import os
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()
_agent = None

@app.entrypoint
def invoke(payload):
    global _agent
    if _agent is None:
        from strands import Agent
        from strands.models import BedrockModel
        model = BedrockModel(
            model_id=os.environ.get("MODEL_ID", "{MODEL_ID}"),
            region_name=os.environ.get("AWS_REGION", "{REGION}"),
            max_tokens=4096,
        )
        _agent = Agent(model=model, system_prompt="""{agent_def["system_prompt"]}""")
    user_message = payload.get("prompt", payload.get("message", "Hello"))
    result = _agent(user_message)
    return {{"result": str(result)}}

if __name__ == "__main__":
    app.run()
'''


def deploy_single_agent(agent_def):
    """Deploy a single agent using agentcore launch --code-build."""
    name = agent_def["name"]
    runtime_name = f"superAgent_{name}"

    tmp = tempfile.mkdtemp(prefix=f"agentcore-{name}-")
    try:
        # Write agent code
        agent_code = generate_agent_code(agent_def)
        with open(os.path.join(tmp, "agent.py"), "w") as f:
            f.write(agent_code)

        # Write requirements
        with open(os.path.join(tmp, "requirements.txt"), "w") as f:
            f.write("strands-agents\nbedrock-agentcore\n")

        # Write YAML config
        config = {
            "agents": {
                runtime_name: {
                    "entry_point": "agent.py",
                    "deployment_type": "container",
                    "role_arn": ROLE_ARN,
                    "region": REGION,
                    "network_mode": "PUBLIC",
                }
            }
        }
        with open(os.path.join(tmp, ".bedrock_agentcore.yaml"), "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        print(f"  Launching via CodeBuild...")
        result = subprocess.run(
            ["agentcore", "launch", "--agent", runtime_name, "--code-build"],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=600,
            input="\n\n\n",
        )

        if result.returncode == 0:
            print(f"  ✅ Success")
            # Extract ARN from output
            for line in result.stdout.split("\n"):
                if "arn:" in line:
                    print(f"  {line.strip()}")
            return True
        else:
            print(f"  ❌ Failed (RC={result.returncode})")
            stderr = result.stderr.strip()
            if stderr:
                # Print last 5 lines of error
                lines = stderr.split("\n")
                for line in lines[-5:]:
                    print(f"  {line}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout (600s)")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("🚀 Deploying all agents to AgentCore (container via CodeBuild)")
    print(f"   Region: {REGION}")
    print(f"   Model:  {MODEL_ID}")
    print(f"   Agents: {len(AGENTS)}\n")

    results = {}
    for agent_def in AGENTS:
        runtime_name = f"superAgent_{agent_def['name']}"
        print(f"\n[{agent_def['display_name']}] -> {runtime_name}")
        ok = deploy_single_agent(agent_def)
        results[agent_def["name"]] = ok

    # Print summary
    print("\n" + "=" * 50)
    print("📋 Summary")
    print("=" * 50)
    for agent_def in AGENTS:
        emoji = "✅" if results.get(agent_def["name"]) else "❌"
        print(f"  {emoji} {agent_def['display_name']}")

    # Check final status
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    arns = {}
    resp = client.list_agent_runtimes()
    for rt in resp.get("agentRuntimeSummaries", []):
        if rt["agentRuntimeName"].startswith("superAgent_"):
            arns[rt["agentRuntimeName"]] = rt.get("agentRuntimeArn", "")
            print(f"  {rt['agentRuntimeName']}: {rt['status']}")

    if arns:
        mapping = {k.replace("superAgent_", "").replace("_", "-"): v for k, v in arns.items()}
        with open(os.path.join(SCRIPT_DIR, "runtime_arns.json"), "w") as f:
            json.dump(mapping, f, indent=2)
        print(f"\n💾 Saved {len(mapping)} ARNs to runtime_arns.json")


if __name__ == "__main__":
    main()
