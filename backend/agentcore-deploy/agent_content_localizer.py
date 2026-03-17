# Agent: 多语言内容生成器 — with S3 skill auto-loading
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
logger = logging.getLogger("content_localizer")

app = BedrockAgentCoreApp()
_agent = None
_s3_client = None
_skills_cache = {}  # Cache loaded skills to avoid repeated S3 calls

SKILLS_BUCKET = os.environ.get("SKILLS_BUCKET", "super-agent-files")
SKILLS_PREFIX = os.environ.get("SKILLS_PREFIX", "skills")
BASE_SYSTEM_PROMPT = '你是一位出海营销内容专家。你精通多语言内容创作和本地化，了解不同市场的文化差异和用户偏好。支持英语、日语、韩语、东南亚语言等。回答时请使用中文，但生成的营销内容请使用目标语言。'
RELEVANT_SKILLS = ['global-marketing']


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _s3_client


def load_skill_from_s3(skill_name):
    """Load a skill from S3, with in-memory caching."""
    if skill_name in _skills_cache:
        return _skills_cache[skill_name]
    try:
        s3 = get_s3_client()
        key = f"{SKILLS_PREFIX}/{skill_name}/SKILL.md"
        resp = s3.get_object(Bucket=SKILLS_BUCKET, Key=key)
        content = resp["Body"].read().decode("utf-8")
        # Strip YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        _skills_cache[skill_name] = content
        logger.info(f"Loaded skill '{skill_name}' from S3 ({len(content)} chars)")
        return content
    except Exception as e:
        logger.error(f"Failed to load skill '{skill_name}': {e}")
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
            skill_sections.append(f"<skill name=\"{sn}\">\n{body}\n</skill>")
    if skill_sections:
        skills_block = "\n\n".join(skill_sections)
        prompt += (
            "\n\n你拥有以下专业技能知识，请在回答中充分运用这些知识框架和指标体系：\n\n"
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
        resp = s3.get_object(Bucket=SKILLS_BUCKET, Key=f"{SKILLS_PREFIX}/skills-index.json")
        index = json.loads(resp["Body"].read().decode("utf-8"))
        return json.dumps(index, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to list skills: {e}")
        return json.dumps({"error": str(e)})


@tool
def load_skill(skill_name: str) -> str:
    """Load additional skill knowledge from S3 on demand.
    Args:
        skill_name: The skill folder name, e.g. 'game-player-retention', 'global-marketing', 'user-behavior-funnel'
    Returns the skill's complete markdown content."""
    content = load_skill_from_s3(skill_name)
    if content:
        return content
    return f"Skill '{skill_name}' not found"


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
            context_parts.append(f"User: {content}")
        else:
            context_parts.append(f"Assistant: {content}")
    context = "\n\n".join(context_parts)
    return (
        f"Here is our conversation so far:\n\n{context}\n\n"
        f"Now the user says:\n{user_message}\n\n"
        f"Please respond based on the full conversation context above."
    )


@app.entrypoint
def invoke(payload):
    global _agent
    logger.info("=== Invocation received ===")
    logger.info(f"Payload keys: {list(payload.keys())}")
    if _agent is None:
        logger.info("Cold start — initializing Strands Agent...")
        init_start = time.time()
        from strands import Agent
        from strands.models import BedrockModel
        model = BedrockModel(
            model_id=os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            max_tokens=4096,
        )
        # Build system prompt with skills from S3
        system_prompt = build_system_prompt()
        logger.info(f"System prompt: {len(system_prompt)} chars ({len(RELEVANT_SKILLS)} skills loaded)")
        _agent = Agent(model=model, system_prompt=system_prompt, tools=SKILL_TOOLS)
        logger.info(f"Agent initialized in {time.time() - init_start:.2f}s")
    else:
        logger.info("Warm start — agent already initialized")
    history = payload.get("history", [])
    full_prompt = build_contextual_prompt(payload)
    logger.info(f"History messages: {len(history)}, prompt length: {len(full_prompt)}")
    start_time = time.time()
    try:
        result = _agent(full_prompt)
        duration = time.time() - start_time
        result_text = str(result)
        logger.info(f"Response generated in {duration:.2f}s ({len(result_text)} chars)")
        return {"result": result_text}
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Agent error after {duration:.2f}s: {type(e).__name__}: {e}")
        raise

if __name__ == "__main__":
    logger.info("Starting AgentCore runtime...")
    app.run()
