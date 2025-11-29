# TDS Project 2 — LLM Analysis Quiz Agent

This repository contains my implementation for the TDS September 2025 Project 2 (LLM Analysis Quiz).  
I built a FastAPI-based agent that receives quiz tasks from the evaluation server, processes each quiz step, and submits the computed answer back.

The agent follows the behaviour described in the project instructions:
1. Accept a POST request containing `email`, `secret` and the quiz `url`
2. Visit the quiz page with Playwright (pages use JavaScript)
3. Extract the rendered text content
4. Use an LLM endpoint (when available in the environment) to generate solver code
5. Detect Python code returned inside ```python ... ``` blocks
6. Execute it safely in a temporary subprocess
7. Submit `{ email, secret, url, answer }` to the grader
8. Continue following the next URL until the quiz ends

This is the code I developed and tested for the project.

---

## Repository Contents

### **main.py**
The FastAPI application that implements:
- `/run` endpoint  
- scraping with Playwright  
- LLM request logic  
- code extraction and execution  
- answer submission  
- recursion through quiz URLs  

### **requirements.txt**
Python dependencies used by the agent.

### **Dockerfile**
Container definition used for deployment  
(sets up Python, Playwright, and launches the FastAPI server).

### **LICENSE**
MIT license as required by the project.

No keys or secrets are included in this repository; they were supplied at runtime as environment variables.

---

## Running during development 

During testing, I used the following:

python -m venv venv
source venv/bin/activate # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --host 0.0.0.0 --port 7860


---

## Notes

This repository contains only the necessary components of the agent.  
Local helper files used during practice are intentionally not included.
