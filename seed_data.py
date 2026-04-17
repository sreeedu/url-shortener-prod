import asyncio
import random
import uuid
from datetime import datetime, timedelta
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.project import Project
from app.models.link import Link, LinkClick
from app.core.security import hash_password
from sqlalchemy.future import select
from app.core.useragent import parse_user_agent

# Realistic dummy options
REFERERS = [None, "https://twitter.com", "https://t.co/xyz", "https://google.com", "https://facebook.com", "https://linkedin.com", "https://reddit.com", "https://news.ycombinator.com", "android-app://com.instagram.android"]

USER_AGENTS = {
    "ios_mobile_safari": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
    "android_mobile_chrome": "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
    "win_desktop_chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "win_desktop_edge": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.51",
    "mac_desktop_safari": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "mac_desktop_chrome": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "linux_desktop_firefox": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/114.0",
    "googlebot": "Googlebot/2.1 (+http://www.google.com/bot.html)",
    "ahrefsbot": "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
}

# Define test link profiles
LINK_PROFILES = [
    {
        "short_code": "ai_test",
        "title": "Summer Shoe Sale (General)",
        "original_url": "https://example.com/summer-sale",
        "clicks": 500,
        "profile": "general"
    },
    {
        "short_code": "ig_promo",
        "title": "Instagram Influencer Promo",
        "original_url": "https://example.com/influencer",
        "clicks": 1200,
        "profile": "mobile_heavy"
    },
    {
        "short_code": "b2b_docs",
        "title": "B2B API Documentation",
        "original_url": "https://example.com/docs/api",
        "clicks": 450,
        "profile": "desktop_heavy"
    },
    {
        "short_code": "hackernews_launch",
        "title": "Launch on HackerNews",
        "original_url": "https://example.com/launch",
        "clicks": 2500,
        "profile": "linux_viral"
    },
    {
        "short_code": "twitter_flash",
        "title": "Twitter Flash Sale (Yesterday)",
        "original_url": "https://example.com/flash24",
        "clicks": 800,
        "profile": "recent_spike"
    },
    {
        "short_code": "scraper_target",
        "title": "Public Pricing Page",
        "original_url": "https://example.com/pricing",
        "clicks": 600,
        "profile": "bot_heavy"
    },
    {
        "short_code": "internal_wiki",
        "title": "Company Internal Wiki",
        "original_url": "https://intranet.example.com",
        "clicks": 200,
        "profile": "internal_edge"
    },
    {
        "short_code": "old_campaign",
        "title": "Last Month's Giveaway",
        "original_url": "https://example.com/giveaway-old",
        "clicks": 300,
        "profile": "old_traffic"
    },
    {
        "short_code": "newsletter_w4",
        "title": "Weekly Newsletter Issue 4",
        "original_url": "https://example.com/newsletter/4",
        "clicks": 900,
        "profile": "email_blast"
    },
    {
        "short_code": "facebook_retarget",
        "title": "FB Retargeting Ads",
        "original_url": "https://example.com/fb-ads",
        "clicks": 1500,
        "profile": "facebook_ads"
    }
]

def generate_click_for_profile(link_id, profile_type, now):
    """Generates a single LinkClick object tailored to a specific traffic profile."""
    
    # Defaults
    days_ago = random.randint(0, 30)
    hours_ago = random.randint(0, 23)
    minutes_ago = random.randint(0, 59)
    ua_key = random.choice(list(USER_AGENTS.keys()))
    referer = random.choice(REFERERS)
    
    if profile_type == "mobile_heavy":
        # 95% mobile traffic, mostly instagram referrer
        ua_key = random.choices(
            ["ios_mobile_safari", "android_mobile_chrome", "win_desktop_chrome"], 
            weights=[60, 35, 5]
        )[0]
        referer = "android-app://com.instagram.android" if random.random() < 0.8 else None
        
    elif profile_type == "desktop_heavy":
        # 95% Windows/Mac Desktop, weekday hours mostly
        ua_key = random.choices(
            ["win_desktop_chrome", "win_desktop_edge", "mac_desktop_chrome", "android_mobile_chrome"],
            weights=[50, 25, 20, 5]
        )[0]
        referer = "https://linkedin.com" if random.random() < 0.4 else "https://google.com"
        hours_ago = random.randint(9, 17) # Business hours
        
    elif profile_type == "linux_viral":
        # HackerNews spike, lots of Linux and Firefox
        ua_key = random.choices(
            ["linux_desktop_firefox", "mac_desktop_safari", "mac_desktop_chrome", "ios_mobile_safari"],
            weights=[40, 20, 30, 10]
        )[0]
        referer = "https://news.ycombinator.com" if random.random() < 0.8 else "https://twitter.com"
        days_ago = random.choices([2, 3, 4, random.randint(5, 30)], weights=[40, 30, 20, 10])[0]
        
    elif profile_type == "recent_spike":
        # Massive spike in the last 24-48 hours
        days_ago = random.choices([0, 1, random.randint(2, 30)], weights=[60, 35, 5])[0]
        referer = random.choice(["https://twitter.com", "https://t.co/xyz"]) if random.random() < 0.9 else None
        
    elif profile_type == "bot_heavy":
        # 85% bots continuously crawling
        ua_key = random.choices(["googlebot", "ahrefsbot", "win_desktop_chrome"], weights=[50, 35, 15])[0]
        referer = None
        
    elif profile_type == "internal_edge":
        # 100% Windows Edge, No referer (direct link)
        ua_key = "win_desktop_edge"
        referer = None
        # Mon-Fri
        days_ago = random.randint(0, 30)
        while (now - timedelta(days=days_ago)).weekday() >= 5:
            days_ago = random.randint(0, 30)
            
    elif profile_type == "old_traffic":
        # All traffic between 20-30 days ago
        days_ago = random.randint(20, 30)
        
    elif profile_type == "email_blast":
        # Huge spike exactly 7 days ago
        days_ago = 7 if random.random() < 0.8 else random.randint(8, 14)
        referer = None # Emails hide referer
        
    elif profile_type == "facebook_ads":
        # Facebook referrers, mostly mobile
        ua_key = random.choices(["android_mobile_chrome", "ios_mobile_safari", "win_desktop_chrome"], weights=[50, 40, 10])[0]
        referer = "https://facebook.com" if random.random() < 0.95 else None

    # Resolve UA string and parse it properly   
    ua_string = USER_AGENTS[ua_key]
    device_type, browser_name, os_name = parse_user_agent(ua_string)
    
    click_date = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
    ip = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.1"
    
    click = LinkClick(
        link_id=link_id,
        ip_address=ip,
        user_agent=ua_string,
        referer=referer,
        os=os_name,
        browser=browser_name,
        device_type=device_type
    )
    click.clicked_at = click_date 
    return click

async def seed_data():
    async with AsyncSessionLocal() as db:
        print("Checking for test user...")
        # 1. Create or get test user
        result = await db.execute(select(User).where(User.email == "test_ai@example.com"))
        user = result.scalars().first()
        
        if not user:
            print("Creating test user (test_ai@example.com)...")
            user = User(
                email="test_ai@example.com",
                password_hash=hash_password("password123"),
                is_active=True,
                is_verified=True
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # 2. Create or get test project
        result = await db.execute(select(Project).where(Project.name == "AI Marketing Campaign", Project.owner_user_id == user.id))
        project = result.scalars().first()
        
        if not project:
            print("Creating test project...")
            project = Project(
                name="AI Marketing Campaign",
                slug="ai-marketing-campaign",
                owner_user_id=user.id
            )
            db.add(project)
            await db.commit()
            await db.refresh(project)

        print(f"--- GENERATING LINKS AND CLICKS ---")
        print(f"Project ID: {project.id}")
        now = datetime.utcnow()

        total_clicks_inserted = 0

        # Create links and clicks iteratively
        for profile in LINK_PROFILES:
            result = await db.execute(select(Link).where(Link.short_code == profile["short_code"], Link.created_by == user.id))
            link = result.scalars().first()
            
            if not link:
                print(f"Creating link '{profile['title']}'...")
                link = Link(
                    original_url=profile["original_url"],
                    short_code=profile["short_code"],
                    title=profile["title"],
                    project_id=project.id,
                    created_by=user.id
                )
                db.add(link)
                await db.commit()
                await db.refresh(link)
            else:
                print(f"Link '{profile['title']}' already exists.")

            # Check if clicks already exist (avoid duplicates)
            result = await db.execute(select(LinkClick.id).where(LinkClick.link_id == link.id).limit(1))
            if result.scalars().first() is None:
                print(f"  -> Generating {profile['clicks']} tailored clicks (Pattern: {profile['profile']})...")
                clicks_to_insert = [generate_click_for_profile(link.id, profile['profile'], now) for _ in range(profile['clicks'])]
                
                # Batch insert
                db.add_all(clicks_to_insert)
                await db.commit()
                total_clicks_inserted += len(clicks_to_insert)
            else:
                print(f"  -> Clicks already generated for this link. Skipping.")

        print(f"\n✅ Successfully inserted {total_clicks_inserted} highly segmented clicks across {len(LINK_PROFILES)} links!")
        print("\n--- HOW TO TEST ---")
        print("1. Login to the frontend with: test_ai@example.com / password123")
        print("2. Go to the 'AI Marketing Campaign' Project.")
        print("3. Check out the 10 distinct links with radically different traffic shapes!")

if __name__ == "__main__":
    asyncio.run(seed_data())
