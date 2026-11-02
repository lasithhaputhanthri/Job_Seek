"""
Phase 9: A2A (Agent-to-Agent) Service.
Runs the Contact Finder as an isolated network service declaring an Agent Card.
Strict Ground Rule: Zero fabricated emails or domains. Reuses ContactFinderWorker
and only returns contacts with authentic source URLs where the email was visibly listed.
"""

import json
from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from src.agents.contact_finder import ContactFinderWorker
from src.db import StateDatabase

AGENT_CARD_PATH = Path(__file__).parent / "agent_card.json"
_shared_db = StateDatabase()


async def get_agent_card(request):
    """Exposes the Agent Card for dynamic discovery."""
    with open(AGENT_CARD_PATH, "r", encoding="utf-8") as f:
        card = json.load(f)
    return JSONResponse(card)


async def health(request):
    return JSONResponse({"status": "healthy", "service": "contact-finder-a2a"})


async def handle_rpc(request):
    """JSON-RPC 2.0 delegation handler for A2A communication."""
    try:
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id", 1)

        if method == "find_hiring_contacts":
            domain = params.get("domain", "")
            comp_name = params.get("company_name", "")
            careers_url = params.get("careers_url", "")

            if not domain and not careers_url:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Missing domain or careers_url in params."},
                }, status_code=400)

            # Delegate to real ContactFinderWorker (Strict: zero fabricated emails!)
            worker = ContactFinderWorker(db=_shared_db)
            company_info = {
                "id": None,
                "name": comp_name or domain,
                "domain": domain,
                "careers_url": careers_url,
            }
            real_contacts = worker.find_contacts_for_company(company_info)

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "status": "success",
                    "company": comp_name,
                    "contacts": real_contacts,
                    "count": len(real_contacts),
                    "a2a_agent": "urn:agent:contact-finder-v2",
                },
            })
        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found in Agent Card."},
            }, status_code=404)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


routes = [
    Route("/.well-known/agent-card.json", get_agent_card),
    Route("/agent-card", get_agent_card),
    Route("/health", health),
    Route("/rpc", handle_rpc, methods=["POST"]),
]

app = Starlette(routes=routes)


def run_server(port: int = 8765):
    print(f"[A2A Service] Starting ContactFinder A2A Service on http://127.0.0.1:{port}...")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run_server()
