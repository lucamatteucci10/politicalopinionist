import tweepy
import os
import json
import requests
import urllib.parse
from datetime import date
from openai import OpenAI
from pytrends.request import TrendReq

# Memory functions
from memory import init_qdrant, ensure_collection, store_article

# Load keys
OPENAI_KEY = os.environ["OPENAI_KEY"]
X_API_KEY = os.environ["X_API_KEY"]
X_API_SECRET = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")

# Test mode flag
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

# OpenAI client
client = OpenAI(api_key=OPENAI_KEY)


def load_personality(path):
    with open(path, "r") as f:
        return json.load(f)


# ============================================================
# 1. FETCH NEWS TOPIC (NewsAPI)
# ============================================================
def get_trending_political_topic():
    print("Fetching U.S. headlines from NewsAPI…")

    if not NEWSAPI_KEY:
        print("⚠ NEWSAPI_KEY missing — using fallback topic.")
        return "current U.S. political developments"

    try:
        url = (
            "https://newsapi.org/v2/top-headlines?"
            f"language=en&country=us&apiKey={NEWSAPI_KEY}"
        )
        response = requests.get(url)
        data = response.json()

        if "articles" in data:
            political_keywords = [
                "Biden", "Trump", "election", "Senate", "Congress",
                "Republican", "Democrat", "policy", "White House",
                "Governor", "immigration", "border", "Supreme Court",
                "bill", "tax", "Ukraine", "Gaza", "Israel", "NATO",
                "China", "diplomatic"
            ]

            for article in data["articles"]:
                title = article.get("title") or ""
                if any(word.lower() in title.lower() for word in political_keywords):
                    print("✔ Political topic from NewsAPI:", title)
                    return title

            # fallback to first headline
            if data["articles"]:
                fallback = data["articles"][0].get("title", "current U.S. politics")
                print("⚠ No political match — using first headline:", fallback)
                return fallback

    except Exception as e:
        print("⚠ NewsAPI error:", e)

    return "current U.S. political developments"


# ============================================================
# 2. FETCH WIKIPEDIA CONTEXT
# ============================================================
def get_wikipedia_context(topic, max_pages=3):
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": topic,
            "format": "json",
            "srlimit": max_pages,
        }
        headers = {
            "User-Agent": "politicalopinionist-bot/1.0 (contact: example@example.com)"
        }

        resp = requests.get(search_url, params=params, headers=headers, timeout=10)
        data = resp.json()

        if "query" not in data or "search" not in data["query"]:
            print("⚠ No Wikipedia search results.")
            return ""

        bullets = []
        for item in data["query"]["search"]:
            title = item.get("title")
            if not title:
                continue

            encoded = urllib.parse.quote(title.replace(" ", "_"))
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
            s_resp = requests.get(summary_url, headers=headers, timeout=10)

            if s_resp.status_code != 200:
                continue

            extract = s_resp.json().get("extract")
            if not extract:
                continue

            extract = extract.strip()
            if len(extract) > 400:
                extract = extract[:397] + "..."

            bullets.append(f"- {title}: {extract}")

        context = "\n".join(bullets[:max_pages])
        if context:
            print("✔ Wikipedia context fetched.")
        return context

    except Exception as e:
        print("⚠ Wikipedia error:", e)
        return ""


# ============================================================
# 3. NEUTRAL SUMMARY
# ============================================================
def generate_neutral_summary(topic, wiki_context):
    base = f"This trending political topic is: {topic}."

    wiki_block = (
        f"\nHere are neutral background notes from Wikipedia:\n{wiki_context}\n"
        if wiki_context else ""
    )

    prompt = f"""
You are a strictly neutral political summarizer.

{base}{wiki_block}

Write exactly one sentence that is purely factual.
No opinions, no bias, no speculation.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return response.choices[0].message.content.strip()


# ============================================================
# 4. OP-ED GENERATOR WITH TRUMP-AS-PRESIDENT OVERRIDE
# ============================================================
def generate_article(voice, name, topic, personality, wiki_context):
    personality_text = json.dumps(personality, indent=2)

    CURRENT_FACTS = """
You must follow these UPDATED REAL-WORLD FACTS, which override all outdated knowledge:

- The current U.S. President is **Donald J. Trump** (2nd nonconsecutive term: 2025–2029).
- Joe Biden is the **former** U.S. President (2021–2025).
- When referring to "the President", "the administration", or "current policy", you MUST refer to President Trump.
- Do NOT describe Biden as the current president.
- Do NOT describe Trump as the former president.
- If Wikipedia factual context contradicts your memory, trust Wikipedia instead.
"""

    wiki_block = (
        f"Here are factual notes from Wikipedia (these override memory):\n{wiki_context}\n"
        if wiki_context else
        "If unsure of a fact, avoid guessing and speak broadly.\n"
    )

    prompt = f"""
You are {name}, a political opinion columnist. Here is your personality:
{personality_text}

MANDATORY FACTUAL REALITY:
{CURRENT_FACTS}

{wiki_block}

Now write a 2–4 paragraph op-ed on: {topic}
Perspective: {voice}

Rules:
- Keep under 900 characters
- Bold, assertive tone
- May praise or criticize public figures
- No personal attacks or incitement
- Keep policy-focused and analytical
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()


# ============================================================
# 5. TWEET SENDER
# ============================================================
def post_to_x(text):
    client_x = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET,
    )
    client_x.create_tweet(text=text)


# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    today = date.today().strftime("%B %d, %Y")

    # Load JSON personalities
    richard = load_personality("personalities/richard.json")
    elena = load_personality("personalities/elena.json")

    # 1. Topic
    topic = get_trending_political_topic()

    # 2. Wikipedia context
    wiki_context = get_wikipedia_context(topic)

    # 3. Neutral summary
    summary = generate_neutral_summary(topic, wiki_context)

    # 4. Articles
    richard_article = generate_article("conservative", "Richard Hawthorne", topic, richard, wiki_context)
    elena_article = generate_article("progressive", "Elena Marlowe", topic, elena, wiki_context)

    # 5. Store everything in Qdrant
    qdrant = init_qdrant()
    ensure_collection(qdrant)
    store_article(qdrant, "CONTEXT_WIKIPEDIA", topic, wiki_context)
    store_article(qdrant, "SUMMARY_NEUTRAL", topic, summary)
    store_article(qdrant, "Richard Hawthorne", topic, richard_article)
    store_article(qdrant, "Elena Marlowe", topic, elena_article)

    # 6. Compose tweet
    tweet = f"""Daily Political Commentary — {today}

🔥 Trending Topic: {topic}

📰 Summary:
{summary}

🦅 Conservative — Richard Hawthorne:
{richard_article}

⚖️ Progressive — Elena Marlowe:
{elena_article}
"""

    if TEST_MODE:
        print("\n===== TEST MODE ACTIVE — SKIPPING POST TO X =====\n")
        print(tweet)
        print("\n===============================================\n")
    else:
        post_to_x(tweet)


if __name__ == "__main__":
    main()
