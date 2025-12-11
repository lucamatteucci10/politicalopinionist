import tweepy
import os
import json
import requests
import urllib.parse
from datetime import date
from openai import OpenAI
from pytrends.request import TrendReq  # still imported if you want to re-use later

# NEW: import memory functions
from memory import init_qdrant, ensure_collection, store_article

# Load keys from GitHub Secrets
OPENAI_KEY = os.environ["OPENAI_KEY"]
X_API_KEY = os.environ["X_API_KEY"]
X_API_SECRET = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]

# Test mode flag
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

# NewsAPI key
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_KEY)


def load_personality(path):
    with open(path, "r") as f:
        return json.load(f)


def get_trending_political_topic():
    """Get a political topic from NewsAPI with keyword filtering."""

    print("Fetching U.S. headlines from NewsAPI…")

    if not NEWSAPI_KEY:
        print("⚠ NEWSAPI_KEY not set, falling back to generic topic.")
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

            # Prefer headlines that clearly look political
            for article in data["articles"]:
                title = article.get("title") or ""
                if any(word.lower() in title.lower() for word in political_keywords):
                    print("✔ NewsAPI political topic:", title)
                    return title

            # If nothing matched but we got headlines, take the first one
            if len(data["articles"]) > 0:
                fallback_title = data["articles"][0].get("title") or "current U.S. political developments"
                print("⚠ No explicit political headline found — using general headline:", fallback_title)
                return fallback_title

    except Exception as e:
        print("⚠ NewsAPI failed:", e)

    print("⚠ Using final fallback topic.")
    return "current U.S. political developments"


def get_wikipedia_context(topic, max_pages=3):
    """Fetch neutral factual background from Wikipedia related to the topic."""

    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": topic,
            "format": "json",
            "srlimit": max_pages,
        }

        headers = {
            # Put any contact you like here, Wikipedia just wants *some* UA
            "User-Agent": "politicalopinionist-bot/1.0 (contact: example@example.com)"
        }

        resp = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        data = resp.json()

        if "query" not in data or "search" not in data["query"]:
            print("⚠ Wikipedia search returned no results.")
            return ""

        bullets = []
        for item in data["query"]["search"]:
            title = item.get("title")
            if not title:
                continue

            # Get summary for this page
            title_encoded = urllib.parse.quote(title.replace(" ", "_"))
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title_encoded}"
            s_resp = requests.get(summary_url, headers=headers, timeout=10)

            if s_resp.status_code != 200:
                continue

            s_data = s_resp.json()
            extract = s_data.get("extract")
            if not extract:
                continue

            short_extract = extract.strip()
            if len(short_extract) > 400:
                short_extract = short_extract[:397] + "..."

            bullets.append(f"- {title}: {short_extract}")

        context = "\n".join(bullets[:max_pages])
        if context:
            print("✔ Wikipedia context fetched.")
        else:
            print("⚠ No usable Wikipedia context extracted.")
        return context

    except Exception as e:
        print("⚠ Wikipedia context fetch failed:", e)
        return ""


def generate_neutral_summary(topic, wiki_context=""):
    """Generate a strictly neutral one-sentence summary, grounded if possible."""

    base = f"This trending political topic is: {topic}."

    if wiki_context:
        context_part = f"""
Here are neutral background notes from Wikipedia about this topic:
{wiki_context}
"""
    else:
        context_part = ""

    prompt = f"""You are a neutral political explainer.

{base}{context_part}

Write exactly one sentence that provides a strictly neutral, factual summary of the topic.
Do NOT express any opinion, emotion, speculation, or evaluation.
Do NOT take a side.
Keep it purely descriptive and high-level.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()


def generate_article(voice, name, topic, personality, wiki_context=""):
    """Generate an opinionated op-ed grounded in Wikipedia facts."""

    personality_text = json.dumps(personality, indent=2)

    if wiki_context:
        context_block = f"""Here are factual background notes from recent Wikipedia pages related to this topic and the entities involved:
{wiki_context}

Treat these as up-to-date facts. If anything you 'remember' conflicts with these notes, trust these notes and avoid outdated claims.
"""
    else:
        context_block = (
            "If you are unsure about a specific fact (like someone's current role or title), "
            "stay vague rather than guessing.\n"
        )

    prompt = f"""You are {name}, an established political opinion columnist. Here is your personality profile:
{personality_text}

{context_block}
Now, write a 2–4 paragraph op-ed article about this trending political topic: {topic}.
Perspective: {voice}.

Your tone should be assertive, bold, and provocative — offering strong opinions,
confident claims, pointed observations, and occasional rhetorical flair. You may explicitly 
name public political figures (e.g., the sitting President, former Presidents, major political leaders, Senators, Governors) 
and occasionally praise or criticize them when relevant, but keep your commentary analytical,
not targeted at specific demographic groups.

You are NOT neutral — you are an opinion writer with a clear ideological viewpoint — 
but you still maintain professionalism and avoid personal attacks or incitement. 
Keep commentary grounded in policy, leadership decisions, and public events.

Keep the article under 900 characters.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )

    return response.choices[0].message.content.strip()


def post_to_x(text):
    client_x = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET
    )
    client_x.create_tweet(text=text)


def main():
    today = date.today().strftime("%B %d, %Y")

    # Load personalities
    richard_personality = load_personality("personalities/richard.json")
    elena_personality = load_personality("personalities/elena.json")

    # 1. Topic from NewsAPI
    topic = get_trending_political_topic()

    # 2. Factual background from Wikipedia
    wiki_context = get_wikipedia_context(topic)

    # 3. Neutral summary
    summary = generate_neutral_summary(topic, wiki_context)

    # 4. Opinion pieces
    conservative_article = generate_article(
        "conservative", "Richard Hawthorne", topic, richard_personality, wiki_context
    )
    progressive_article = generate_article(
        "progressive", "Elena Marlowe", topic, elena_personality, wiki_context
    )

    # 5. Store articles in Qdrant
    qdrant = init_qdrant()
    ensure_collection(qdrant)

    store_article(qdrant, "Richard Hawthorne", topic, conservative_article)
    store_article(qdrant, "Elena Marlowe", topic, progressive_article)

    # 6. Compose tweet
    tweet = f"""Daily Political Commentary — {today}

🔥 Trending Topic: {topic}

📰 Summary:
{summary}

🦅 Conservative — Richard Hawthorne:
{conservative_article}

⚖️ Progressive — Elena Marlowe:
{progressive_article}
"""

    # 7. Test mode vs live post
    if TEST_MODE:
        print("\n===== TEST MODE ACTIVE — SKIPPING POST TO X =====")
        print(tweet)
        print("=================================================\n")
    else:
        post_to_x(tweet)


if __name__ == "__main__":
    main()
