#!/usr/bin/env python3
"""
Global Marketer Business Scenario Tests

Tests the global_marketer agent with realistic business cases that exercise:
  1. Browser tool (web scraping, competitor analysis)
  2. Code Interpreter tool (data analysis, API calls)
  3. Marketing domain knowledge (strategy, content, ads)
  4. Cross-agent collaboration scenarios (tasks that would involve other agents)

Each scenario simulates a real business workflow for a Chinese company going global.

Usage:
  python test_global_marketer_scenarios.py              # Run all tests
  python test_global_marketer_scenarios.py --quick       # Run quick tests only (no browser)
  python test_global_marketer_scenarios.py --browser     # Run browser tests only
  python test_global_marketer_scenarios.py --scenario N  # Run specific scenario (1-based)
"""
import json
import subprocess
import sys
import time
import argparse

SCRIPT_DIR = "backend/agentcore-deploy"

# ─── Business Context ─────────────────────────────────────────────────────────
# Fictional company: "星辰科技 (StarTech)" — a Chinese DTC brand selling smart
# home devices, expanding to US, Japan, and Southeast Asia markets.
# ──────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 1: Browser Tool — Web Scraping & Competitor Analysis
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "B1",
        "category": "browser",
        "agent": "global_marketer",
        "title": "Product Hunt 竞品发现",
        "prompt": (
            "我们公司星辰科技准备在Product Hunt上发布一款智能家居控制器。"
            "请帮我抓取Product Hunt首页，看看今天有哪些热门产品，"
            "分析它们的标语和定位策略，给我们的产品发布提供参考建议。"
        ),
        "expect_keywords": ["Product Hunt", "产品"],
        "timeout": 180,
        "tool_expected": "browser",
        "description": "Browser: scrape Product Hunt for competitive intelligence",
    },
    {
        "id": "B2",
        "category": "browser",
        "agent": "global_marketer",
        "title": "Amazon 竞品价格监控",
        "prompt": (
            "请帮我用browser工具打开Amazon.com，搜索'smart home hub'，"
            "抓取前5个搜索结果的产品名称、价格和评分，"
            "然后分析我们的定价策略应该如何制定（我们的成本价是$25）。"
        ),
        "expect_keywords": ["Amazon", "价格"],
        "timeout": 180,
        "tool_expected": "browser",
        "description": "Browser: Amazon competitor price monitoring",
    },
    {
        "id": "B3",
        "category": "browser",
        "agent": "global_marketer",
        "title": "TikTok 热门话题调研",
        "prompt": (
            "我们要在TikTok上推广智能家居产品。"
            "请帮我用browser打开TikTok.com，看看#smarthome相关的热门内容趋势，"
            "给出我们应该制作什么类型的短视频内容建议。"
        ),
        "expect_keywords": ["TikTok", "内容"],
        "timeout": 180,
        "tool_expected": "browser",
        "description": "Browser: TikTok trend research for content strategy",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 2: Code Interpreter — Data Analysis & API
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "C1",
        "category": "code_interpreter",
        "agent": "global_marketer",
        "title": "广告ROI数据分析",
        "prompt": (
            "请用code_interpreter帮我分析以下广告投放数据，计算各渠道的ROI和CPA，"
            "并给出预算优化建议：\n"
            "- Facebook Ads: 花费$5000, 点击12000, 转化180, 收入$12000\n"
            "- Google Ads: 花费$3000, 点击8000, 转化95, 收入$7500\n"
            "- TikTok Ads: 花费$2000, 点击15000, 转化120, 收入$6000\n"
            "请计算每个渠道的CTR、CVR、CPA、ROAS，并用表格展示。"
        ),
        "expect_keywords": ["ROI", "ROAS"],
        "timeout": 120,
        "tool_expected": "code_interpreter",
        "description": "Code Interpreter: ad spend ROI analysis with calculations",
    },
    {
        "id": "C2",
        "category": "code_interpreter",
        "agent": "global_marketer",
        "title": "Hacker News 科技趋势抓取",
        "prompt": (
            "请用code_interpreter抓取Hacker News首页(https://news.ycombinator.com)的"
            "前10条新闻标题和链接，分析当前科技圈关注的热点话题，"
            "看看有没有和智能家居相关的讨论。"
        ),
        "expect_keywords": ["Hacker News", "新闻"],
        "timeout": 120,
        "tool_expected": "code_interpreter",
        "description": "Code Interpreter: scrape static HN + trend analysis",
    },
    {
        "id": "C3",
        "category": "code_interpreter",
        "agent": "global_marketer",
        "title": "市场规模估算模型",
        "prompt": (
            "请用Python帮我建立一个简单的TAM/SAM/SOM市场规模估算模型：\n"
            "- 全球智能家居市场规模: $1200亿 (TAM)\n"
            "- 智能家居控制器细分: 占比15%\n"
            "- 我们目标市场(美国+日本+东南亚): 占全球45%\n"
            "- 我们第一年可触达的市场份额: 0.1%\n"
            "请计算TAM/SAM/SOM并给出分析。"
        ),
        "expect_keywords": ["TAM", "SAM", "SOM"],
        "timeout": 120,
        "tool_expected": "code_interpreter",
        "description": "Code Interpreter: TAM/SAM/SOM market sizing model",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 3: Marketing Strategy (no tool, pure knowledge)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "S1",
        "category": "strategy",
        "agent": "global_marketer",
        "title": "出海GTM策略制定",
        "prompt": (
            "星辰科技是一家深圳的智能家居公司，核心产品是一款售价$49的智能家居中控器，"
            "支持Matter协议，兼容Alexa/Google Home/HomeKit。"
            "我们计划2026年Q2进入美国市场。请帮我制定一个完整的Go-To-Market策略，"
            "包括：目标用户画像、渠道策略、定价策略、营销节奏和KPI指标。"
        ),
        "expect_keywords": ["用户", "渠道", "策略"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Strategy: full GTM plan for US market entry",
    },
    {
        "id": "S2",
        "category": "strategy",
        "agent": "global_marketer",
        "title": "KOL合作方案设计",
        "prompt": (
            "我们预算$20,000做一轮KOL营销推广智能家居控制器，目标市场是美国。"
            "请帮我设计KOL合作方案：\n"
            "1. 应该选择什么类型和量级的KOL？\n"
            "2. 合作形式建议（开箱、评测、植入等）\n"
            "3. 预算分配方案\n"
            "4. 效果评估指标"
        ),
        "expect_keywords": ["KOL", "预算"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Strategy: KOL collaboration plan with budget allocation",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 4: Cross-Agent Collaboration Scenarios
    # These test prompts that touch domains of OTHER agents, verifying the
    # global_marketer can handle or appropriately address them.
    # ══════════════════════════════════════════════════════════════════════════

    # → Overlaps with content_localizer (多语言内容生成器)
    {
        "id": "X1",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "多语言营销文案 (×content_localizer)",
        "prompt": (
            "我们的智能家居控制器要同时在美国、日本和泰国上市。"
            "请帮我为每个市场写一段产品发布的社交媒体文案（Facebook/Twitter），"
            "要求：美国用英语、日本用日语、泰国用泰语，"
            "每段文案要符合当地文化习惯和社交媒体风格。"
        ),
        "expect_keywords": ["英", "日"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: multilingual content (content_localizer domain)",
    },
    # → Overlaps with ad_optimizer (广告投放优化师)
    {
        "id": "X2",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "Facebook广告投放策略 (×ad_optimizer)",
        "prompt": (
            "我们准备在Facebook上投放智能家居控制器的广告，月预算$10,000。"
            "目标市场是美国25-45岁的科技爱好者和智能家居用户。"
            "请帮我制定：\n"
            "1. 受众定向策略（兴趣、行为、Lookalike）\n"
            "2. 广告创意方向（图片/视频/轮播）\n"
            "3. 分阶段预算分配（测试期→放量期→稳定期）\n"
            "4. 关键优化指标和目标值"
        ),
        "expect_keywords": ["Facebook", "受众", "预算"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: ad strategy (ad_optimizer domain)",
    },
    # → Overlaps with seo_optimizer (SEO优化助手)
    {
        "id": "X3",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "产品官网SEO优化 (×seo_optimizer)",
        "prompt": (
            "我们的产品官网 startech-home.com 刚上线，"
            "请帮我制定SEO优化方案：\n"
            "1. 核心关键词和长尾关键词建议\n"
            "2. 首页meta标签和title建议\n"
            "3. 内容营销策略（博客主题建议）\n"
            "4. 外链建设策略"
        ),
        "expect_keywords": ["SEO", "关键词"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: SEO strategy (seo_optimizer domain)",
    },
    # → Overlaps with site_generator (AI建站助手)
    {
        "id": "X4",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "落地页转化优化 (×site_generator)",
        "prompt": (
            "我们的广告落地页转化率只有1.5%，行业平均是3-5%。"
            "请从营销角度分析落地页应该包含哪些关键元素来提升转化率，"
            "给出一个高转化落地页的结构建议，包括：\n"
            "- Hero区域的文案和CTA设计\n"
            "- 社会证明（评价、媒体报道）的展示方式\n"
            "- 价格展示和促销策略\n"
            "- 信任标识（安全认证、退款保证等）"
        ),
        "expect_keywords": ["转化", "CTA"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: landing page optimization (site_generator domain)",
    },
    # → Overlaps with event_planner (活动策划助手)
    {
        "id": "X5",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "线上发布会策划 (×event_planner)",
        "prompt": (
            "星辰科技要在美国举办一场线上产品发布会，发布新款智能家居控制器。"
            "请帮我策划这场发布会的营销推广方案：\n"
            "1. 发布会前的预热营销（社交媒体、邮件、PR）\n"
            "2. 发布会当天的直播推广策略\n"
            "3. 发布会后的持续传播计划\n"
            "4. 媒体和KOL邀请策略"
        ),
        "expect_keywords": ["发布", "营销"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: launch event marketing (event_planner domain)",
    },
    # → Overlaps with player_analyst (玩家数据分析师) — data-driven marketing
    {
        "id": "X6",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "用户留存与复购策略 (×player_analyst)",
        "prompt": (
            "我们的智能家居产品用户数据如下：\n"
            "- 30日留存率: 65%\n"
            "- 90日留存率: 40%\n"
            "- 复购率(配件): 12%\n"
            "- NPS评分: 42\n"
            "请从营销角度分析如何提升用户留存和复购率，"
            "设计一套用户生命周期营销方案（激活→留存→复购→推荐）。"
        ),
        "expect_keywords": ["留存", "复购"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: retention marketing (player_analyst domain)",
    },
    # → Overlaps with hr_assistant — employer branding
    {
        "id": "X7",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "雇主品牌海外传播 (×hr_assistant)",
        "prompt": (
            "星辰科技要在美国招聘10名工程师，需要建立海外雇主品牌。"
            "请从营销角度帮我制定雇主品牌传播方案：\n"
            "1. LinkedIn公司页面内容策略\n"
            "2. 技术博客和开源项目推广\n"
            "3. Glassdoor评价管理\n"
            "4. 校园招聘营销活动"
        ),
        "expect_keywords": ["LinkedIn", "品牌"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: employer branding (hr_assistant domain)",
    },
    # → Overlaps with it_support — marketing tech stack
    {
        "id": "X8",
        "category": "cross_agent",
        "agent": "global_marketer",
        "title": "营销技术栈选型 (×it_support)",
        "prompt": (
            "我们需要搭建出海营销的技术栈(MarTech Stack)，预算有限。"
            "请推荐适合中小型出海企业的营销工具组合：\n"
            "1. CRM系统\n"
            "2. 邮件营销工具\n"
            "3. 社交媒体管理工具\n"
            "4. 数据分析工具\n"
            "5. 广告管理平台\n"
            "请给出每个类别的推荐工具、价格区间和选型建议。"
        ),
        "expect_keywords": ["CRM", "工具"],
        "timeout": 60,
        "tool_expected": None,
        "description": "Cross-agent: MarTech stack (it_support domain)",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # CATEGORY 5: End-to-End Business Workflow (complex, multi-step)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "E1",
        "category": "e2e",
        "agent": "global_marketer",
        "title": "完整出海营销方案",
        "prompt": (
            "星辰科技是一家深圳智能家居公司，核心产品是$49的智能中控器(支持Matter/Alexa/Google Home)。"
            "我们2026年Q2要进入美国市场，总营销预算$100,000。\n\n"
            "请帮我制定一个完整的出海营销方案，包括：\n"
            "1. 市场分析：美国智能家居市场现状和竞争格局\n"
            "2. 目标用户：用户画像和购买决策路径\n"
            "3. 品牌定位：差异化定位和品牌故事\n"
            "4. 渠道策略：线上(Amazon/DTC官网)和社交媒体矩阵\n"
            "5. 内容策略：各平台内容规划\n"
            "6. 广告策略：Facebook/Google/TikTok投放计划\n"
            "7. PR策略：媒体关系和Product Hunt发布\n"
            "8. 预算分配：$100K的详细分配方案\n"
            "9. 时间线：Q2三个月的执行节奏\n"
            "10. KPI：关键指标和目标值"
        ),
        "expect_keywords": ["市场", "用户", "品牌", "渠道", "预算"],
        "timeout": 90,
        "tool_expected": None,
        "description": "E2E: comprehensive go-to-market plan ($100K budget)",
    },
    {
        "id": "E2",
        "category": "e2e",
        "agent": "global_marketer",
        "title": "竞品深度分析报告 (Browser+分析)",
        "prompt": (
            "请帮我做一份智能家居控制器的竞品分析报告。"
            "先用browser工具访问以下竞品官网收集信息：\n"
            "1. https://www.home-assistant.io (Home Assistant)\n"
            "2. https://www.hubitat.com (Hubitat)\n\n"
            "然后分析：\n"
            "- 各竞品的产品定位和目标用户\n"
            "- 定价策略对比\n"
            "- 营销渠道和内容策略\n"
            "- 我们的差异化机会点\n"
            "- SWOT分析"
        ),
        "expect_keywords": ["竞品", "分析"],
        "timeout": 180,
        "tool_expected": "browser",
        "description": "E2E: competitor deep-dive with browser + analysis",
    },
]


# ─── Test Runner ──────────────────────────────────────────────────────────────

def invoke_agent(agent_name, prompt, timeout=180):
    """Invoke an agent via agentcore CLI and return the response text."""
    payload = json.dumps({"prompt": prompt})
    result = subprocess.run(
        ["agentcore", "invoke", payload, "-a", agent_name],
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = result.stdout

    response_text = ""
    in_response = False
    for line in stdout.split("\n"):
        if "Response:" in line:
            in_response = True
            continue
        if in_response:
            response_text += line + "\n"

    response_text = response_text.strip()
    if not response_text:
        for line in stdout.split("\n"):
            line = line.strip()
            if line.startswith("{") and "result" in line:
                response_text = line
                break

    if not response_text:
        return None, result.stderr or result.stdout

    try:
        data = json.loads(response_text)
        return data.get("result", ""), None
    except json.JSONDecodeError:
        try:
            combined = response_text.replace("\n", "")
            data = json.loads(combined)
            return data.get("result", ""), None
        except Exception:
            return response_text, None


def check_keywords(text, keywords):
    """Check if response contains expected keywords (case-insensitive)."""
    text_lower = text.lower()
    found = [kw for kw in keywords if kw.lower() in text_lower]
    missing = [kw for kw in keywords if kw.lower() not in text_lower]
    return found, missing


def run_test(scenario, index, total):
    """Run a single scenario and return results."""
    sid = scenario["id"]
    title = scenario["title"]
    agent = scenario["agent"]
    prompt = scenario["prompt"]
    timeout = scenario.get("timeout", 120)
    tool = scenario.get("tool_expected")
    desc = scenario["description"]
    category = scenario["category"]

    cat_emoji = {
        "browser": "🌐",
        "code_interpreter": "🐍",
        "strategy": "📋",
        "cross_agent": "🔗",
        "e2e": "🚀",
    }.get(category, "📋")

    tool_tag = f" [{tool}]" if tool else ""

    print(f"\n{'─'*72}")
    print(f"  [{index}/{total}] {cat_emoji} {sid}: {title}{tool_tag}")
    print(f"  📝 {desc}")
    print(f"  💬 {prompt[:90]}...")

    start = time.time()
    try:
        response, error = invoke_agent(agent, prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        duration = round(time.time() - start, 1)
        print(f"  ❌ TIMEOUT ({timeout}s)")
        return {
            "id": sid, "title": title, "category": category,
            "status": "TIMEOUT", "duration": duration, "tool": tool,
        }
    except Exception as e:
        duration = round(time.time() - start, 1)
        print(f"  ❌ ERROR: {e}")
        return {
            "id": sid, "title": title, "category": category,
            "status": "ERROR", "duration": duration, "error": str(e), "tool": tool,
        }

    duration = round(time.time() - start, 1)

    if error and not response:
        print(f"  ❌ INVOKE FAILED ({duration}s)")
        print(f"     Error: {error[:200]}")
        return {
            "id": sid, "title": title, "category": category,
            "status": "FAIL", "duration": duration, "tool": tool,
        }

    if not response or len(str(response)) < 30:
        print(f"  ❌ EMPTY/SHORT RESPONSE ({duration}s): {response}")
        return {
            "id": sid, "title": title, "category": category,
            "status": "FAIL", "duration": duration, "tool": tool,
        }

    response_str = str(response)
    print(f"  ✅ Response: {len(response_str)} chars in {duration}s")

    # Preview
    preview = response_str[:250].replace("\n", " ")
    print(f"  📄 {preview}...")

    # Check keywords
    found, missing = check_keywords(response_str, scenario["expect_keywords"])
    if missing:
        print(f"  ⚠️  Missing keywords: {missing} (found: {found})")
        keyword_pass = len(found) >= len(scenario["expect_keywords"]) / 2
    else:
        print(f"  ✅ Keywords matched: {found}")
        keyword_pass = True

    status = "PASS" if keyword_pass else "WARN"
    return {
        "id": sid,
        "title": title,
        "category": category,
        "status": status,
        "duration": duration,
        "response_len": len(response_str),
        "keywords_found": len(found),
        "keywords_total": len(scenario["expect_keywords"]),
        "tool": tool,
    }


def main():
    parser = argparse.ArgumentParser(description="Global Marketer Business Scenario Tests")
    parser.add_argument("--quick", action="store_true", help="Skip browser tests (faster)")
    parser.add_argument("--browser", action="store_true", help="Run browser tests only")
    parser.add_argument("--strategy", action="store_true", help="Run strategy tests only")
    parser.add_argument("--cross", action="store_true", help="Run cross-agent tests only")
    parser.add_argument("--e2e", action="store_true", help="Run end-to-end tests only")
    parser.add_argument("--scenario", type=int, help="Run specific scenario (1-based index)")
    args = parser.parse_args()

    # Filter scenarios
    if args.scenario:
        idx = args.scenario - 1
        if idx < 0 or idx >= len(SCENARIOS):
            print(f"❌ Scenario {args.scenario} not found (valid: 1-{len(SCENARIOS)})")
            sys.exit(1)
        test_scenarios = [SCENARIOS[idx]]
    elif args.browser:
        test_scenarios = [s for s in SCENARIOS if s["category"] == "browser"]
    elif args.strategy:
        test_scenarios = [s for s in SCENARIOS if s["category"] == "strategy"]
    elif args.cross:
        test_scenarios = [s for s in SCENARIOS if s["category"] == "cross_agent"]
    elif args.e2e:
        test_scenarios = [s for s in SCENARIOS if s["category"] == "e2e"]
    elif args.quick:
        test_scenarios = [s for s in SCENARIOS if s["category"] != "browser"]
    else:
        test_scenarios = SCENARIOS

    # Count by category
    cats = {}
    for s in test_scenarios:
        cats[s["category"]] = cats.get(s["category"], 0) + 1

    print("=" * 72)
    print("🌍 Global Marketer — Business Scenario Tests")
    print("=" * 72)
    print(f"  Company:    星辰科技 (StarTech) — Smart Home DTC Brand")
    print(f"  Agent:      global_marketer (出海营销专家)")
    print(f"  Scenarios:  {len(test_scenarios)}")
    for cat, count in sorted(cats.items()):
        emoji = {"browser": "🌐", "code_interpreter": "🐍", "strategy": "📋",
                 "cross_agent": "🔗", "e2e": "🚀"}.get(cat, "📋")
        print(f"    {emoji} {cat}: {count}")
    print(f"  Timestamp:  {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    for i, scenario in enumerate(test_scenarios, 1):
        result = run_test(scenario, i, len(test_scenarios))
        results.append(result)

    # ── Summary ──
    print(f"\n{'='*72}")
    print("📊 TEST RESULTS SUMMARY")
    print(f"{'='*72}")

    passed = warned = failed = 0
    total_duration = 0

    for r in results:
        status = r["status"]
        sid = r["id"]
        title = r["title"]
        cat = r["category"]
        duration = r.get("duration", 0)
        resp_len = r.get("response_len", 0)
        kw = f"{r.get('keywords_found', 0)}/{r.get('keywords_total', 0)}"
        tool = r.get("tool") or "-"
        total_duration += duration

        if status == "PASS":
            emoji = "✅"
            passed += 1
        elif status == "WARN":
            emoji = "⚠️ "
            warned += 1
        else:
            emoji = "❌"
            failed += 1

        print(f"  {emoji} {sid:4s} {status:7s} {duration:>6.1f}s  {resp_len:>5}ch  kw:{kw:5s}  tool:{tool:18s}  {title}")

    print(f"\n{'─'*72}")
    print(f"  Total: {len(results)}  |  ✅ Pass: {passed}  |  ⚠️  Warn: {warned}  |  ❌ Fail: {failed}")
    print(f"  Total time: {total_duration:.0f}s ({total_duration/60:.1f}min)")
    print(f"{'─'*72}")

    if failed == 0:
        print(f"\n🎉 All {len(results)} scenarios passed!")
    else:
        print(f"\n❌ {failed} scenario(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
