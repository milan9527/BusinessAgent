---
name: web-crawler
description: 网页爬虫代码库技能。提供可复用的Python爬虫代码模板，配合AgentCore Code Interpreter使用。包含通用网页抓取、批量URL采集、API调用、数据解析清洗、结构化数据提取等代码片段。当agent需要用代码抓取网页数据时，直接复用这些模板代码。适用关键词：爬虫、抓取、requests、beautifulsoup、数据采集、批量抓取、API、JSON解析、HTML解析、代码解释器。
---

# 网页爬虫代码库

为 AgentCore Code Interpreter 提供可复用的 Python 爬虫代码模板。使用时将代码传入 code_interpreter 工具执行。

## 工具选择决策指南

根据任务特征自动选择正确的工具：

### 使用 Browser 工具的场景
- 需要JavaScript渲染的动态页面（SPA、React/Vue应用）
- 需要登录、点击按钮、填写表单等交互操作
- 需要截图取证
- 单个页面的深度浏览和交互
- 社交媒体动态内容（无限滚动加载）

### 使用 Code Interpreter 工具的场景
- 批量抓取多个URL（>3个页面）
- 静态HTML页面的数据提取
- 调用公开REST API获取数据
- 数据清洗、统计分析、生成图表
- 处理CSV/JSON/Excel文件
- 需要正则表达式或复杂文本处理
- 抓取RSS/Atom feeds

### 协同使用
- Browser 先探索页面结构 → Code Interpreter 批量抓取
- Code Interpreter 抓取原始数据 → Code Interpreter 分析可视化

## 代码模板

### 1. 通用网页抓取

```python
import requests
from bs4 import BeautifulSoup

def fetch_page(url, timeout=15):
    """抓取单个网页，返回BeautifulSoup对象"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, 'html.parser')

# 使用示例
soup = fetch_page('https://example.com')
title = soup.find('title').text
print(f"页面标题: {title}")
```

### 2. 批量URL抓取

```python
import requests
from bs4 import BeautifulSoup
import time
import json

def batch_fetch(urls, delay=1):
    """批量抓取多个URL，返回结果列表"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    results = []
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            results.append({
                'url': url,
                'status': resp.status_code,
                'title': soup.find('title').text if soup.find('title') else '',
                'html': resp.text
            })
        except Exception as e:
            results.append({'url': url, 'status': 'error', 'error': str(e)})
        time.sleep(delay)
    return results

# 使用示例
urls = ['https://example.com', 'https://example.org']
data = batch_fetch(urls)
for d in data:
    print(f"{d['url']} -> {d['status']}: {d.get('title','')}")
```

### 3. 新闻/文章列表提取

```python
import requests
from bs4 import BeautifulSoup

def extract_articles(url, item_selector, title_selector, link_selector=None):
    """从列表页提取文章标题和链接"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, 'html.parser')
    articles = []
    for item in soup.select(item_selector):
        title_el = item.select_one(title_selector)
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = ''
        if link_selector:
            link_el = item.select_one(link_selector)
            if link_el and link_el.get('href'):
                link = link_el['href']
        elif title_el.name == 'a':
            link = title_el.get('href', '')
        articles.append({'title': title, 'link': link})
    return articles

# Hacker News 示例
articles = extract_articles(
    'https://news.ycombinator.com',
    item_selector='.titleline',
    title_selector='a'
)
for i, a in enumerate(articles[:10], 1):
    print(f"{i}. {a['title']}")
    print(f"   {a['link']}")
```

### 4. 电商产品数据提取

```python
import requests
from bs4 import BeautifulSoup
import json

def scrape_product_listings(url):
    """通用电商产品列表抓取框架"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    resp = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, 'html.parser')

    # 尝试提取JSON-LD结构化数据（很多电商网站都有）
    products = []
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'Product':
                products.append({
                    'name': data.get('name'),
                    'price': data.get('offers', {}).get('price'),
                    'currency': data.get('offers', {}).get('priceCurrency'),
                    'description': data.get('description', '')[:200]
                })
        except:
            pass
    return products, soup
```

### 5. Google Trends / 搜索趋势

```python
import requests
import json

def get_google_suggestions(keyword, lang='en', country='us'):
    """获取Google搜索建议（免费，无需API key）"""
    url = f'http://suggestqueries.google.com/complete/search'
    params = {
        'client': 'firefox',
        'q': keyword,
        'hl': lang,
        'gl': country
    }
    resp = requests.get(url, params=params, timeout=10)
    data = json.loads(resp.text)
    return data[1] if len(data) > 1 else []

# 使用示例
suggestions = get_google_suggestions('wireless earbuds')
for s in suggestions:
    print(f"  - {s}")
```

### 6. RSS/Atom Feed 解析

```python
import requests
from bs4 import BeautifulSoup

def parse_rss(feed_url):
    """解析RSS/Atom feed，提取文章列表"""
    resp = requests.get(feed_url, timeout=15)
    soup = BeautifulSoup(resp.text, 'xml')

    articles = []
    # RSS 2.0
    for item in soup.find_all('item'):
        articles.append({
            'title': item.find('title').text if item.find('title') else '',
            'link': item.find('link').text if item.find('link') else '',
            'date': item.find('pubDate').text if item.find('pubDate') else '',
            'description': item.find('description').text[:200] if item.find('description') else ''
        })
    # Atom
    if not articles:
        for entry in soup.find_all('entry'):
            articles.append({
                'title': entry.find('title').text if entry.find('title') else '',
                'link': entry.find('link')['href'] if entry.find('link') else '',
                'date': entry.find('updated').text if entry.find('updated') else '',
                'description': entry.find('summary').text[:200] if entry.find('summary') else ''
            })
    return articles
```

### 7. 公开API调用模板

```python
import requests
import json

def call_api(url, params=None, headers=None):
    """通用REST API调用"""
    default_headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    if headers:
        default_headers.update(headers)
    resp = requests.get(url, params=params, headers=default_headers, timeout=15)
    resp.raise_for_status()
    return resp.json()

# GitHub trending 示例
def github_trending(language='python', since='daily'):
    """获取GitHub trending项目（通过页面抓取）"""
    url = f'https://github.com/trending/{language}?since={since}'
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, 'html.parser')
    repos = []
    for article in soup.select('article.Box-row'):
        name_el = article.select_one('h2 a')
        desc_el = article.select_one('p')
        if name_el:
            repos.append({
                'name': name_el.get_text(strip=True).replace('\n', '').replace(' ', ''),
                'url': 'https://github.com' + name_el['href'],
                'description': desc_el.get_text(strip=True) if desc_el else ''
            })
    return repos
```

### 8. 数据清洗与分析

```python
import json
import re
from collections import Counter

def clean_text(text):
    """清洗HTML文本"""
    text = re.sub(r'<[^>]+>', '', text)  # 去除HTML标签
    text = re.sub(r'\s+', ' ', text)     # 合并空白
    return text.strip()

def extract_emails(text):
    """提取邮箱地址"""
    return re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)

def extract_prices(text):
    """提取价格信息"""
    return re.findall(r'[\$€£¥]\s*[\d,]+\.?\d*', text)

def word_frequency(text, top_n=20):
    """词频统计"""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return Counter(words).most_common(top_n)

def summarize_data(items, key):
    """对列表数据按key做统计摘要"""
    values = [item.get(key) for item in items if item.get(key) is not None]
    if not values:
        return {}
    if all(isinstance(v, (int, float)) for v in values):
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values)
        }
    return {'count': len(values), 'unique': len(set(values)), 'top5': Counter(values).most_common(5)}
```

## 使用注意事项
- 所有代码在 AgentCore Code Interpreter 的沙箱中执行，已预装 requests 和 beautifulsoup4
- 批量抓取时加入 delay 避免被封IP
- 仅抓取公开可访问数据，遵守 robots.txt
- 大量数据建议分批处理，单次执行有超时限制
