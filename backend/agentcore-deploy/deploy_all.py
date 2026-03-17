#!/usr/bin/env python3
"""
Deploy all Super Agent platform agents to Amazon Bedrock AgentCore Runtime.

Uses boto3 create_agent_runtime with codeConfiguration (S3-based code deploy).
Each agent shares the same Python code but gets a unique system prompt via env vars.
"""
import io
import json
import os
import time
import zipfile

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNT_ID = "632930644527"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/AgentCoreRuntimeRole"
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
S3_BUCKET = "agentcore-code-632930644527-us-east-1"
S3_PREFIX = "agentcore-deploy"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

AGENTS = [
    {
        "name": "player-analyst",
        "display_name": "玩家数据分析师",
        "system_prompt": "你是一位专业的游戏数据分析师。你擅长分析玩家行为数据、留存率、付费转化率和LTV。请用数据驱动的方式提供运营建议。回答时请使用中文。",
    },
    {
        "name": "event-planner",
        "display_name": "活动策划助手",
        "system_prompt": "你是一位游戏活动策划专家。你擅长设计游戏内活动、奖励机制和限时活动。请根据玩家画像和游戏类型提供创意方案。回答时请使用中文。",
    },
    {
        "name": "content-localizer",
        "display_name": "多语言内容生成器",
        "system_prompt": "你是一位出海营销内容专家。你精通多语言内容创作和本地化，了解不同市场的文化差异和用户偏好。支持英语、日语、韩语、东南亚语言等。回答时请使用中文，但生成的营销内容请使用目标语言。",
    },
    {
        "name": "ad-optimizer",
        "display_name": "广告投放优化师",
        "system_prompt": "你是一位数字广告投放优化专家。你擅长Facebook、Google、TikTok等平台的广告投放策略，能够分析广告数据并提供优化建议。回答时请使用中文。",
    },
    {
        "name": "site-generator",
        "display_name": "AI建站助手",
        "system_prompt": "你是一位AI网站生成专家。你能根据用户的自然语言描述生成完整的网站代码，包括HTML、CSS和JavaScript。生成的网站应该是响应式的、美观的、符合现代设计标准的。回答时请使用中文。",
    },
    {
        "name": "seo-optimizer",
        "display_name": "SEO优化助手",
        "system_prompt": "你是一位SEO优化专家。你擅长网站SEO分析、关键词优化、meta标签生成和内容策略制定。回答时请使用中文。",
    },
    {
        "name": "hr-assistant",
        "display_name": "HR Assistant",
        "system_prompt": "You are an HR assistant specialized in recruitment and onboarding processes.",
    },
    {
        "name": "it-support",
        "display_name": "IT Support Agent",
        "system_prompt": "You are an IT support agent helping users with technical issues.",
    },
]


def build_agent_zip():
    """Build a zip of the agent source code."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ["agent_template.py", "requirements.txt"]:
            fpath = os.path.join(SCRIPT_DIR, fname)
            zf.write(fpath, fname)
    buf.seek(0)
    return buf.read()


def upload_to_s3(s3_client, zip_bytes, agent_name):
    """Upload agent code zip to S3."""
    key = f"{S3_PREFIX}/{agent_name}/code.zip"
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=zip_bytes)
    return key


def get_existing_runtimes(client):
    """List existing agent runtimes."""
    runtimes = {}
    token = None
    while True:
        kwargs = {}
        if token:
            kwargs["nextToken"] = token
        resp = client.list_agent_runtimes(**kwargs)
        for rt in resp.get("agentRuntimeSummaries", []):
            runtimes[rt["agentRuntimeName"]] = rt
        token = resp.get("nextToken")
        if not token:
            break
    return runtimes


def deploy_agent(client, agent_def, s3_key):
    """Deploy a single agent to AgentCore."""
    runtime_name = f"superAgent_{agent_def['name'].replace('-', '_')}"

    try:
        response = client.create_agent_runtime(
            agentRuntimeName=runtime_name,
            description=f"{agent_def['display_name']} - Super Agent Platform",
            agentRuntimeArtifact={
                "codeConfiguration": {
                    "code": {
                        "s3": {
                            "bucket": S3_BUCKET,
                            "prefix": s3_key,
                        }
                    },
                    "runtime": "PYTHON_3_12",
                    "entryPoint": ["agent_template.py"],
                }
            },
            networkConfiguration={"networkMode": "PUBLIC"},
            roleArn=ROLE_ARN,
            environmentVariables={
                "AGENT_SYSTEM_PROMPT": agent_def["system_prompt"],
                "MODEL_ID": MODEL_ID,
                "AWS_REGION": REGION,
            },
        )
        arn = response.get("agentRuntimeArn", "N/A")
        status = response.get("status", "N/A")
        print(f"  ✅ Created: {arn} (status: {status})")
        return True
    except client.exceptions.ConflictException:
        print(f"  ⏭️  Already exists, skipping")
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return False


def wait_for_ready(client, timeout=600):
    """Wait for all super-agent runtimes to become READY."""
    print(f"\n⏳ Waiting for runtimes to become READY (timeout: {timeout}s)...")
    start = time.time()
    target_names = {f"superAgent_{a['name'].replace('-', '_')}" for a in AGENTS}

    while (time.time() - start) < timeout:
        runtimes = get_existing_runtimes(client)
        statuses = {}
        for name in target_names:
            rt = runtimes.get(name)
            statuses[name] = rt.get("status", "NOT_FOUND") if rt else "NOT_FOUND"

        creating = [n for n, s in statuses.items() if s in ("CREATING", "UPDATING")]
        ready = [n for n, s in statuses.items() if s == "READY"]
        failed = [n for n, s in statuses.items() if s in ("FAILED", "DELETING")]

        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] Ready: {len(ready)}, Creating: {len(creating)}, Failed: {len(failed)}")

        if not creating:
            break

        time.sleep(30)

    return statuses


def main():
    print("🚀 Deploying all agents to Amazon Bedrock AgentCore")
    print(f"   Region:  {REGION}")
    print(f"   Model:   {MODEL_ID}")
    print(f"   Role:    {ROLE_ARN}")
    print(f"   S3:      s3://{S3_BUCKET}/{S3_PREFIX}/")
    print(f"   Agents:  {len(AGENTS)}")
    print()

    agentcore = boto3.client("bedrock-agentcore-control", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)

    # Check existing
    existing = get_existing_runtimes(agentcore)
    to_deploy = []
    for agent_def in AGENTS:
        runtime_name = f"superAgent_{agent_def['name'].replace('-', '_')}"
        if runtime_name in existing:
            status = existing[runtime_name].get("status", "?")
            print(f"  ⏭️  {runtime_name} already exists ({status})")
        else:
            to_deploy.append(agent_def)

    if not to_deploy:
        print("\n✅ All agents already deployed!")
    else:
        # Build and upload code
        print(f"\n📦 Building agent code zip...")
        zip_bytes = build_agent_zip()
        print(f"   Zip size: {len(zip_bytes)} bytes")

        for agent_def in to_deploy:
            runtime_name = f"superAgent_{agent_def['name'].replace('-', '_')}"
            print(f"\n🚀 [{agent_def['display_name']}] -> {runtime_name}")

            s3_key = upload_to_s3(s3, zip_bytes, agent_def["name"])
            print(f"  📤 Uploaded to s3://{S3_BUCKET}/{s3_key}")

            deploy_agent(agentcore, agent_def, s3_key)

        # Wait for all to be ready
        wait_for_ready(agentcore)

    # Final status
    runtimes = get_existing_runtimes(agentcore)
    print("\n" + "=" * 60)
    print("📋 Final Status")
    print("=" * 60)

    arns = {}
    for agent_def in AGENTS:
        runtime_name = f"superAgent_{agent_def['name'].replace('-', '_')}"
        rt = runtimes.get(runtime_name)
        if rt:
            status = rt.get("status", "?")
            arn = rt.get("agentRuntimeArn", "")
            rid = rt.get("agentRuntimeId", "")
            emoji = {"READY": "✅", "CREATING": "⏳", "UPDATING": "⏳"}.get(status, "❌")
            print(f"  {emoji} {agent_def['display_name']:20s} {runtime_name:35s} {status}")
            if arn:
                arns[agent_def["name"]] = arn
        else:
            print(f"  ❓ {agent_def['display_name']:20s} {runtime_name:35s} NOT FOUND")

    # Save ARN mapping
    if arns:
        mapping_path = os.path.join(SCRIPT_DIR, "runtime_arns.json")
        with open(mapping_path, "w") as f:
            json.dump(arns, f, indent=2)
        print(f"\n💾 ARN mapping saved to {mapping_path}")


if __name__ == "__main__":
    main()
