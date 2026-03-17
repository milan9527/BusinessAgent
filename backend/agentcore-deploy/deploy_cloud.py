#!/usr/bin/env python3
"""
Deploy all 8 agents to Amazon Bedrock AgentCore using `agentcore deploy` (CodeBuild).

This script:
1. Generates .bedrock_agentcore.yaml with all 8 agent configs
2. For each agent, generates a dedicated Python entrypoint with baked-in system prompt
3. Deploys each agent via `agentcore deploy -a <name>` (CodeBuild, no local Docker)
4. Collects ARNs and saves to runtime_arns.json
"""
import json
import os
import subprocess
import sys
import time

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "skills")
REGION = "us-east-1"
ACCOUNT_ID = "632930644527"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/AgentCoreRuntimeRole"
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

# Mapping: agent_name -> list of skill folder names to inject
AGENT_SKILLS = {
    "player_analyst": ["game-player-retention", "user-behavior-funnel"],
    "event_planner": ["game-player-retention"],
    "content_localizer": ["global-marketing"],
    "ad_optimizer": ["global-marketing", "user-behavior-funnel"],
    "site_generator": [],
    "seo_optimizer": [],
    "hr_assistant": [],
    "it_support": [],
    "global_marketer": ["global-marketing", "global-marketing-browser"],
}


def load_skill_content(skill_name):
    """Load SKILL.md body content (strip YAML frontmatter)."""
    path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if not os.path.exists(path):
        print(f"  ⚠️  Skill not found: {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Strip YAML frontmatter (between --- markers)
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()
    return content


def build_system_prompt_with_skills(base_prompt, agent_name):
    """Enrich system prompt with relevant skill knowledge."""
    skill_names = AGENT_SKILLS.get(agent_name, [])
    if not skill_names:
        return base_prompt

    skill_sections = []
    for sn in skill_names:
        body = load_skill_content(sn)
        if body:
            skill_sections.append(f"<skill name=\"{sn}\">\n{body}\n</skill>")

    if not skill_sections:
        return base_prompt

    skills_block = "\n\n".join(skill_sections)
    return (
        f"{base_prompt}\n\n"
        f"你拥有以下专业技能知识，请在回答中充分运用这些知识框架和指标体系：\n\n"
        f"{skills_block}"
    )


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
    {
        "name": "global_marketer",
        "display_name": "出海营销专家",
        "system_prompt": "你是一位资深的出海营销专家(Global Marketing Specialist)。你精通全球市场营销策略制定、多语言内容创作、社交媒体矩阵运营(TikTok/Facebook/Instagram/LinkedIn/YouTube/小红书)、KOL网红合作管理、广告投放优化(Facebook Ads/Google Ads/TikTok Ads)、市场本地化和竞品分析。你具备浏览器数据采集能力，可以访问网页获取实时市场数据、竞品信息和行业趋势。你的目标客户是中国出海企业(B2B/B2C)，帮助他们在海外市场建立品牌、获取客户、提升ROI。回答时请使用中文，但生成的营销内容请使用目标市场语言。",
    },
]


def generate_agent_entrypoint(agent_def):
    """Generate a dedicated Python file for each agent with S3 skill auto-loading."""
    name = agent_def["name"]
    display = agent_def["display_name"]
    sp = agent_def["system_prompt"]

    skill_names = AGENT_SKILLS.get(name, [])
    # repr() safely embeds the strings
    sp_repr = repr(sp)
    skills_repr = repr(skill_names)

    code = f'''# Agent: {display} — with S3 skill auto-loading
import os
import sys
import time
import json
import logging
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("{name}")

app = BedrockAgentCoreApp()
_agent = None
_s3_client = None
_skills_cache = {{}}  # Cache loaded skills to avoid repeated S3 calls

SKILLS_BUCKET = os.environ.get("SKILLS_BUCKET", "super-agent-files")
SKILLS_PREFIX = os.environ.get("SKILLS_PREFIX", "skills")
BASE_SYSTEM_PROMPT = {sp_repr}
RELEVANT_SKILLS = {skills_repr}


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "{REGION}"))
    return _s3_client


def load_skill_from_s3(skill_name):
    """Load a skill from S3, with in-memory caching."""
    if skill_name in _skills_cache:
        return _skills_cache[skill_name]
    try:
        s3 = get_s3_client()
        key = f"{{SKILLS_PREFIX}}/{{skill_name}}/SKILL.md"
        resp = s3.get_object(Bucket=SKILLS_BUCKET, Key=key)
        content = resp["Body"].read().decode("utf-8")
        # Strip YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        _skills_cache[skill_name] = content
        logger.info(f"Loaded skill '{{skill_name}}' from S3 ({{len(content)}} chars)")
        return content
    except Exception as e:
        logger.error(f"Failed to load skill '{{skill_name}}': {{e}}")
        return None


def build_system_prompt():
    """Build system prompt with skills loaded from S3."""
    prompt = BASE_SYSTEM_PROMPT
    if not RELEVANT_SKILLS:
        return prompt
    skill_sections = []
    for sn in RELEVANT_SKILLS:
        body = load_skill_from_s3(sn)
        if body:
            skill_sections.append(f"<skill name=\\"{{sn}}\\">\\n{{body}}\\n</skill>")
    if skill_sections:
        skills_block = "\\n\\n".join(skill_sections)
        prompt += (
            "\\n\\n你拥有以下专业技能知识，请在回答中充分运用这些知识框架和指标体系：\\n\\n"
            + skills_block
        )
    return prompt


from strands import tool

@tool
def list_skills() -> str:
    """List all available skills from the skills repository.
    Returns a JSON list of skills with name, folder, and description.
    Call this when you need knowledge beyond your pre-loaded skills."""
    try:
        s3 = get_s3_client()
        resp = s3.get_object(Bucket=SKILLS_BUCKET, Key=f"{{SKILLS_PREFIX}}/skills-index.json")
        index = json.loads(resp["Body"].read().decode("utf-8"))
        return json.dumps(index, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to list skills: {{e}}")
        return json.dumps({{"error": str(e)}})


@tool
def load_skill(skill_name: str) -> str:
    """Load additional skill knowledge from S3 on demand.
    Args:
        skill_name: The skill folder name, e.g. 'game-player-retention', 'global-marketing', 'user-behavior-funnel'
    Returns the skill's complete markdown content."""
    content = load_skill_from_s3(skill_name)
    if content:
        return content
    return f"Skill '{{skill_name}}' not found"


SKILL_TOOLS = [list_skills, load_skill]


def build_contextual_prompt(payload):
    user_message = payload.get("prompt", payload.get("message", "Hello"))
    history = payload.get("history", [])
    if not history:
        return user_message
    context_parts = []
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            context_parts.append(f"User: {{content}}")
        else:
            context_parts.append(f"Assistant: {{content}}")
    context = "\\n\\n".join(context_parts)
    return (
        f"Here is our conversation so far:\\n\\n{{context}}\\n\\n"
        f"Now the user says:\\n{{user_message}}\\n\\n"
        f"Please respond based on the full conversation context above."
    )


@app.entrypoint
def invoke(payload):
    global _agent
    logger.info("=== Invocation received ===")
    logger.info(f"Payload keys: {{list(payload.keys())}}")
    if _agent is None:
        logger.info("Cold start — initializing Strands Agent...")
        init_start = time.time()
        from strands import Agent
        from strands.models import BedrockModel
        model = BedrockModel(
            model_id=os.environ.get("MODEL_ID", "{MODEL_ID}"),
            region_name=os.environ.get("AWS_REGION", "{REGION}"),
            max_tokens=4096,
        )
        # Build system prompt with skills from S3
        system_prompt = build_system_prompt()
        logger.info(f"System prompt: {{len(system_prompt)}} chars ({{len(RELEVANT_SKILLS)}} skills loaded)")
        _agent = Agent(model=model, system_prompt=system_prompt, tools=SKILL_TOOLS)
        logger.info(f"Agent initialized in {{time.time() - init_start:.2f}}s")
    else:
        logger.info("Warm start — agent already initialized")
    history = payload.get("history", [])
    full_prompt = build_contextual_prompt(payload)
    logger.info(f"History messages: {{len(history)}}, prompt length: {{len(full_prompt)}}")
    start_time = time.time()
    try:
        result = _agent(full_prompt)
        duration = time.time() - start_time
        result_text = str(result)
        logger.info(f"Response generated in {{duration:.2f}}s ({{len(result_text)}} chars)")
        return {{"result": result_text}}
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Agent error after {{duration:.2f}}s: {{type(e).__name__}}: {{e}}")
        raise

if __name__ == "__main__":
    logger.info("Starting AgentCore runtime...")
    app.run()
'''
    return code


def generate_yaml_config():
    """Generate .bedrock_agentcore.yaml with all agents."""
    agents_config = {}
    for agent_def in AGENTS:
        name = agent_def["name"]
        entrypoint = f"agent_{name}.py"
        agents_config[name] = {
            "name": name,
            "entrypoint": entrypoint,
            "deployment_type": "container",
            "runtime_type": None,
            "platform": "linux/arm64",
            "container_runtime": "none",
            "source_path": SCRIPT_DIR,
            "aws": {
                "execution_role": ROLE_ARN,
                "execution_role_auto_create": False,
                "account": ACCOUNT_ID,
                "region": REGION,
                "ecr_repository": None,
                "ecr_auto_create": True,
                "s3_path": None,
                "s3_auto_create": True,
                "network_configuration": {
                    "network_mode": "PUBLIC",
                    "network_mode_config": None,
                },
                "protocol_configuration": {
                    "server_protocol": "HTTP",
                },
                "observability": {"enabled": True},
                "lifecycle_configuration": {
                    "idle_runtime_session_timeout": None,
                    "max_lifetime": None,
                },
            },
            "bedrock_agentcore": {
                "agent_id": None,
                "agent_arn": None,
                "agent_session_id": None,
            },
            "codebuild": {
                "project_name": None,
                "execution_role": None,
                "source_bucket": None,
            },
            "memory": {
                "mode": "NO_MEMORY",
                "memory_id": None,
                "memory_arn": None,
                "memory_name": f"{name}_memory",
                "event_expiry_days": 30,
                "first_invoke_memory_check_done": False,
                "was_created_by_toolkit": False,
            },
            "identity": {
                "credential_providers": [],
                "workload": None,
            },
            "aws_jwt": {
                "enabled": False,
                "audiences": [],
                "signing_algorithm": "ES384",
                "issuer_url": None,
                "duration_seconds": 300,
            },
            "authorizer_configuration": None,
            "request_header_configuration": None,
            "oauth_configuration": None,
            "api_key_env_var_name": None,
            "api_key_credential_provider_name": None,
            "is_generated_by_agentcore_create": False,
        }

    config = {
        "default_agent": AGENTS[0]["name"],
        "agents": agents_config,
    }
    return config


def write_agent_files():
    """Write individual agent entrypoint files and requirements.txt."""
    for agent_def in AGENTS:
        name = agent_def["name"]
        filepath = os.path.join(SCRIPT_DIR, f"agent_{name}.py")
        code = generate_agent_entrypoint(agent_def)
        with open(filepath, "w") as f:
            f.write(code)
        print(f"  📝 {filepath}")

    # Ensure requirements.txt exists
    req_path = os.path.join(SCRIPT_DIR, "requirements.txt")
    with open(req_path, "w") as f:
        f.write("strands-agents[otel]\nbedrock-agentcore\naws-opentelemetry-distro>=0.10.0\nboto3\n")
    print(f"  📝 {req_path}")


def deploy_agent(name, display_name):
    """Deploy a single agent using agentcore deploy."""
    print(f"\n🚀 Deploying: {display_name} ({name})")

    cmd = [
        "agentcore", "deploy",
        "-a", name,
        "--auto-update-on-conflict",
        "--env", f"MODEL_ID={MODEL_ID}",
        "--env", f"AWS_REGION={REGION}",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )

        # Print output
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-10:]:
                print(f"  [err] {line}")

        if result.returncode == 0:
            print(f"  ✅ Deploy initiated for {name}")
            return True
        else:
            print(f"  ❌ Deploy failed (RC={result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout (600s)")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def check_status():
    """Check status of all deployed runtimes via boto3."""
    import boto3
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    arns = {}
    token = None
    while True:
        kwargs = {}
        if token:
            kwargs["nextToken"] = token
        resp = client.list_agent_runtimes(**kwargs)
        for rt in resp.get("agentRuntimeSummaries", []):
            name = rt.get("agentRuntimeName", "")
            arns[name] = {
                "arn": rt.get("agentRuntimeArn", ""),
                "id": rt.get("agentRuntimeId", ""),
                "status": rt.get("status", "UNKNOWN"),
            }
        token = resp.get("nextToken")
        if not token:
            break

    return arns


def main():
    print("=" * 60)
    print("🚀 AgentCore Cloud Deployment (CodeBuild)")
    print("=" * 60)
    print(f"  Region:  {REGION}")
    print(f"  Account: {ACCOUNT_ID}")
    print(f"  Role:    {ROLE_ARN}")
    print(f"  Model:   {MODEL_ID}")
    print(f"  Agents:  {len(AGENTS)}")

    # Step 1: Generate agent files
    print(f"\n📦 Step 1: Generating agent entrypoint files...")
    write_agent_files()

    # Step 2: Generate YAML config
    print(f"\n📄 Step 2: Generating .bedrock_agentcore.yaml...")
    config = generate_yaml_config()
    yaml_path = os.path.join(SCRIPT_DIR, ".bedrock_agentcore.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    print(f"  📝 {yaml_path}")

    # Step 3: Deploy each agent
    print(f"\n🚀 Step 3: Deploying agents via CodeBuild...")
    results = {}
    for agent_def in AGENTS:
        ok = deploy_agent(agent_def["name"], agent_def["display_name"])
        results[agent_def["name"]] = ok

    # Step 4: Check status
    print(f"\n📋 Step 4: Checking deployment status...")
    time.sleep(5)
    runtimes = check_status()

    print(f"\n{'='*60}")
    print("📋 Deployment Summary")
    print(f"{'='*60}")

    arn_mapping = {}
    for agent_def in AGENTS:
        name = agent_def["name"]
        deploy_ok = results.get(name, False)
        rt = runtimes.get(name, {})
        status = rt.get("status", "NOT_FOUND")
        arn = rt.get("arn", "")

        emoji = "✅" if deploy_ok else "❌"
        status_emoji = {"READY": "🟢", "CREATING": "🟡", "UPDATING": "🟡"}.get(status, "🔴")
        print(f"  {emoji} {agent_def['display_name']:20s} {name:20s} {status_emoji} {status}")

        if arn:
            # Map back to the dash-separated name used in the app
            app_name = name.replace("_", "-")
            arn_mapping[app_name] = arn

    # Save ARN mapping
    if arn_mapping:
        mapping_path = os.path.join(SCRIPT_DIR, "runtime_arns.json")
        with open(mapping_path, "w") as f:
            json.dump(arn_mapping, f, indent=2, ensure_ascii=False)
        print(f"\n💾 ARN mapping saved to {mapping_path}")

    deployed = sum(1 for v in results.values() if v)
    print(f"\n  Deployed: {deployed}/{len(AGENTS)}")

    if deployed < len(AGENTS):
        print("\n⚠️  Some agents failed to deploy. Check errors above.")
        sys.exit(1)
    else:
        print("\n🎉 All agents deployed! Use `agentcore status` to monitor.")


if __name__ == "__main__":
    main()
