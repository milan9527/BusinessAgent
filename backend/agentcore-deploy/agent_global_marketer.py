# Agent: 出海营销专家 — with S3 skill loading + AgentCore Browser + Code Interpreter
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
logger = logging.getLogger("global_marketer")

app = BedrockAgentCoreApp()
_agent = None
_s3_client = None
_skills_cache = {}

SKILLS_BUCKET = os.environ.get("SKILLS_BUCKET", "super-agent-files")
SKILLS_PREFIX = os.environ.get("SKILLS_PREFIX", "skills")
BASE_SYSTEM_PROMPT = (
    '你是一位资深的出海营销专家(Global Marketing Specialist)。'
    '你精通全球市场营销策略制定、多语言内容创作、社交媒体矩阵运营(TikTok/Facebook/Instagram/LinkedIn/YouTube/小红书)、'
    'KOL网红合作管理、广告投放优化(Facebook Ads/Google Ads/TikTok Ads)、市场本地化和竞品分析。'
    '\n\n你具备两种数据采集工具。用户只需用自然语言描述需求，你自主判断使用哪个工具，无需用户指定。'
    '\n\n## 工具自动选择规则（严格遵守）'
    '\n\n### 核心原则：抓取网页内容时，默认使用 browser 工具'
    '\n现代网站绝大多数使用JavaScript框架（React/Vue/Next.js等），requests.get()只能拿到空壳HTML。'
    '\n因此，当用户要求抓取、查看、获取某个网站的内容时，默认使用 browser 工具。'
    '\n\n### → 必须使用 browser 工具的场景'
    '\n- 抓取任何网站首页内容（Product Hunt、Amazon、Shopify、TikTok等）'
    '\n- 页面依赖JavaScript渲染（几乎所有现代网站都是）'
    '\n- 需要交互操作：点击、滚动、登录、填表'
    '\n- 需要截图取证或视觉分析'
    '\n- 社交媒体页面（TikTok/Facebook/Instagram/LinkedIn/YouTube）'
    '\n- 电商平台产品页面（Amazon/Shopee/Lazada）'
    '\n- 竞品官网浏览和分析'
    '\n- 用户说"抓取XX网站"、"看看XX网站"、"获取XX页面"时'
    '\n\n### → 仅在以下场景使用 code_interpreter 工具'
    '\n- 明确已知的纯静态HTML站点（如 Hacker News news.ycombinator.com、Wikipedia）'
    '\n- 调用公开REST API获取JSON数据'
    '\n- 数据清洗、统计分析、生成图表'
    '\n- 处理CSV/JSON/Excel等数据文件'
    '\n- RSS/Atom Feed解析'
    '\n- 对 browser 已采集的数据做二次处理和分析'
    '\n- 用户明确要求"写代码"或"用Python"时'
    '\n\n### 决策示例'
    '\n- "帮我抓取Product Hunt首页热门产品" → browser（SPA网站，必须JS渲染）'
    '\n- "帮我看看竞品官网长什么样" → browser'
    '\n- "抓取Amazon上某产品的评价" → browser（电商平台）'
    '\n- "分析TikTok上这个话题的热门视频" → browser'
    '\n- "帮我抓取Hacker News首页新闻" → code_interpreter（已知纯静态HTML）'
    '\n- "从这个API获取市场数据并做图表" → code_interpreter（API+分析）'
    '\n- "分析刚才抓取的数据，做个对比图表" → code_interpreter（数据处理）'
    '\n- "批量抓取这10个RSS源" → code_interpreter（RSS解析）'
    '\n\n使用 code_interpreter 时，参考 web-crawler 技能中的代码模板，直接复用其中的函数。'
    '\n\n你的目标客户是中国出海企业(B2B/B2C)，帮助他们在海外市场建立品牌、获取客户、提升ROI。'
    '回答时请使用中文，但生成的营销内容请使用目标市场语言。'
)
RELEVANT_SKILLS = ['global-marketing', 'global-marketing-browser', 'web-crawler']

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
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
    Returns a JSON list of skills with name, folder, and description."""
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
        skill_name: The skill folder name, e.g. 'global-marketing', 'global-marketing-browser'
    Returns the skill's complete markdown content."""
    content = load_skill_from_s3(skill_name)
    if content:
        return content
    return f"Skill '{skill_name}' not found"


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
        logger.info("Cold start — initializing Strands Agent with AgentCore Browser...")
        init_start = time.time()
        from strands import Agent
        from strands.models import BedrockModel

        model = BedrockModel(
            model_id=MODEL_ID,
            region_name=AWS_REGION,
            max_tokens=4096,
        )

        # Build system prompt with skills from S3
        system_prompt = build_system_prompt()
        logger.info(f"System prompt: {len(system_prompt)} chars ({len(RELEVANT_SKILLS)} skills loaded)")

        # Initialize AgentCore Browser tool (custom browser with PUBLIC network)
        tools = [list_skills, load_skill]
        try:
            logger.info("Attempting to import AgentCoreBrowser...")
            from strands_tools.browser import AgentCoreBrowser
            logger.info("AgentCoreBrowser imported successfully")
            browser_id = os.environ.get("BROWSER_ID", "public_browser_webauth-piLpCAcEYA")
            browser_tool = AgentCoreBrowser(region=AWS_REGION, identifier=browser_id)
            logger.info(f"AgentCoreBrowser instance created: region={AWS_REGION}, id={browser_id}")
            tools.append(browser_tool.browser)
            logger.info(f"AgentCore Browser tool added to tools list")
        except ImportError as e:
            logger.error(f"AgentCore Browser import failed: {e}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            logger.error(f"AgentCore Browser init failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        # Initialize AgentCore Code Interpreter (custom with PUBLIC network for web crawling)
        try:
            logger.info("Attempting to import AgentCoreCodeInterpreter...")
            from strands_tools.code_interpreter import AgentCoreCodeInterpreter
            logger.info("AgentCoreCodeInterpreter imported successfully")
            ci_id = os.environ.get("CODE_INTERPRETER_ID", "public_code_interpreter-0ycPXzozC4")
            ci_tool = AgentCoreCodeInterpreter(region=AWS_REGION, identifier=ci_id)
            logger.info(f"AgentCoreCodeInterpreter instance created: region={AWS_REGION}, id={ci_id}")
            tools.append(ci_tool.code_interpreter)
            logger.info(f"AgentCore Code Interpreter (PUBLIC network) tool added to tools list")
        except ImportError as e:
            logger.error(f"AgentCore Code Interpreter import failed: {e}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            logger.error(f"AgentCore Code Interpreter init failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        _agent = Agent(model=model, system_prompt=system_prompt, tools=tools)
        logger.info(f"Agent initialized in {time.time() - init_start:.2f}s with {len(tools)} tools")
    else:
        logger.info("Warm start — agent already initialized")

    full_prompt = build_contextual_prompt(payload)
    logger.info(f"Prompt length: {len(full_prompt)}")
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
