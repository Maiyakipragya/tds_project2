# main.py
import os
import json
import httpx
import subprocess
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from openai import OpenAI
from playwright.sync_api import sync_playwright

app = FastAPI()

client = OpenAI(
    api_key=os.environ.get("AIPROXY_TOKEN"),
    base_url="http://aiproxy.sanandworkers.workers.dev/openai/v1"
)

class Task(BaseModel):
    email: str
    secret: str
    url: str

def run_code(script):
    with open("solver.py", "w") as f:
        f.write(script)
    
    try:
        result = subprocess.run(["python", "solver.py"], capture_output=True, text=True, timeout=20)
        return result.stdout.strip()
    except Exception as e:
        return str(e)

def get_page_text(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        content = page.content()
        text = page.inner_text("body")
        browser.close()
        return content, text

def process_quiz(url, email, secret):
    print(f"Processing {url}")
    html, text = get_page_text(url)
    
    # Simple extraction prompt
    msgs = [
        {"role": "system", "content": "You are a python coding assistant. Return only python code in markdown blocks."},
        {"role": "user", "content": f"Here is a webpage text:\n{text}\n\nWrite a python script to solve the question asked. Print the answer. Use httpx for downloading and pandas for data."}
    ]
    
    resp = client.chat.completions.create(model="gpt-4o-mini", messages=msgs)
    content = resp.choices[0].message.content
    
    import re
    code = re.search(r"```python(.*?)```", content, re.DOTALL)
    if code:
        script = code.group(1).strip()
    else:
        script = content

    answer = run_code(script)
    print(f"Computed answer: {answer}")

    # Try to clean answer
    try:
        final_ans = float(answer)
        if final_ans.is_integer():
            final_ans = int(final_ans)
    except:
        final_ans = answer

    # Submit
    # Assuming standard submit format based on project docs
    submit_payload = {
        "email": email,
        "secret": secret,
        "url": url,
        "answer": final_ans
    }
    
    # We guess the submit URL is usually the base domain + /submit or similar
    # For the project, the submit URL is dynamic, but for this basic setup we will try to extract it
    # or just use the common submission endpoint if known. 
    # To be safe, we ask LLM to find the submit URL from HTML.
    
    url_prompt = f"Find the submission URL and parameter name in this HTML. Return JSON {{'url': '...', 'param': '...'}}: {html[:2000]}"
    url_resp = client.chat.completions.create(
        model="gpt-4o-mini", 
        messages=[{"role": "user", "content": url_prompt}],
        response_format={"type": "json_object"}
    )
    url_data = json.loads(url_resp.choices[0].message.content)
    submit_url = url_data.get("url")

    if submit_url:
        httpx.post(submit_url, json=submit_payload)

@app.post("/run")
async def run_task(task: Task, background_tasks: BackgroundTasks):
    # Change this secret to whatever you put in the Google Form
    if task.secret != "MySuperSecretKey": 
        raise HTTPException(status_code=403, detail="Wrong secret")
    
    background_tasks.add_task(process_quiz, task.url, task.email, task.secret)
    return {"message": "Task started"}

@app.get("/")
def read_root():
    return {"status": "running"}