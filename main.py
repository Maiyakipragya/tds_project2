"""
main.py — TDS Project 2 agent (author: Maiya)

I wrote this agent to accept quiz POSTs and attempt solving the tasks automatically.
This file implements:
- a FastAPI `/run` endpoint that accepts {email, secret, url}
- page scraping with Playwright
- LLM calls (tries GROQ / OpenAI if API keys are present; otherwise attempts contest proxy)
- execution of solver code returned by the model (if any) with safety limits
- submission of answers to the provided /submit endpoint and follow-up chaining

I keep concise diagnostics so the build logs show what happened during evaluation.
No secrets are stored here; provide API keys through environment variables.
"""

import os
import re
import json
import socket
import subprocess
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

app = FastAPI()

# Basic configuration
AI_PROXY_HOSTNAME = "aiproxy.sanandworkers.workers.dev"
DIRECT_IPS = ["172.67.182.196", "104.21.32.227"]
MODEL_NAME = "gpt-4o-mini"
SYSTEM_INSTRUCTION = (
    "You are a python helper. Return only python code in ```python``` blocks. "
    "Use requests, pandas, and scikit-learn where appropriate. Print the final answer."
)

@app.on_event("startup")
def startup_check():
    token = os.environ.get("AIPROXY_TOKEN")
    if token:
        print(f"✅ AIPROXY_TOKEN present (starts with: {token[:3]}...)")
    else:
        print("ℹ️ No AIPROXY_TOKEN set. Provide GROQ_API_KEY or OPENAI_API_KEY if available.")

class Task(BaseModel):
    email: str
    secret: str
    url: str

def make_session(retries: int = 3, backoff: float = 1.0):
    s = requests.Session()
    r = Retry(total=retries, backoff_factor=backoff, status_forcelist=[429,500,502,503,504])
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.mount("http://", HTTPAdapter(max_retries=r))
    return s

def run_code(script: str, timeout: int = 60) -> str:
    """Write solver.py and execute it with a timeout. Return stdout or error text."""
    with open("solver.py", "w", encoding="utf-8") as f:
        f.write(script)
    try:
        result = subprocess.run(["python", "solver.py"], capture_output=True, text=True, timeout=timeout)
        out = result.stdout.strip()
        return out or (result.stderr.strip() or "")
    except subprocess.TimeoutExpired:
        return "ERROR: solver timed out"
    except Exception as e:
        return f"ERROR: running solver failed: {e}"

def get_page_text(url: str):
    """Render page with Playwright and return (html, inner_text)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(1000)
        content = page.content()
        text = page.inner_text("body")
        browser.close()
        return content, text

def process_quiz(url: str, email: str, secret: str):
    print(f"\n🚀 Processing: {url}")

    # 1) Scrape the page
    try:
        html, text = get_page_text(url)
        print("✅ Scraping successful")
    except Exception as e:
        print(f"❌ Scraping failed: {e}")
        return

    # 2) Prepare payload for LLM
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": f"Task: Write python code to solve this quiz based on this text:\n{text[:15000]}"}
        ]
    }

    session = make_session()
    ai_content = None

    # 3) Preferred providers: GROQ then OpenAI (if keys present)
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    aiproxy_token = os.environ.get("AIPROXY_TOKEN")

    if groq_key:
        try:
            print("🤖 Asking Groq...")
            resp = session.post("https://api.groq.com/openai/v1/chat/completions",
                                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                                json={"model": "llama3-70b-8192", "messages": payload["messages"]},
                                timeout=60)
            if resp.status_code == 200:
                ai_content = resp.json()['choices'][0]['message']['content']
                print("✅ AI Response received from Groq")
            else:
                print(f"⚠ Groq returned {resp.status_code}")
        except Exception as e:
            print(f"❌ Groq error: {e}")

    if not ai_content and openai_key:
        try:
            print("🤖 Asking OpenAI...")
            resp = session.post("https://api.openai.com/v1/chat/completions",
                                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                                json={"model": "gpt-4o-mini", "messages": payload["messages"]},
                                timeout=60)
            if resp.status_code == 200:
                ai_content = resp.json()['choices'][0]['message']['content']
                print("✅ AI Response received from OpenAI")
            else:
                print(f"⚠ OpenAI returned {resp.status_code}")
        except Exception as e:
            print(f"❌ OpenAI error: {e}")

    # 4) If still nothing, attempt the contest proxy (best-effort fallback)
    if not ai_content and aiproxy_token:
        try:
            print("🤖 Trying contest proxy (best-effort)...")
            try:
                proxy_url = f"https://{AI_PROXY_HOSTNAME}/openai/v1/chat/completions"
                resp = session.post(proxy_url, headers={"Authorization": f"Bearer {aiproxy_token}", "Content-Type": "application/json"},
                                    json=payload, timeout=60, verify=True)
                if resp.status_code == 200:
                    ai_content = resp.json()['choices'][0]['message']['content']
                    print("✅ AI Response via proxy hostname")
            except Exception as e:
                print(f"❌ proxy hostname attempt: {e}")

            if not ai_content:
                try:
                    addrs = socket.getaddrinfo(AI_PROXY_HOSTNAME, 443)
                    ips = sorted({x[4][0] for x in addrs})
                except Exception as e:
                    ips = []
                cand_ips = ips or DIRECT_IPS
                for ip in cand_ips:
                    try:
                        proxy_url = f"https://{ip}/openai/v1/chat/completions"
                        headers_ip = {"Authorization": f"Bearer {aiproxy_token}", "Content-Type": "application/json", "Host": AI_PROXY_HOSTNAME}
                        resp = session.post(proxy_url, headers=headers_ip, json=payload, timeout=60, verify=False)
                        if resp.status_code == 200:
                            ai_content = resp.json()['choices'][0]['message']['content']
                            print("✅ AI Response via IP fallback")
                            break
                    except Exception:
                        continue
        except Exception as e:
            print(f"❌ proxy attempts failed: {e}")

    if not ai_content:
        print("ℹ️ No AI content retrieved; attempting to continue with local handling if possible.")
        ai_content = ""

    # 5) Extract python block if present and run
    code_match = re.search(r"```python(.*?)```", ai_content, re.DOTALL)
    script = code_match.group(1).strip() if code_match else ai_content

    if script:
        print("⚡ Running generated code...")
        answer = run_code(script)
        print(f"💡 Computed Answer: {answer}")
    else:
        answer = ""

    # 6) Normalize answer
    try:
        final_ans = float(answer)
        if final_ans.is_integer():
            final_ans = int(final_ans)
    except Exception:
        final_ans = answer

    # 7) Submit
    submit_payload = {"email": email, "secret": secret, "url": url, "answer": final_ans}
    submit_url = "https://tds-llm-analysis.s-anand.net/submit"
    m = re.search(r"https://[^\s\"']+/submit", html)
    if m:
        submit_url = m.group(0)

    print(f"📤 Submitting to {submit_url}")
    try:
        sub = session.post(submit_url, json=submit_payload, timeout=30, verify=False)
        print(f"✅ Submission result: {sub.status_code}, {sub.text[:400]}")
        try:
            sd = sub.json()
            if sd.get("url"):
                print("🔗 Following next URL")
                process_quiz(sd["url"], email, secret)
            else:
                print("🏁 Finished (no next URL).")
        except Exception:
            print("⚠ Could not parse submission response")
    except Exception as e:
        print(f"❌ Submission failed: {e}")

@app.post("/run")
async def run_task(task: Task, background_tasks: BackgroundTasks):
    if task.secret != "MySuperSecretKey":
        raise HTTPException(status_code=403, detail="Invalid Secret")
    background_tasks.add_task(process_quiz, task.url, task.email, task.secret)
    return {"message": "Task started"}

@app.get("/")
def home():
    return {"status": "running"}
