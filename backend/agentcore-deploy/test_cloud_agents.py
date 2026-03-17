#!/usr/bin/env python3
"""
End-to-end test for all 9 AgentCore cloud-deployed agents.
Each agent gets a domain-specific test case to verify it responds in-character.
"""
import json
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TEST_CASES = [
    {
        "agent": "player_analyst",
        "display": "玩家数据分析师",
        "prompt": "我们游戏的7日留存率从45%下降到了32%，DAU也在持续下滑，请帮我分析可能的原因并给出优化建议",
        "expect_keywords": ["留存", "玩家", "数据", "分析"],
        "expect_lang": "zh",
    },
    {
        "agent": "event_planner",
        "display": "活动策划助手",
        "prompt": "我们是一款二次元手游，春节期间想做一个限时活动来提升付费率，请给出一个活动策划方案",
        "expect_keywords": ["活动", "奖励", "玩家"],
        "expect_lang": "zh",
    },
    {
        "agent": "content_localizer",
        "display": "多语言内容生成器",
        "prompt": "请帮我把以下营销文案翻译成日语并做本地化调整：'限时特惠！首充6元即可获得SSR角色一个，活动仅剩3天！'",
        "expect_keywords": ["日", "本"],
        "expect_lang": "mixed",
    },
    {
        "agent": "ad_optimizer",
        "display": "广告投放优化师",
        "prompt": "我们在Facebook上投放了一组广告，CPI是$2.5，CTR是1.2%，ROAS是1.8，请分析这组数据并给出优化建议",
        "expect_keywords": ["广告", "优化", "CPI", "CTR"],
        "expect_lang": "zh",
    },
    {
        "agent": "site_generator",
        "display": "AI建站助手",
        "prompt": "请帮我生成一个简单的产品落地页，产品是一个AI写作助手，需要包含hero区域、功能介绍和CTA按钮，只需要给出HTML代码",
        "expect_keywords": ["html", "<", ">", "div"],
        "expect_lang": "zh",
    },
    {
        "agent": "seo_optimizer",
        "display": "SEO优化助手",
        "prompt": "我的网站 example.com 是一个在线教育平台，请帮我生成首页的meta标签和SEO优化建议",
        "expect_keywords": ["meta", "SEO", "关键词"],
        "expect_lang": "zh",
    },
    {
        "agent": "hr_assistant",
        "display": "HR Assistant",
        "prompt": "We need to hire a senior backend engineer. Please draft a job description including requirements, responsibilities, and benefits.",
        "expect_keywords": ["engineer", "experience", "responsibilities"],
        "expect_lang": "en",
    },
    {
        "agent": "it_support",
        "display": "IT Support Agent",
        "prompt": "My laptop keeps showing a blue screen error (BSOD) with the code IRQL_NOT_LESS_OR_EQUAL after the latest Windows update. What should I do?",
        "expect_keywords": ["driver", "update", "restart"],
        "expect_lang": "en",
    },
    {
        "agent": "global_marketer",
        "display": "出海营销专家",
        "prompt": "我们是一家中国跨境电商公司，主要卖智能家居产品，想在北美市场做社交媒体营销，请给出TikTok和Facebook的营销策略建议",
        "expect_keywords": ["TikTok", "Facebook", "营销", "内容"],
        "expect_lang": "zh",
    },
]


def invoke_agent(agent_name, prompt, timeout=180):
    """Invoke an agent via agentcore CLI and return the parsed response."""
    payload = json.dumps({"prompt": prompt})
    result = subprocess.run(
        ["agentcore", "invoke", payload, "-a", agent_name],
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    # Extract JSON response from output (last lines after "Response:")
    stdout = result.stdout
    # Find the JSON response in the output
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
        # Try to find JSON anywhere in output
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
        # Might be multi-line JSON
        try:
            # Combine all lines after Response:
            combined = response_text.replace("\n", "")
            data = json.loads(combined)
            return data.get("result", ""), None
        except Exception:
            return response_text, None


def check_keywords(text, keywords):
    """Check if response contains expected keywords (case-insensitive)."""
    text_lower = text.lower()
    found = []
    missing = []
    for kw in keywords:
        if kw.lower() in text_lower:
            found.append(kw)
        else:
            missing.append(kw)
    return found, missing


def run_test(test_case):
    """Run a single test case and return results."""
    agent = test_case["agent"]
    display = test_case["display"]
    prompt = test_case["prompt"]

    print(f"\n{'='*70}")
    print(f"🧪 {display} ({agent})")
    print(f"{'='*70}")
    print(f"  📝 Prompt: {prompt[:80]}...")

    start = time.time()
    try:
        response, error = invoke_agent(agent, prompt)
    except subprocess.TimeoutExpired:
        print(f"  ❌ TIMEOUT (180s)")
        return {"agent": agent, "status": "TIMEOUT", "duration": 180}
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return {"agent": agent, "status": "ERROR", "error": str(e)}

    duration = round(time.time() - start, 1)

    if error and not response:
        print(f"  ❌ INVOKE FAILED ({duration}s)")
        print(f"     Error: {error[:200]}")
        return {"agent": agent, "status": "FAIL", "duration": duration, "error": error[:200]}

    if not response or len(str(response)) < 20:
        print(f"  ❌ EMPTY/SHORT RESPONSE ({duration}s)")
        print(f"     Got: {response}")
        return {"agent": agent, "status": "FAIL", "duration": duration, "error": "Response too short"}

    response_str = str(response)
    print(f"  ✅ Response received ({len(response_str)} chars, {duration}s)")

    # Show preview
    preview = response_str[:200].replace("\n", " ")
    print(f"  📄 Preview: {preview}...")

    # Check keywords
    found, missing = check_keywords(response_str, test_case["expect_keywords"])
    if missing:
        print(f"  ⚠️  Missing keywords: {missing} (found: {found})")
        keyword_pass = len(found) >= len(test_case["expect_keywords"]) / 2
    else:
        print(f"  ✅ All keywords found: {found}")
        keyword_pass = True

    # Check language
    lang = test_case["expect_lang"]
    if lang == "zh":
        has_chinese = any("\u4e00" <= c <= "\u9fff" for c in response_str)
        if has_chinese:
            print(f"  ✅ Chinese response confirmed")
        else:
            print(f"  ⚠️  Expected Chinese but got non-Chinese response")
    elif lang == "en":
        has_ascii = any(c.isascii() and c.isalpha() for c in response_str)
        if has_ascii:
            print(f"  ✅ English response confirmed")
        else:
            print(f"  ⚠️  Expected English response")

    status = "PASS" if keyword_pass else "WARN"
    return {
        "agent": agent,
        "display": display,
        "status": status,
        "duration": duration,
        "response_len": len(response_str),
        "keywords_found": len(found),
        "keywords_total": len(test_case["expect_keywords"]),
    }


def main():
    print("🚀 AgentCore Cloud Agent Test Suite")
    print(f"   Testing {len(TEST_CASES)} agents with domain-specific prompts")
    print(f"   Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    for tc in TEST_CASES:
        result = run_test(tc)
        results.append(result)

    # Summary
    print(f"\n{'='*70}")
    print("📋 TEST RESULTS SUMMARY")
    print(f"{'='*70}")

    passed = 0
    warned = 0
    failed = 0

    for r in results:
        status = r["status"]
        agent = r["agent"]
        display = r.get("display", agent)
        duration = r.get("duration", "?")
        resp_len = r.get("response_len", 0)
        kw = f"{r.get('keywords_found', 0)}/{r.get('keywords_total', 0)}"

        if status == "PASS":
            emoji = "✅"
            passed += 1
        elif status == "WARN":
            emoji = "⚠️ "
            warned += 1
        else:
            emoji = "❌"
            failed += 1

        print(f"  {emoji} {display:20s} {agent:22s} {status:7s} {duration:>6}s  {resp_len:>5} chars  keywords: {kw}")

    total = len(results)
    print(f"\n  Total: {total}  |  ✅ Passed: {passed}  |  ⚠️  Warned: {warned}  |  ❌ Failed: {failed}")

    if failed == 0:
        print(f"\n🎉 All {total} agents are operational!")
    else:
        print(f"\n⚠️  {failed} agent(s) need attention")
        sys.exit(1)


if __name__ == "__main__":
    main()
