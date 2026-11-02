"""
Phase 9: A2A Client for the Manager Agent.
Discovers peer agent capabilities via Agent Card and delegates tasks over HTTP JSON-RPC.
"""

from typing import Any, Dict, List
import httpx


class A2AAgentClient:
    def __init__(self, endpoint_url: str = "http://127.0.0.1:8765"):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.agent_card: Dict[str, Any] = {}

    def discover(self) -> Dict[str, Any]:
        """Discovers the remote agent's identity and capabilities via its Agent Card."""
        card_url = f"{self.endpoint_url}/agent-card"
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(card_url)
            if resp.status_code == 200:
                self.agent_card = resp.json()
                print(f"[A2A Client] Discovered peer agent: '{self.agent_card.get('name')}' ({self.agent_card.get('agent_id')})")
                return self.agent_card
            else:
                raise RuntimeError(f"Failed to fetch Agent Card from {card_url} (HTTP {resp.status_code})")

    def delegate_contact_search(self, company_name: str, domain: str) -> List[Dict[str, Any]]:
        """Delegates a contact discovery task to the peer agent."""
        if not self.agent_card:
            self.discover()

        rpc_url = f"{self.endpoint_url}/rpc"
        payload = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "find_hiring_contacts",
            "params": {"company_name": company_name, "domain": domain},
        }

        with httpx.Client(timeout=8.0) as client:
            resp = client.post(rpc_url, json=payload)
            if resp.status_code == 200:
                result = resp.json().get("result", {})
                return result.get("contacts", [])
            else:
                print(f"[A2A Error] Remote agent returned HTTP {resp.status_code}")
                return []
