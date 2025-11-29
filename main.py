# main.py
import os
import json
import requests
import subprocess
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright

app = FastAPI()

# --- DIAGNOSTICS ---
@app.on_event("startup")
def startup_check():
    token = os.environ.get("AIPROXY_TOKEN")
    if token:
        print(f"✅ Token loaded (starts with {token[:3]}...)")
    else:
        print("❌ Token MISSING")

class Task(BaseModel):
    email: str
    secret: str
    url: str

def get_ai_client():
    """Creates a requests session with retries for stability"""
    session = requests.Session()
    # Retry 3 times on connection errors or server errors (500, 502, 503, 504)
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

def run_code(script):
    with open("solver.py", "w") as f:
        f.write(script)
    try:
        # UPDATED: Timeout increased to 60s (Safety buffer)
        result = subprocess.run(["python", "solver.py"], capture_output=True, text=True, timeout=60)
        return result.stdout.strip()
    except Exception as e:
        return str(e)

def get_page_text(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = browser.new_page()
        page.goto(url)
        # Wait 1 second for JavaScript to render the quiz content
        page.wait_for_timeout(1000)
        content = page.content()
        text = page.inner_text("body")
        browser.close()
        return content, text

def process_quiz(url, email, secret):
    print(f"\n🚀 Processing: {url}")
    
    token = os.environ.get("AIPROXY_TOKEN")
    if not token:
        print("❌ ERROR: AIPROXY_TOKEN is missing")
        return

    try:
        # 1. Scraping
        try:
            html, text = get_page_text(url)
            print("✅ Scraping successful")
        except Exception as e:
            print(f"❌ Scraping Failed: {e}")
            return

        # 2. AI Call
        print("🤖 Asking AI...")
        
        # We use HTTPS as per Project Instructions
        proxy_url = "https://aiproxy.sanandworkers.workers.dev/openai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a python helper. Return only python code in ```python``` blocks. Use requests, pandas, and scikit-learn. Print the final answer."},
                {"role": "user", "content": f"Task: Write python code to solve this quiz based on this text:\n{text[:15000]}"}
            ]
        }

        try:
            session = get_ai_client()
            # verify=False is a safety net for SSL issues in the container environment
            response = session.post(proxy_url, headers=headers, json=payload, timeout=60, verify=False)
            
            if response.status_code != 200:
                print(f"❌ AI Status Error: {response.status_code}")
                print(f"Response: {response.text}")
                return

            ai_data = response.json()
            ai_content = ai_data['choices'][0]['message']['content']
            print("✅ AI Response received")
            
        except Exception as e:
            print(f"❌ AI Connection Error: {e}")
            return

        # 3. Extract and Run Code
        import re
        code_match = re.search(r"```python(.*?)```", ai_content, re.DOTALL)
        script = code_match.group(1).strip() if code_match else ai_content

        print("⚡ Running generated code...")
        answer = run_code(script)
        print(f"💡 Computed Answer: {answer}")

        # 4. Clean Answer
        try:
            final_ans = float(answer)
            if final_ans.is_integer():
                final_ans = int(final_ans)
        except:
            final_ans = answer

        # 5. Submit
        submit_payload = {"email": email, "secret": secret, "url": url, "answer": final_ans}
        
        # Default submit URL
        submit_url = "https://tds-llm-analysis.s-anand.net/submit"
        
        # Regex to find the submit URL in the specific quiz page
        match = re.search(r"https://[^\s\"']+/submit", html)
        if match:
            submit_url = match.group(0)

        print(f"📤 Submitting to {submit_url}")
        
        # We use the session with retries for submission too
        sub = session.post(submit_url, json=submit_payload, timeout=30, verify=False)
        print(f"✅ Submission Result: {sub.status_code}, {sub.text}")

        # 6. RECURSION (Project Logic: If correct, get new URL)
        try:
            sub_data = sub.json()
            if "url" in sub_data and sub_data["url"]:
                next_url = sub_data["url"]
                print(f"🔗 Chain continues! Moving to: {next_url}")
                process_quiz(next_url, email, secret)
            else:
                print("🏁 Quiz finished (no new URL).")
        except:
            pass

    except Exception as e:
        print(f"❌ GLOBAL ERROR: {e}")

@app.post("/run")
async def run_task(task: Task, background_tasks: BackgroundTasks):
    if task.secret != "MySuperSecretKey":
        raise HTTPException(status_code=403, detail="Invalid Secret")
    
    background_tasks.add_task(process_quiz, task.url, task.email, task.secret)
    return {"message": "Task started"}

@app.get("/")
def home():
    return {"status": "running"}
