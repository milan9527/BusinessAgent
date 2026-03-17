#!/usr/bin/env python3
"""
Comprehensive scenario test for all 8 AgentCore cloud agents.
Tests domain-specific scenarios AND verifies skill knowledge is being used.

Each agent gets multiple test cases:
  - Basic domain test (same as before)
  - Skill-specific test (verifies skill knowledge is injected)
"""
import json
import subprocess
import sys
import time

SCRIPT_DIR = "backend/agentcore-deploy"

# ─── Test Cases ───────────────────────────────────────────────────────────────
# Each test has:
#   agent: runtime name
#   display: display name
#   prompt: what to ask
#   expect_keywords: keywords that should appear in response (case-insensitive)
#   skill_test: True if this tests skill knowledge specifically
#   description: what this test validates

TEST_CASES = [
    # ── player_analyst: basic + skill tests ──
    {
        "agent": "player_analyst",
        "display": "玩家数据分析师",
        "prompt": "我们游戏的7日留存率从45%下降到了32%，DAU也在持续下滑，请帮我分析可能的原因并给出优化建议",
        "expect_keywords": ["留存", "玩家"],
        "skill_test": False,
        "description": "Basic retention analysis",
    },
    {
        "agent": "player_analyst",
        "display": "玩家数据分析师",
        "prompt": "请用LTV公式帮我计算：ARPU是5元，平均生命周期是60天，付费率8%，ARPPU是62.5元。并给出提升LTV的建议",
        "expect_keywords": ["LTV", "ARPU"],
        "skill_test": True,
        "description": "Skill: LTV calculation from game-player-retention",
    },
    {
        "agent": "player_analyst",
        "display": "玩家数据分析师",
        "prompt": "我们的注册到首次付费的漏斗转化率只有2%，请帮我分析每个步骤可能的流失原因，并给出优化建议",
        "expect_keywords": ["漏斗", "转化"],
        "skill_test": True,
        "description": "Skill: funnel analysis from user-behavior-funnel",
    },
    # ── event_planner: basic + skill test ──
    {
        "agent": "event_planner",
        "display": "活动策划助手",
        "prompt": "我们是一款二次元手游，春节期间想做一个限时活动来提升付费率和留存率，请给出一个活动策划方案",
        "expect_keywords": ["活动", "奖励"],
        "skill_test": False,
        "description": "Basic event planning",
    },
    {
        "agent": "event_planner",
        "display": "活动策划助手",
        "prompt": "我们游戏的新手期(Day 0-3)留存率很低，只有25%，请根据留存优化策略设计一个新手引导改进方案",
        "expect_keywords": ["新手", "留存"],
        "skill_test": True,
        "description": "Skill: retention optimization from game-player-retention",
    },
    # ── content_localizer: basic + skill test ──
    {
        "agent": "content_localizer",
        "display": "多语言内容生成器",
        "prompt": "请帮我把以下营销文案翻译成日语并做本地化调整：'限时特惠！首充6元即可获得SSR角色一个，活动仅剩3天！'",
        "expect_keywords": ["日"],
        "skill_test": False,
        "description": "Basic content localization",
    },
    {
        "agent": "content_localizer",
        "display": "多语言内容生成器",
        "prompt": "我们要在小红书上推广一款出海手游，请帮我写一篇种草笔记，要求符合小红书的文案风格，包含emoji和热门标签",
        "expect_keywords": ["小红书", "#"],
        "skill_test": True,
        "description": "Skill: RedNote content template from global-marketing",
    },
    # ── ad_optimizer: basic + skill tests ──
    {
        "agent": "ad_optimizer",
        "display": "广告投放优化师",
        "prompt": "我们在Facebook上投放了一组广告，CPI是$2.5，CTR是1.2%，ROAS是1.8，请分析这组数据并给出优化建议",
        "expect_keywords": ["CPI", "优化"],
        "skill_test": False,
        "description": "Basic ad optimization",
    },
    {
        "agent": "ad_optimizer",
        "display": "广告投放优化师",
        "prompt": "我们准备在东南亚市场投放TikTok广告，月预算5万美元，请帮我制定分阶段投放策略（测试期、放量期、稳定期），并给出预算分配建议",
        "expect_keywords": ["测试", "预算"],
        "skill_test": True,
        "description": "Skill: phased ad strategy from global-marketing",
    },
    {
        "agent": "ad_optimizer",
        "display": "广告投放优化师",
        "prompt": "我们的广告落地页到注册的转化率只有3%，请帮我设计一个A/B测试方案来优化这个漏斗步骤",
        "expect_keywords": ["A/B", "转化"],
        "skill_test": True,
        "description": "Skill: A/B testing from user-behavior-funnel",
    },
    # ── site_generator: basic test ──
    {
        "agent": "site_generator",
        "display": "AI建站助手",
        "prompt": "请帮我生成一个游戏官网落地页，产品是一款二次元RPG手游，需要包含hero区域、游戏特色介绍和下载按钮",
        "expect_keywords": ["html", "<"],
        "skill_test": False,
        "description": "Basic website generation",
    },
    # ── seo_optimizer: basic test ──
    {
        "agent": "seo_optimizer",
        "display": "SEO优化助手",
        "prompt": "我的网站是一个游戏资讯平台，请帮我生成首页的meta标签、title标签和SEO优化建议",
        "expect_keywords": ["meta", "SEO"],
        "skill_test": False,
        "description": "Basic SEO optimization",
    },
    # ── hr_assistant: basic test ──
    {
        "agent": "hr_assistant",
        "display": "HR Assistant",
        "prompt": "We need to hire a senior game backend engineer with experience in distributed systems. Please draft a job description.",
        "expect_keywords": ["engineer", "experience"],
        "skill_test": False,
        "description": "Basic HR job description",
    },
    # ── it_support: basic test ──
    {
        "agent": "it_support",
        "display": "IT Support Agent",
        "prompt": "Our Jenkins CI/CD pipeline keeps failing with 'out of memory' errors during the Docker build step. What should we check?",
        "expect_keywords": ["memory", "Docker"],
        "skill_test": False,
        "description": "Basic IT troubleshooting",
    },
]


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

    # Find JSON response in output
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


def run_test(test_case, index, total):
    """Run a single test case and return results."""
    agent = test_case["agent"]
    display = test_case["display"]
    prompt = test_case["prompt"]
    is_skill = test_case["skill_test"]
    desc = test_case["description"]

    tag = "🔧 SKILL" if is_skill else "📋 BASIC"

    print(f"\n{'─'*70}")
    print(f"  [{index}/{total}] {tag} {display} ({agent})")
    print(f"  📝 {desc}")
    print(f"  💬 {prompt[:80]}...")

    start = time.time()
    try:
        response, error = invoke_agent(agent, prompt)
    except subprocess.TimeoutExpired:
        print(f"  ❌ TIMEOUT (180s)")
        return {"agent": agent, "status": "TIMEOUT", "duration": 180, "skill_test": is_skill, "desc": desc}
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return {"agent": agent, "status": "ERROR", "error": str(e), "skill_test": is_skill, "desc": desc}

    duration = round(time.time() - start, 1)

    if error and not response:
        print(f"  ❌ INVOKE FAILED ({duration}s)")
        print(f"     Error: {error[:200]}")
        return {"agent": agent, "status": "FAIL", "duration": duration, "skill_test": is_skill, "desc": desc}

    if not response or len(str(response)) < 20:
        print(f"  ❌ EMPTY/SHORT RESPONSE ({duration}s)")
        return {"agent": agent, "status": "FAIL", "duration": duration, "skill_test": is_skill, "desc": desc}

    response_str = str(response)
    print(f"  ✅ Response: {len(response_str)} chars in {duration}s")

    # Preview
    preview = response_str[:200].replace("\n", " ")
    print(f"  📄 {preview}...")

    # Check keywords
    found, missing = check_keywords(response_str, test_case["expect_keywords"])
    if missing:
        print(f"  ⚠️  Missing keywords: {missing} (found: {found})")
        keyword_pass = len(found) >= len(test_case["expect_keywords"]) / 2
    else:
        print(f"  ✅ Keywords matched: {found}")
        keyword_pass = True

    status = "PASS" if keyword_pass else "WARN"
    return {
        "agent": agent,
        "display": display,
        "status": status,
        "duration": duration,
        "response_len": len(response_str),
        "keywords_found": len(found),
        "keywords_total": len(test_case["expect_keywords"]),
        "skill_test": is_skill,
        "desc": desc,
    }


def main():
    print("=" * 70)
    print("🚀 AgentCore Comprehensive Scenario Test")
    print("=" * 70)

    total_tests = len(TEST_CASES)
    skill_tests = sum(1 for t in TEST_CASES if t["skill_test"])
    basic_tests = total_tests - skill_tests

    print(f"  Total tests:  {total_tests}")
    print(f"  Basic tests:  {basic_tests}")
    print(f"  Skill tests:  {skill_tests}")
    print(f"  Timestamp:    {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    for i, tc in enumerate(TEST_CASES, 1):
        result = run_test(tc, i, total_tests)
        results.append(result)

    # ── Summary ──
    print(f"\n{'='*70}")
    print("📋 TEST RESULTS SUMMARY")
    print(f"{'='*70}")

    passed = warned = failed = 0
    skill_passed = skill_total = 0

    for r in results:
        status = r["status"]
        is_skill = r.get("skill_test", False)
        desc = r.get("desc", "")
        duration = r.get("duration", "?")
        resp_len = r.get("response_len", 0)
        kw = f"{r.get('keywords_found', 0)}/{r.get('keywords_total', 0)}"

        if is_skill:
            skill_total += 1

        if status == "PASS":
            emoji = "✅"
            passed += 1
            if is_skill:
                skill_passed += 1
        elif status == "WARN":
            emoji = "⚠️ "
            warned += 1
        else:
            emoji = "❌"
            failed += 1

        tag = "[SKILL]" if is_skill else "[BASIC]"
        print(f"  {emoji} {tag:8s} {r.get('agent', ''):22s} {status:7s} {duration:>6}s  {resp_len:>5}ch  kw:{kw}  {desc}")

    print(f"\n{'─'*70}")
    print(f"  Total: {total_tests}  |  ✅ Pass: {passed}  |  ⚠️  Warn: {warned}  |  ❌ Fail: {failed}")
    print(f"  Skill tests: {skill_passed}/{skill_total} passed")
    print(f"{'─'*70}")

    if failed == 0 and skill_passed == skill_total:
        print(f"\n🎉 All {total_tests} tests passed! Skills are being used correctly.")
    elif failed == 0:
        print(f"\n⚠️  All agents responded, but {skill_total - skill_passed} skill test(s) had keyword warnings.")
    else:
        print(f"\n❌ {failed} test(s) failed. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
