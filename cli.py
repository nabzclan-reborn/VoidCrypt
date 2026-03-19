# VoidCrypt CLI - Test client for the privacy proxy
# Copyright (c) 2026 Nabzclan
# MIT License - https://github.com/nabzclan-reborn/VoidCrypt

"""
Lets you chat through the encrypted proxy from the terminal.
"""

import os
import sys
import json
import argparse
import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE = "http://localhost:8400"
DEFAULT_MODEL = "openrouter/auto"


def chat(base_url: str, model: str, messages: list[dict], stream: bool = True):
    """Send a chat completion request through VoidCrypt."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    if stream:
        with httpx.Client(timeout=120) as client:
            with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status_code != 200:
                    print(f"Error {resp.status_code}: {resp.read().decode()}")
                    return None

                full_response = ""
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            print(content, end="", flush=True)
                            full_response += content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass
                print()
                return full_response
    else:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                print(f"Error {resp.status_code}: {resp.text}")
                return None
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            print(content)

            # Show privacy metadata if available
            vc = result.get("_voidcrypt")
            if vc:
                print(f"\n--- VoidCrypt: {vc['entities_redacted']} entities redacted ---")
            return content


def check_health(base_url: str):
    """Check proxy health."""
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5)
        data = resp.json()
        print(f"Status: {data['status']}")
        if data.get("vault_stats"):
            stats = data["vault_stats"]
            print(f"Vault: {stats['total_entities']} entities stored")
            for t, c in stats.get("by_type", {}).items():
                print(f"  - {t}: {c}")
    except httpx.ConnectError:
        print(f"Cannot connect to VoidCrypt at {base_url}")
        sys.exit(1)


def show_audit(base_url: str, limit: int = 20):
    """Show recent audit log."""
    resp = httpx.get(f"{base_url}/v1/audit", params={"limit": limit}, timeout=10)
    entries = resp.json()
    if not entries:
        print("No audit entries yet.")
        return
    for entry in entries:
        print(f"\n[{entry['timestamp']}] Request {entry['request_id']}:")
        for r in entry["redactions"]:
            print(f"  {r['type']} → {r['token']}")


def interactive(base_url: str, model: str):
    """Interactive chat mode."""
    print("=" * 50)
    print("  VoidCrypt - Private AI Chat")
    print("  Your messages are encrypted before reaching the LLM")
    print("=" * 50)
    print(f"  Model: {model}")
    print(f"  Proxy: {base_url}")
    print("  Type 'quit' to exit, 'audit' to see redactions")
    print("=" * 50)

    messages = []
    system_prompt = input("\nSystem prompt (Enter to skip): ").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    while True:
        try:
            user_input = input("\n🔒 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "audit":
            show_audit(base_url)
            continue
        if user_input.lower() == "health":
            check_health(base_url)
            continue
        if user_input.lower() == "clear":
            messages = messages[:1] if messages and messages[0]["role"] == "system" else []
            httpx.post(f"{base_url}/v1/vault/clear", timeout=5)
            print("Session cleared.")
            continue

        messages.append({"role": "user", "content": user_input})
        print("\n🤖 AI: ", end="")
        response = chat(base_url, model, messages)
        if response:
            messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VoidCrypt CLI Client")
    parser.add_argument("--base", default=DEFAULT_BASE, help="VoidCrypt proxy URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model to use")
    parser.add_argument("--health", action="store_true", help="Check proxy health")
    parser.add_argument("--audit", action="store_true", help="Show audit log")
    parser.add_argument("--message", "-m", help="Send a single message")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming")

    args = parser.parse_args()

    if args.health:
        check_health(args.base)
    elif args.audit:
        show_audit(args.base)
    elif args.message:
        messages = [{"role": "user", "content": args.message}]
        chat(args.base, args.model, messages, stream=not args.no_stream)
    else:
        interactive(args.base, args.model)
