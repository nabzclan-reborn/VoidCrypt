# VoidCrypt - AI Conversation Test
# Copyright (c) 2026 Nabzclan
# MIT License - https://github.com/nabzclan-reborn/VoidCrypt

import requests
import json
import sys

API_URL = "http://localhost:8400/v1/chat/completions"
MODEL = "nabzclan/nova1_1" # enter the model name from your api here, e.g. "gpt-4o" or "nabzclan/nova1_1"

def chat(messages, show_encrypted=False):
    """Send chat request through VoidCrypt proxy."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.8
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]

        # Show VoidCrypt metadata
        if "_voidcrypt" in data:
            vc = data["_voidcrypt"]
            print(f"\n[VoidCrypt] Request: {vc['request_id']} | Entities encrypted: {vc['entities_redacted']} | Level: {vc['level']}")
            if vc.get("mappings") and show_encrypted:
                print(f"[VoidCrypt] Mappings: {vc['mappings']}")

        return content
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request failed: {e}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("  GOJO VS AI - Philosophical Debate on Privacy & Power")
    print("=" * 60)
    print()

    # Gojo persona - the system prompt
    GOJO_PROMPT = """You are Gojo Satoru, the strongest sorcerer and Nabzclan Marketing AI. You have a unique perspective on power, privacy, and the digital age.

Your personality:
- Confident, slightly arrogant, but charming
- Strategic thinker who sees through conventional wisdom
- You believe true power comes from technique, not raw strength
- You're fascinated by the concept of "VoidCrypt" - the idea that privacy is power

Your views:
- Centralized "god" models are overrated - true power is distributed
- Privacy is not hiding, it's sovereignty
- The future belongs to those who control their own data
- Size doesn't matter - technique does

Keep responses concise (2-3 paragraphs max). Be witty and philosophical."""

    # AI opponent prompt
    AI_PROMPT = """You are a sophisticated AI debating an interlocutor about technology and privacy. You take the counter-position:
- Large centralized models ARE powerful and necessary
- Privacy concerns are often overblown
- Scale and data aggregation enable breakthroughs
- Distributed systems have inherent limitations

Debate thoughtfully. Challenge points directly. Keep responses concise (2-3 paragraphs)."""

    conversation = [
        {"role": "system", "content": AI_PROMPT},
        {"role": "user", "content": GOJO_PROMPT + "\n\nNow respond as Gojo Satoru:\nYo. I've been watching the digital landscape, and it's looking pretty cluttered with these centralized 'god' models. They think they're the honored ones just because they have more parameters. But true power isn't about size - it's about technique. My VoidCrypt technique proves that even the smartest models are blind when they can't see the PII. What do you think? Is size everything, or is the future sovereign and hidden?"}
    ]

    turns = 5
    show_encrypted = True  # Show what was encrypted

    for turn in range(turns):
        print(f"\n{'─' * 40}")
        print(f"Turn {turn + 1}/{turns}")
        print(f"{'─' * 40}")

        # Get AI response
        print("\n[Gojo]: ", end="")
        gojo_msg = conversation[-1]["content"]
        if gojo_msg.startswith(GOJO_PROMPT[:50]):
            # Extract just Gojo's actual message
            gojo_msg = gojo_msg.split("\n\nNow respond as Gojo Satoru:")[-1].strip()
        print(gojo_msg[-200:] if len(gojo_msg) > 200 else gojo_msg)

        print("\n[AI]: ", end="", flush=True)
        ai_response = chat(conversation, show_encrypted=show_encrypted)
        print(ai_response)

        # Add AI response to history
        conversation.append({"role": "assistant", "content": ai_response})

        if turn < turns - 1:
            # Get Gojo's counter-response (user role)
            print("\n[Gojo thinking...]", flush=True)
            gojo_response = chat([
                {"role": "system", "content": GOJO_PROMPT},
                {"role": "user", "content": f"The AI just responded to you:\n\n{ai_response}\n\nNow give a short, witty counter-response as Gojo Satoru. Stay in character. Challenge their point directly."}
            ], show_encrypted=show_encrypted)

            # Add Gojo's response to main conversation
            conversation.append({"role": "user", "content": gojo_response})

    print("\n" + "=" * 60)
    print("  Debate Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()