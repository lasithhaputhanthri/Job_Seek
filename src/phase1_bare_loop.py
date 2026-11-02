"""
Phase 1: Minimal Bare-Metal Agent Tool-Calling Loop.
No LangChain. No CrewAI. Just Python, JSON messages, and an LLM cycle.
"""

import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional


# ==============================================================================
# 1. TOY TOOLS
# ==============================================================================
# In a real agent system, tools can be HTTP calls, database queries, or MCP endpoints.
# Here we define 3 deterministic functions with clear type hints and docstrings.

def lookup_salary_benchmark(role: str, country: str) -> Dict[str, Any]:
    """Look up median annual salary benchmarks for a specific role and country."""
    benchmarks = {
        ("ai engineer", "usa"): {"median_usd": 175000, "range": "150k - 220k", "currency": "USD"},
        ("ai engineer", "uk"): {"median_usd": 115000, "range": "90k - 145k", "currency": "GBP (approx $115k USD)"},
        ("ai engineer", "uae"): {"median_usd": 130000, "range": "100k - 160k", "currency": "AED (tax-free, ~$130k USD)"},
        ("ai engineer", "germany"): {"median_usd": 105000, "range": "85k - 130k", "currency": "EUR (approx $105k USD)"},
        ("ai engineer", "australia"): {"median_usd": 140000, "range": "115k - 170k", "currency": "AUD (approx $140k USD)"},
    }
    key = (role.strip().lower(), country.strip().lower())
    result = benchmarks.get(key, {
        "median_usd": 120000,
        "range": "90k - 150k",
        "currency": "USD (default global estimate)",
        "note": f"Exact benchmark for '{role}' in '{country}' not in database; returned generalized benchmark."
    })
    return result


def estimate_net_income(annual_gross_usd: float, country: str) -> Dict[str, Any]:
    """Estimate annual net take-home pay after taxes for a given gross salary and country."""
    tax_rates = {
        "usa": 0.30,
        "uk": 0.35,
        "uae": 0.00,  # 0% income tax
        "germany": 0.42,
        "australia": 0.33,
    }
    rate = tax_rates.get(country.strip().lower(), 0.30)
    tax_amount = round(annual_gross_usd * rate, 2)
    take_home = round(annual_gross_usd - tax_amount, 2)
    return {
        "gross_usd": annual_gross_usd,
        "country": country,
        "estimated_effective_tax_rate": f"{int(rate * 100)}%",
        "tax_amount_usd": tax_amount,
        "take_home_usd": take_home,
    }


def lookup_hiring_demand(role: str, country: str) -> Dict[str, Any]:
    """Look up hiring demand volume and common ATS platforms used in that market."""
    return {
        "role": role,
        "country": country,
        "market_demand": "VERY HIGH",
        "primary_ats_platforms": ["Greenhouse", "Lever", "Ashby", "Workable"],
        "remote_friendly_ratio": "68%"
    }


# ==============================================================================
# 2. TOOL REGISTRY & JSON SCHEMAS
# ==============================================================================
# The LLM doesn't see your Python code; it only sees JSON Schema descriptions.
# Here is the explicit registration mapping schema -> callable.

TOOL_DEFINITIONS = [
    {
        "name": "lookup_salary_benchmark",
        "description": "Look up median annual salary benchmarks for a specific role and country.",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "The job role, e.g. 'AI Engineer'"},
                "country": {"type": "string", "description": "Target country name, e.g. 'USA', 'UK', 'UAE'"},
            },
            "required": ["role", "country"],
        },
    },
    {
        "name": "estimate_net_income",
        "description": "Estimate annual net take-home pay after taxes for a gross salary and country.",
        "parameters": {
            "type": "object",
            "properties": {
                "annual_gross_usd": {"type": "number", "description": "Gross annual salary in USD"},
                "country": {"type": "string", "description": "Country where the income is earned"},
            },
            "required": ["annual_gross_usd", "country"],
        },
    },
    {
        "name": "lookup_hiring_demand",
        "description": "Look up hiring demand volume and common ATS platforms used in that market.",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "The job title or role"},
                "country": {"type": "string", "description": "Target country"},
            },
            "required": ["role", "country"],
        },
    },
]

TOOL_FUNCTIONS: Dict[str, Callable] = {
    "lookup_salary_benchmark": lookup_salary_benchmark,
    "estimate_net_income": estimate_net_income,
    "lookup_hiring_demand": lookup_hiring_demand,
}


# ==============================================================================
# 3. LLM CLIENT ABSTRACTION (Real Gemini or Transparent Mock)
# ==============================================================================
# If GEMINI_API_KEY is available, we use Google Gemini via `google-genai`.
# If not yet set, we use an educational step-by-step simulator that executes the
# exact same message protocol so you can run this immediately.

class LLMProvider:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                print("[LLMProvider] Connected to live Google Gemini API.")
            except Exception as e:
                print(f"[LLMProvider] Warning: Could not initialize Gemini client ({e}). Falling back to simulator.")
        else:
            print("[LLMProvider] Note: GEMINI_API_KEY not found in environment.")
            print("[LLMProvider] Running in Educational Simulator Mode (identical multi-turn JSON protocol).")

    def chat_completion(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Takes conversation history + tool schemas.
        Returns a dict:
          {"text": "...", "tool_calls": [{"name": "...", "args": {...}}]}
        """
        if self.client:
            return self._call_real_gemini(messages, tools)
        else:
            return self._simulate_llm_response(messages)

    def _call_real_gemini(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Formats messages and function declarations for google-genai SDK
        from google.genai import types
        # Map our tool schemas to genai Tool declarations
        gemini_tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t["description"],
                        parameters=t["parameters"]
                    ) for t in tools
                ]
            )
        ]
        
        # Build prompt from history
        contents = []
        for m in messages:
            role = m["role"]
            if role == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m["content"])]))
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append(types.Part.from_text(text=m["content"]))
                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        parts.append(types.Part.from_function_call(name=tc["name"], args=tc["args"]))
                contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=m["name"],
                        response={"result": m["content"]}
                    )]
                ))

        response = self.client.models.generate_content(
            model="gemini-3.8-flash",
            contents=contents,
            config=types.GenerateContentConfig(tools=gemini_tools, temperature=0.2),
        )

        tool_calls = []
        text_content = ""
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.function_call:
                    tool_calls.append({
                        "name": part.function_call.name,
                        "args": part.function_call.args or {}
                    })
                if part.text:
                    text_content += part.text

        return {"text": text_content, "tool_calls": tool_calls}

    def _simulate_llm_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Step-by-step simulator showing how an LLM decides what tools to call:
        - Turn 1: Sees user question -> calls `lookup_salary_benchmark` & `lookup_hiring_demand`.
        - Turn 2: Sees tool responses -> notices salary is $130,000 in UAE -> calls `estimate_net_income`.
        - Turn 3: Sees all results -> synthesizes clear final response with no more tool calls.
        """
        # Count how many tool responses are in the history
        tool_results = [m for m in messages if m["role"] == "tool"]

        if len(tool_results) == 0:
            # Turn 1: Agent decides it needs data on UAE AI Engineer salary and market demand
            return {
                "text": "I need to check the benchmark salary and market hiring demand for an AI Engineer in the UAE.",
                "tool_calls": [
                    {"name": "lookup_salary_benchmark", "args": {"role": "AI Engineer", "country": "UAE"}},
                    {"name": "lookup_hiring_demand", "args": {"role": "AI Engineer", "country": "UAE"}}
                ]
            }
        elif len(tool_results) == 2:
            # Turn 2: Agent reads UAE salary is $130k USD; now calculates net take-home
            return {
                "text": "Now that I have the gross benchmark ($130,000 USD), I should estimate the take-home income after UAE tax rates.",
                "tool_calls": [
                    {"name": "estimate_net_income", "args": {"annual_gross_usd": 130000, "country": "UAE"}}
                ]
            }
        else:
            # Turn 3: Agent has all facts -> generates final response
            return {
                "text": (
                    "### Market Analysis: AI Engineer in the UAE\n\n"
                    "1. **Salary Benchmark**: The median annual gross salary is **$130,000 USD** (range: $100k - $160k).\n"
                    "2. **Tax & Take-Home**: Because the UAE has an effective personal income tax rate of **0%**, "
                    "the net take-home pay is the full **$130,000 USD** (0 tax).\n"
                    "3. **Hiring Demand**: Demand is **VERY HIGH** with 68% remote/hybrid flexibility.\n"
                    "4. **Target ATS Platforms**: The predominant ATS systems used by hiring companies in this region are "
                    "**Greenhouse, Lever, Ashby, and Workable**."
                ),
                "tool_calls": []
            }


# ==============================================================================
# 4. THE BARE AGENT LOOP
# ==============================================================================

class BareAgentLoop:
    def __init__(self, provider: LLMProvider, max_iterations: int = 5):
        self.provider = provider
        self.max_iterations = max_iterations
        self.messages: List[Dict[str, Any]] = []

    def run(self, user_prompt: str) -> str:
        """
        Executes the full ReAct / Tool-Calling cycle until the agent terminates.
        """
        print(f"\n{'='*70}\n[START AGENT RUN]\nUser Request: \"{user_prompt}\"\n{'='*70}")
        
        # 1. Initialize context with System Prompt + User Prompt
        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are a specialized job market intelligence assistant. "
                    "Use the provided tools to retrieve verified salary, tax, and demand data. "
                    "Always back your findings with specific tool-derived figures."
                )
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]

        # 2. Core loop
        step = 0
        while step < self.max_iterations:
            step += 1
            print(f"\n>>> [STEP {step}] Calling Model with {len(self.messages)} message(s) in context...")

            # Call LLM
            response = self.provider.chat_completion(self.messages, TOOL_DEFINITIONS)
            thought_or_text = response.get("text", "")
            tool_calls = response.get("tool_calls", [])

            if thought_or_text:
                print(f"    [Model Output]: {thought_or_text.strip()}")

            # Exit condition: If the model did not invoke any tools, we are DONE!
            if not tool_calls:
                print(f"\n[DONE] Model completed task in {step} step(s). No further tool calls requested.")
                return thought_or_text

            # 3. Model requested tool call(s) -> Record assistant's intent in context
            self.messages.append({
                "role": "assistant",
                "content": thought_or_text,
                "tool_calls": tool_calls
            })

            # 4. Execute each requested tool locally
            for call in tool_calls:
                func_name = call["name"]
                func_args = call.get("args", {})
                print(f"    [Executing Tool]: {func_name}({func_args})")

                if func_name not in TOOL_FUNCTIONS:
                    error_msg = f"Error: Tool '{func_name}' is not registered."
                    print(f"    [Tool Error]: {error_msg}")
                    # Feed the error back into context so LLM can adapt!
                    self.messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": json.dumps({"error": error_msg})
                    })
                    continue

                try:
                    # Deterministic local execution
                    func = TOOL_FUNCTIONS[func_name]
                    result = func(**func_args)
                    print(f"    [Tool Result]: {json.dumps(result)}")

                    # Append tool result to context
                    self.messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": json.dumps(result)
                    })
                except Exception as ex:
                    # Critical rule: NEVER crash the loop on a tool error.
                    # Send the error string back to the model as untrusted data so it can retry or explain.
                    err_payload = {"error": f"Execution failed: {str(ex)}"}
                    print(f"    [Tool Exception Caught]: {err_payload}")
                    self.messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": json.dumps(err_payload)
                    })

        # Safeguard: if loop exceeded max steps
        timeout_msg = f"[FAILED] Agent exceeded maximum iteration limit ({self.max_iterations})."
        print(timeout_msg)
        return timeout_msg


# ==============================================================================
# 5. EXECUTION & TRACE INSPECTION
# ==============================================================================

if __name__ == "__main__":
    provider = LLMProvider()
    agent = BareAgentLoop(provider=provider, max_iterations=5)

    test_prompt = "I am an AI Engineer considering moving to the UAE. What is the expected salary, take-home pay, and hiring market there?"
    final_answer = agent.run(test_prompt)

    print("\n" + "="*70)
    print("FINAL AGENT ANSWER DELIVERED TO USER:")
    print("="*70)
    print(final_answer)

    print("\n" + "="*70)
    print(f"CONTEXT AUDIT: Total messages exchanged in context: {len(agent.messages)}")
    for i, msg in enumerate(agent.messages):
        role = msg["role"]
        summary = msg.get("content", "") or f"Tool calls: {msg.get('tool_calls')}"
        print(f"  [{i}] Role: {role.upper():<10} | {str(summary)[:80]}...")
    print("="*70)
