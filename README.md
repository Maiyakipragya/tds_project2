# TDS Project 2 — LLM Analysis Quiz Agent

This repository contains my implementation for the TDS September 2025 Project 2 (LLM Analysis Quiz).  
I built a FastAPI-based agent that receives quiz tasks, processes the task page, generates or executes solver code, and submits the answer back to the evaluation server.

All secrets/keys are provided at runtime through environment variables. None are stored in this repository.

---

## ✦ What this agent does

The agent implements the workflow required in the project:

1. Accepts a POST request with:
   - `email`
   - `secret`
   - `url` (the quiz step)
2. Scrapes the quiz page using **Playwright** (JavaScript-rendered)
3. Sends the extracted text to an LLM (Groq / OpenAI, if available)
4. Extracts any Python code returned in a ```python ... ``` block
5. Executes the code safely in a sandboxed subprocess
6. Submits `{ email, secret, url, answer }` to the quiz server
7. Follows chained quiz URLs recursively until the quiz ends

The design matches the specification in the project documentation.

---

## ✦ Running locally (optional)

I used the following setup while developing and testing my agent:

1. Create and activate a virtual environment:
   python -m venv venv
   source venv/bin/activate        # Windows: .\venv\Scripts\activate

2. Install dependencies:
   pip install -r requirements.txt
   playwright install chromium

3. (Optional) Set your LLM keys as environment variables:
   export GROQ_API_KEY="..."
   export OPENAI_API_KEY="..."

This is only for development/debugging. The evaluation itself uses the deployed endpoint.

