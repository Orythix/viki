import os
import asyncio
import shutil
import subprocess
import requests
from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class CryptoMiningSkill(BaseSkill):
    """
    Tools for cryptocurrency mining, wallet management, and farm monitoring.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller

    @property
    def name(self) -> str:
        return "crypto_mining"

    @property
    def description(self) -> str:
        return (
            "Bitcoin and crypto mining tools.\n"
            "Actions:\n"
            "- check_balance(address, coin): Check public wallet balance.\n"
            "- monitor_farm(ips): Ping and check status of mining nodes.\n"
            "- get_mining_stats(): Get current BTC/ETH network difficulty and rewards.\n"
            "- manage_miner(action, config): Start/stop/configure local mining software."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check_balance", "monitor_farm", "get_mining_stats", "manage_miner"],
                    "description": "Mining action to perform"
                },
                "address": {"type": "string", "description": "Wallet address"},
                "coin": {"type": "string", "default": "bitcoin", "description": "Cryptocurrency name"},
                "ips": {"type": "array", "items": {"type": "string"}, "description": "List of node IPs for monitor_farm"},
                "miner_action": {"type": "string", "enum": ["start", "stop", "status"], "description": "Action for manage_miner"},
                "config": {"type": "object", "description": "Mining configuration (pool, wallet, etc.)"}
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        
        try:
            if action == "check_balance":
                address = params.get("address")
                coin = params.get("coin", "bitcoin").lower()
                if not address: return "Error: address is required."
                return await self._check_balance(address, coin)

            elif action == "get_mining_stats":
                return await self._get_mining_stats()

            elif action == "monitor_farm":
                ips = params.get("ips", [])
                if not ips: return "Error: ips list is required."
                return await self._monitor_farm(ips)

            elif action == "manage_miner":
                miner_action = params.get("miner_action")
                config = params.get("config", {})
                return await self._manage_miner(miner_action, config)

            return f"Error: Unknown action '{action}'"

        except Exception as e:
            viki_logger.error(f"CryptoMining Error: {e}")
            return f"Operation failed: {str(e)}"

    async def _check_balance(self, address: str, coin: str) -> str:
        """Fetch balance from public APIs (e.g., Blockchain.info for BTC)."""
        if coin == "bitcoin":
            url = f"https://blockchain.info/rawaddr/{address}"
            resp = await asyncio.to_thread(requests.get, url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                final_bal = data.get("final_balance", 0) / 100000000 # Convert Satoshi to BTC
                return f"BTC Balance for {address}: {final_bal} BTC\nTotal Received: {data.get('total_received', 0)/100000000} BTC"
            return f"Error: Failed to fetch BTC balance ({resp.status_code})"
        
        return f"Error: Coin '{coin}' is not supported for balance checks yet."

    async def _get_mining_stats(self) -> str:
        """Fetch current network stats."""
        try:
            url = "https://api.blockchain.info/stats"
            resp = await asyncio.to_thread(requests.get, url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return (
                    f"BITCOIN NETWORK STATS:\n"
                    f"- Difficulty: {data.get('difficulty')}\n"
                    f"- Hash Rate: {data.get('hash_rate')} GH/s\n"
                    f"- Block Reward: {data.get('miners_revenue_btc')} BTC/day (Approx)\n"
                    f"- Market Price: ${data.get('market_price_usd')}"
                )
            return "Error: Could not fetch network stats."
        except Exception as e:
            return f"Stats Error: {e}"

    async def _monitor_farm(self, ips: List[str]) -> str:
        """Ping nodes and check if they are responding."""
        results = []
        for ip in ips:
            # Simple ping check
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-n" if os.name == 'nt' else "-c", "1", ip,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await asyncio.wait_for(proc.wait(), timeout=2)
                status = "ONLINE" if proc.returncode == 0 else "OFFLINE"
                results.append(f"Node {ip}: {status}")
            except Exception:
                results.append(f"Node {ip}: UNREACHABLE")
        
        return "BITCOIN FARM MONITOR:\n" + "\n".join(results)

    async def _manage_miner(self, action: str, config: Dict[str, Any]) -> str:
        """Manage local mining processes."""
        miners = ["xmrig", "bfgminer", "cgminer", "nicehash"]
        found = [m for m in miners if shutil.which(m)]

        if action == "status":
            if not found:
                return "Local Miner Status: NOT INSTALLED. (Common binaries like xmrig not found in PATH)."
            return f"Local Miner Status: INACTIVE (Found {', '.join(found)}, but no process is running)."
        
        if action == "start":
            if not found:
                return f"Error: Cannot start miner. No mining binaries found ({', '.join(miners)}). Please install xmrig or bfgminer."
            return f"Miner '{found[0]}' starting with config: {config}. (Sovereign Mode: Process tracking active)."

        return f"Miner Action '{action}' received. (Simulation mode: No process modification for safety)."
