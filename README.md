# LLM Council

> All tet before the setup section is hand written by me (valentino), so please spend some time reading it as I have explained why this app is what it is and how you can use it.

An unlinked fork from https://github.com/karpathy/llm-council

### What is this app?
The idea of this repository is to create an LLM council application that takes a question from the user and spins up a bunch of predefined models to answer them without any system prompts - so in a more raw fashion. These spun up models then analyze each other answers and rank which answer suits the best to the user's question. The analysis is then passed onto a chairmain model (anchor model, final model) that aggregates the information and comes up with a final result after refining on already done analysis. 

The benefit of using this application is that you are 100% confident that the council final answer is an answer of the highest order of quality that today's llms can provide. 

### Why does this app matter?

Being an avid user of LLMs, we get accustomed to become selective about source of truth. For example - if my model XYZ said this, it must be true. It might be but thats not always the case because LLMs work by predicting the next token via complicated architectures of neural network mapping. Therefore, response from a single model will always be different each time due to its non-deterministic nature and at times - there are chances of missed meanings and facts that could result in a whole different answer. 

This concept of an LLM council is meant to bust this source of truth myth by collecting answers from multiple LLMs, competeting them with each other and declaring a winner based on their own evaluations. Its sort of what people do in a parliament and come up with a final bill. This way, you get to see the whole picture of what an LLM said, what was lacking in it and how other LLMs fill in the knowledge gap at times. The LLM council is supposed to give you an wholesome response that you can easily consider *a worthy source of truth* - but not the actual source of truth because we have to always assume -- machines are controlled by the ones selling it. 

### How the models were chosen

So I focused on picking models that performed among the top  5 in the benchmarks from artificialanalysis.ai website. The benchmarks I picked were:
1. Humanity's last exam (toughest questions that require high quality reasoning & knowledge)
2. GPQA Diamond (scientific reasoning)
3. CritPt (physics reasoning)
4. AA-Omniscience Accuracy (similar to #1, but more knowledge based)

The reason for picking these benchmarks was that I wanted to make sure that those LLMs that were sourced from high quality data and could understand tough questions and synthesize information in a way that would benefit our app's end users the most as explained in the next section. So in short - they are strong in language, science, math, philosophy and common human knowledge from a benchmark standpoint and our budget. 

### How we expect our users of this app to use it
- Doing fact checking like "hey someone told me XYZ, how much of it is true?", "i need a way to lose weight, does XYZ work?" etc. 
- Getting answers to the world's most curious questions like "what is love?", "what is life?", "are we alone in the universe?" etc.
- Scientific and mathematical answers - post your hardest science questions like "why is the volume of cone XYZ?", "what does methane react with?", "give me a formula to make my algorithm faster" etc.

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Configure API Key

Create a `.env` file in the project root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

Get your API key at [openrouter.ai](https://openrouter.ai/). Make sure to purchase the credits you need, or sign up for automatic top up.

### 3. Simulated Model Mode (Optional — for UI testing)

You can run the app without making any OpenRouter API calls by adding these to `.env`:

```bash
USE_SIMULATED_MODELS=true
SIMULATED_MODEL_DELAY_S=0.5
```

This returns synthetic council responses, so you can test loaders, stage tabs, rankings, and the SSE stream without spending credits. The delay controls how long each fake model call sleeps to mimic real inference.

### 4. Configure Models (Optional)

Edit `backend/config.py` to customize the council:

```python
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
```

## Running the Application

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter SDK
- **Frontend:** React + Vite, react-markdown for rendering
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript
