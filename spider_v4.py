import pandas as pd
import re
import time
import sys
import urllib.parse
from collections import deque
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# --- CONFIGURATION ---
OUTPUT_FILE = "spider_v4_leads.csv"
MAX_DEPTH = 2  
MAX_LEADS = 500  
SEARCH_PAGES_TO_SCRAPE = 5
RESTART_EVERY_N = 20

# KEYWORDS THAT MEAN "THIS IS A DIRECTORY"
DIRECTORY_KEYWORDS = ["top", "best", "list", "companies", "directory", "ranking", "review", "clutch", "goodfirms", "glassdoor", "f6s", "soralist", "techbehemoths"]

# KEYWORDS THAT MEAN "WE GOT BLOCKED"
BLOCKED_TITLES = ["checking your browser", "just a moment", "access denied", "security check", "challenge", "attention required", "403 forbidden"]

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled") # Hides "Robot" flag
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    service.creation_flags = 0x08000000 if sys.platform == "win32" else 0 
    return webdriver.Chrome(service=service, options=chrome_options)

def is_directory(title, url):
    t = title.lower()
    u = url.lower()
    if any(k in t for k in DIRECTORY_KEYWORDS): return True
    if any(k in u for k in DIRECTORY_KEYWORDS): return True # Check URL too!
    if "blog" in u or "article" in u: return True
    return False

def is_blocked(title):
    t = title.lower()
    if any(k in t for k in BLOCKED_TITLES): return True
    return False

def clean_url(url):
    if "duckduckgo.com/l/" in url or "uddg=" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'uddg' in qs: return qs['uddg'][0]
        except: pass
    return url

def extract_contacts(driver):
    try:
        text = driver.find_element(By.TAG_NAME, "body").text
        page_source = driver.page_source
        
        emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))
        # Filter out junk emails (images, support emails for the directory itself)
        emails = [e for e in emails if not any(x in e for x in ['.png', '.jpg', 'gif', 'sentry', 'wix', 'domain', 'example', 'support@f6s.com'])]

        phones = list(set(re.findall(r'(?:\+88|88)?(01[3-9]\d{8})', text.replace('-', '').replace(' ', ''))))
        
        wa_links = re.findall(r'wa\.me/(\d+)', page_source)
        wa_api = re.findall(r'api\.whatsapp\.com/send\?phone=(\d+)', page_source)
        whatsapps = list(set(wa_links + wa_api))
        
        return emails, phones, whatsapps
    except:
        return [], [], []

def get_external_links(driver, current_domain):
    links = []
    try:
        elements = driver.find_elements(By.TAG_NAME, "a")
        for el in elements:
            try:
                href = el.get_attribute("href")
                if not href or not href.startswith("http"): continue
                if any(x in href for x in ['facebook', 'linkedin', 'twitter', 'google', 'instagram', 'youtube']): continue
                if current_domain in href: continue # Skip internal links
                links.append(href)
            except: continue
    except: pass
    return list(set(links))

def smart_spider(initial_query):
    print(f"\n🕷️  Starting SPIDER V4 (Anti-Block) on: '{initial_query}'...")
    
    driver = setup_driver()
    visit_queue = deque()
    visited_urls = set()
    leads_data = []

    # --- PHASE 1: HARVEST SEARCH PAGES ---
    print(f"🔎  Phase 1: Harvesting Top {SEARCH_PAGES_TO_SCRAPE} Pages of Results...")
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(initial_query)}"
    driver.get(search_url)

    for i in range(SEARCH_PAGES_TO_SCRAPE):
        print(f"   -> Scanning Search Page {i+1}...")
        
        results = driver.find_elements(By.CLASS_NAME, "result__a")
        for res in results:
            try:
                raw_link = res.get_attribute("href")
                link = clean_url(raw_link)
                title = res.text
                if link and link not in visited_urls:
                    visit_queue.append((link, 1, title)) 
                    visited_urls.add(link)
            except: pass
        
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "div.nav-link input[value='Next']")
            next_btn.click()
            time.sleep(2)
        except:
            print("   -> No more search pages.")
            break
            
    print(f"✅  Queue Populated: {len(visit_queue)} targets found. Starting Deep Spider...")
    
    # --- PHASE 2: DEEP SPIDER ---
    sites_visited_count = 0

    try:
        while visit_queue and len(leads_data) < MAX_LEADS:
            # Memory Restart
            if sites_visited_count > 0 and sites_visited_count % RESTART_EVERY_N == 0:
                print("   ♻️  Restaring Chrome...")
                driver.quit(); time.sleep(1); driver = setup_driver()

            url, depth, source_title = visit_queue.popleft()
            if depth > MAX_DEPTH: continue

            print(f"[{len(leads_data)} leads] Visiting: {url[:40]}...")
            sites_visited_count += 1
            
            try:
                driver.set_page_load_timeout(15)
                driver.get(url)
                time.sleep(1.5)
                
                title = driver.title
                current_domain = urllib.parse.urlparse(url).netloc
                
                # CHECK 1: DID WE GET BLOCKED?
                if is_blocked(title):
                    print(f"   🛑 BLOCKED by Cloudflare ('{title}'). Skipping.")
                    continue

                # CHECK 2: IS IT A DIRECTORY? (Now checks URL too, not just title)
                if is_directory(title, url):
                    print(f"   -> Detected List: '{title[:30]}...' -> Harvesting Links")
                    links = get_external_links(driver, current_domain)
                    added = 0
                    for link in links:
                        if link and link not in visited_urls:
                            visit_queue.append((link, depth + 1, title))
                            visited_urls.add(link)
                            added += 1
                    print(f"   -> Added {added} new targets.")

                # CHECK 3: IT'S A COMPANY SITE
                else:
                    emails, phones, whatsapps = extract_contacts(driver)
                    
                    if not emails:
                        try:
                            contact_link = driver.find_element(By.PARTIAL_LINK_TEXT, "Contact")
                            driver.get(contact_link.get_attribute("href"))
                            time.sleep(2)
                            e2, p2, w2 = extract_contacts(driver)
                            emails += e2; phones += p2; whatsapps += w2
                        except: pass
                    
                    if emails or phones or whatsapps:
                        print(f"   -> 🎯 FOUND: {len(emails)} Emails | {len(whatsapps)} WA")
                        leads_data.append({
                            "Company": title, "Website": url, "Source": source_title,
                            "Emails": ", ".join(list(set(emails))),
                            "Phones": ", ".join(list(set(phones))),
                            "WhatsApp": ", ".join(list(set(whatsapps)))
                        })
                        pd.DataFrame(leads_data).to_csv(OUTPUT_FILE, index=False)
                    else:
                        print("   -> No data.")

            except Exception as e:
                print(f"   ⚠️  Skipping site: {e}")
                driver.quit(); driver = setup_driver()
                continue

    except KeyboardInterrupt:
        print("\n🛑  Stopping...")

    finally:
        try: driver.quit()
        except: pass
        if leads_data:
            pd.DataFrame(leads_data).to_csv(OUTPUT_FILE, index=False)
            print(f"\n✅ Finished! Saved {len(leads_data)} leads to {OUTPUT_FILE}")

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else input("Search Query: ")
    smart_spider(query)
