#!/usr/bin/env python3
"""
Deploy all agents to AgentCore using CodeBuild (cloud container build).
This avoids the cold start timeout issue with code deployment by pre-installing deps.
"""
import boto3
import io
import json
import os
import time
import zipfile

REGION = "us-east-1"
ACCOUNT_ID = "632930644527"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/AgentCoreRuntimeRole"
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
S3_BUCKET = "agentcore-code-632930644527-us-east-1"
ECR_REPO = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/super-agent-runtime"

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

AGENT_CODE_TEMPLATE = '''"""Agent for Bedrock AgentCore Runtime: {display_name}"""
import os
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()
_agent = None

SYSTEM_PROMPT = """{system_prompt}"""

@app.entrypoint
def invoke(payload):
    global _agent
    if _agent is None:
        from strands import Agent
        from strands.models import BedrockModel
        model = BedrockModel(
            model_id=os.environ.get("MODEL_ID", "{model_id}"),
            region_name=os.environ.get("AWS_REGION", "{region}"),
            max_tokens=4096,
        )
        _agent = Agent(model=model, system_prompt=SYSTEM_PROMPT)
    user_message = payload.get("prompt", payload.get("message", "Hello"))
    result = _agent(user_message)
    return {{"result": str(result)}}

if __name__ == "__main__":
    app.run()
'''

DOCKERFILE = '''FROM --platform=linux/arm64 python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .
EXPOSE 8080
CMD ["python", "agent.py"]
'''

REQUIREMENTS = "strands-agents\nbedrock-agentcore\n"


def build_agent_zip(agent_def):
    """Build a zip with agent code, Dockerfile, and requirements."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Agent code with baked-in system prompt
        code = AGENT_CODE_TEMPLATE.format(
            display_name=agent_def["display_name"],
            system_prompt=agent_def["system_prompt"],
            model_id=MODEL_ID,
            region=REGION,
        )
        zf.writestr("agent.py", code)
        zf.writestr("requirements.txt", REQUIREMENTS)
        zf.writestr("Dockerfile", DOCKERFILE)
    buf.seek(0)
    return buf.read()


def get_existing_runtimes(client):
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


def main():
    print("🚀 Deploying all agents to AgentCore (container via CodeBuild)")
    print(f"   Region: {REGION}, Model: {MODEL_ID}")
    print(f"   Agents: {len(AGENTS)}\n")

    agentcore = boto3.client("bedrock-agentcore-control", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)

    # First, delete existing code-deploy runtimes that have cold start issues
    EXISTING_IDS = {
        "player_analyst": "superAgent_player_analyst-EUT7w667Tw",
        "event_planner": "superAgent_event_planner-HX4lB2BBg2",
        "content_localizer": "superAgent_content_localizer-03ybDKDN6F",
        "ad_optimizer": "superAgent_ad_optimizer-01Xl0dDM7I",
        "site_generator": "superAgent_site_generator-BhHO4MHyND",
        "seo_optimizer": "superAgent_seo_optimizer-yLUocs3zri",
        "hr_assistant": "superAgent_hr_assistant-YwrCLo8CPI",
        "it_support": "superAgent_it_support-xJvASCG0Cj",
    }

    print("🗑️  Deleting old code-deploy runtimes...")
    for name, rid in EXISTING_IDS.items():
        try:
            agentcore.delete_agent_runtime(agentRuntimeId=rid)
            print(f"  Deleted {name} ({rid})")
        except Exception as e:
            print(f"  Skip {name}: {e}")

    print("\nWaiting 15s for deletions to propagate...")
    time.sleep(15)

    # Ensure ECR repo exists
    ecr = boto3.client("ecr", region_name=REGION)
    try:
        ecr.create_repository(repositoryName="super-agent-runtime")
    except ecr.exceptions.RepositoryAlreadyExistsException:
        pass

    # Deploy each agent
    arns = {}
    for agent_def in AGENTS:
        runtime_name = f"superAgent_{agent_def['name']}"
        print(f"\n🚀 [{agent_def['display_name']}] -> {runtime_name}")

        # Upload code zip to S3
        zip_bytes = build_agent_zip(agent_def)
        s3_key = f"agentcore-deploy/{agent_def['name']}/container.zip"
        s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=zip_bytes)
        print(f"  📤 Uploaded {len(zip_bytes)} bytes to s3://{S3_BUCKET}/{s3_key}")

        # Create with container config (CodeBuild will build the image)
        try:
            resp = agentcore.create_agent_runtime(
                agentRuntimeName=runtime_name,
                description=f"{agent_def['display_name']} - Super Agent Platform",
                agentRuntimeArtifact={
                    "containerConfiguration": {
                        "containerUri": f"s3://{S3_BUCKET}/{s3_key}",
                    }
                },
                networkConfiguration={"networkMode": "PUBLIC"},
                roleArn=ROLE_ARN,
            )
            arn = resp.get("agentRuntimeArn", "")
            print(f"  ✅ Created: {arn} (status: {resp.get('status')})")
            arns[agent_def["name"]] = arn
        except Exception as e:
            print(f"  ❌ Failed: {e}")

    # Wait for ready
    if arns:
        print(f"\n⏳ Waiting for {len(arns)} runtimes to build and become READY...")
        start = time.time()
        while (time.time() - start) < 900:
            all_ready = True
            for name, arn in arns.items():
                rid = arn.split("/")[-1]
                try:
                    resp = agentcore.get_agent_runtime(agentRuntimeId=rid)
                    status = resp["status"]
                    if status != "READY":
                        all_ready = False
                except:
                    all_ready = False
            elapsed = int(time.time() - start)
            if all_ready:
                print(f"  ✅ All READY after {elapsed}s")
                break
            print(f"  [{elapsed}s] Still building...")
            time.sleep(30)

    # Save ARN mapping
    mapping_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime_arns.json")
    with open(mapping_path, "w") as f:
        json.dump(arns, f, indent=2)
    print(f"\n💾 ARN mapping saved to {mapping_path}")

    # Print final status
    print("\n" + "=" * 60)
    print("📋 Final Status")
    print("=" * 60)
    for agent_def in AGENTS:
        name = agent_def["name"]
        arn = arns.get(name)
        if arn:
            rid = arn.split("/")[-1]
            try:
                resp = agentcore.get_agent_runtime(agentRuntimeId=rid)
                print(f"  {agent_def['display_name']:20s} {resp['status']}")
            except:
                print(f"  {agent_def['display_name']:20s} UNKNOWN")
        else:
            print(f"  {agent_def['display_name']:20s} NOT DEPLOYED")


if __name__ == "__main__":
    main()
