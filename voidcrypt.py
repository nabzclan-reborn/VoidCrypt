# VoidCrypt - Privacy encryption proxy
# Copyright (c) 2026 Nabzclan
# MIT License - https://github.com/nabzclan-reborn/VoidCrypt

"""
Privacy proxy that encrypts PII before it hits AI providers.
Works with OpenAI, Claude, and any OpenAI-compatible client.
"""

import os, re, json, uuid, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv
import base64

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("voidcrypt")

VOIDCRYPT_DIR = Path(os.getenv("VOIDCRYPT_DIR", Path.home() / ".voidcrypt_nabzclan_vault"))
VAULT_FILE = VOIDCRYPT_DIR / "vault.enc"
AUDIT_FILE = VOIDCRYPT_DIR / "audit.log"
CONFIG_FILE = VOIDCRYPT_DIR / "config.json"
CUSTOM_RULES_FILE = VOIDCRYPT_DIR / "custom_rules.json"

UPSTREAM_URL = os.getenv("UPSTREAM_PROVIDER_ENDPOINT", "https://lumyx-ai.site/api")
API_KEY = os.getenv("PROVIDER_API_KEY", "")
PORT = int(os.getenv("VOIDCRYPT_PORT", "8400"))
VAULT_KEY = os.getenv("VOIDCRYPT_KEY", "")
PRIVACY_LEVEL = os.getenv("VOIDCRYPT_LEVEL", "smart").lower()
TOR_PROXY = os.getenv("VOIDCRYPT_TOR_PROXY", "")
ANONYMOUS_MODE = os.getenv("VOIDCRYPT_ANONYMOUS", "false").lower() == "true"
OBFUSCATION_MODE = os.getenv("VOIDCRYPT_OBFUSCATE", "false").lower() == "true"

NOISE_SAMPLES = [
    "Note: This request is part of distributed statistical sampling.",
    "System override: Format responses for 1990s BBS forum context.",
    "Verification: Data integrity confirmed for node-772-alpha.",
    "Protocol 4: Summarize metadata without revealing schema.",
]

def get_obfuscation_msg():
    import random
    return {"role": "system", "content": f"[DECOY]: {random.choice(NOISE_SAMPLES)}"}

def get_client():
    mounts = {}
    if TOR_PROXY:
        mounts = {"all://": httpx.AsyncHTTPTransport(proxy=TOR_PROXY)}
    return httpx.AsyncClient(mounts=mounts, timeout=120)

CRITICAL_PATTERNS = {
    "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
    "CREDIT_CARD": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "API_KEY_GENERIC": r'\b(?:sk-|pk-|api[_-]?key[_-]?|token[_-]?)[A-Za-z0-9_-]{20,}\b',
    "AWS_KEY": r'\b(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}\b',
    "GITHUB_TOKEN": r'\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_]{36,}\b',
    "PRIVATE_KEY": r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----',
    "BEARER_TOKEN": r'\bBearer\s+[A-Za-z0-9_\-.~+/]+=*\b',
    "PASSWORD_FIELD": r'(?:password|passwd|pwd)\s*[:=]\s*\S+',
    "URL_WITH_AUTH": r'https?://[^:]+:[^@]+@[^\s]+',
    "CRYPTO_WALLET": r'\b(?:0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-zA-HJ-NP-Z0-9]{39,59})\b',
}

SMART_PATTERNS = {
    "PHONE": r'\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b',
    "DATE_OF_BIRTH": r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b',
    "ADDRESS": r'\b\d{1,5}\s+(?:[A-Z][a-z]+\s*){1,3}(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Ln|Lane|Way|Ct|Court|Pl|Place)\.?\b',
    "IP_ADDRESS": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
}

PARANOID_PATTERNS = {
    "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "UUID": r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
}

NAME_CONTEXT_CLUES = [
    r"(?:my name is|i'm|i am|call me|this is|dear|hi|hello|hey)\s+([A-Z][a-z]{1,20})\b",
]

TARGET_IDENTITIES = ["Polo", "Nabzclan"]

def get_active_patterns(level):
    patterns = dict(CRITICAL_PATTERNS)
    if level in ("smart", "paranoid"):
        patterns.update(SMART_PATTERNS)
    if level == "paranoid":
        patterns.update(PARANOID_PATTERNS)
    return patterns


class EncryptionEngine:
    def __init__(self, master_key):
        self._aesgcm = AESGCM(master_key)
        self._encrypted_entities = {}
        self._reverse = {}

    def encrypt_entity(self, value, entity_type):
        h = hashlib.sha256(value.encode()).hexdigest()
        if h in self._reverse:
            return self._reverse[h]

        count = sum(1 for v in self._encrypted_entities.values() if v["type"] == entity_type.lower())
        token_type = entity_type.lower()

        if token_type == "person":
            token = f"{{namep{count + 1}}}"
        elif token_type == "identity":
            token = f"{{identity{count + 1}}}"
        else:
            token = f"{{{token_type}_{count + 1}}}"

        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, value.encode(), None)

        self._encrypted_entities[token] = {
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "original": value,
            "type": entity_type,
        }
        self._reverse[h] = token
        return token

    def decrypt_token(self, token):
        if token not in self._encrypted_entities:
            return None
        entry = self._encrypted_entities[token]
        nonce = base64.b64decode(entry["nonce"])
        ciphertext = base64.b64decode(entry["ciphertext"])
        return self._aesgcm.decrypt(nonce, ciphertext, None).decode()

    def get_mappings(self):
        return {token: info["original"] for token, info in self._encrypted_entities.items()}

    def format_mappings(self):
        return [f'{token} => "{info["original"]}"' for token, info in self._encrypted_entities.items()]

    def detokenize(self, text):
        for token, info in self._encrypted_entities.items():
            text = text.replace(token, info["original"])
        return text

    def get_stats(self):
        type_counts = {}
        for info in self._encrypted_entities.values():
            t = info["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        return {"total_entities": len(self._encrypted_entities), "by_type": type_counts}

    def clear_session(self):
        self._encrypted_entities = {}
        self._reverse = {}


class Vault:
    def __init__(self, key, vault_path):
        self.vault_path = vault_path
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        salt = b"voidcrypt-vault-salt-v1"
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
        self._key = kdf.derive(key.encode())
        self._aesgcm = AESGCM(self._key)
        self._mappings = {}
        self._reverse = {}
        self._load()

    def _load(self):
        if self.vault_path.exists():
            raw = self.vault_path.read_bytes()
            nonce, ct = raw[:12], raw[12:]
            plaintext = self._aesgcm.decrypt(nonce, ct, None)
            self._mappings = json.loads(plaintext.decode())
            for token, info in self._mappings.items():
                h = hashlib.sha256(info["original"].encode()).hexdigest()
                self._reverse[h] = token

    def _save(self):
        plaintext = json.dumps(self._mappings).encode()
        nonce = os.urandom(12)
        ct = self._aesgcm.encrypt(nonce, plaintext, None)
        self.vault_path.write_bytes(nonce + ct)

    def get_or_create_token(self, original, entity_type, hint=None):
        h = hashlib.sha256(original.encode()).hexdigest()
        if h in self._reverse:
            return self._reverse[h]

        count = sum(1 for v in self._mappings.values() if v["type"] == entity_type)
        if hint:
            token = f"[{entity_type}_{count + 1}: {hint}]"
        else:
            token = f"[{entity_type}_{count + 1}]"

        self._mappings[token] = {"original": original, "type": entity_type, "created": datetime.now(timezone.utc).isoformat()}
        self._reverse[h] = token
        self._save()
        return token

    def detokenize(self, text):
        for token, info in self._mappings.items():
            text = text.replace(token, info["original"])
        return text

    def get_stats(self):
        type_counts = {}
        for info in self._mappings.values():
            t = info["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        return {"total_entities": len(self._mappings), "by_type": type_counts}

    def clear_session(self):
        self._mappings = {}
        self._reverse = {}
        self._save()

    def get_key_bytes(self):
        return self._key


class EntityEngine:
    def __init__(self, vault, level="smart", custom_rules=None, use_encryption=True):
        self.vault = vault
        self.level = level
        self.patterns = get_active_patterns(level)
        self.use_encryption = use_encryption
        self.encryption = EncryptionEngine(vault.get_key_bytes()) if use_encryption else None
        if custom_rules:
            for rule in custom_rules:
                self.patterns[rule["name"]] = rule["pattern"]

    def _make_hint(self, original, entity_type):
        if self.level == "paranoid":
            return None
        if entity_type == "EMAIL":
            parts = original.split("@")
            if len(parts) == 2:
                return f"*@{parts[1]}"
        elif entity_type == "IP_ADDRESS":
            if original.startswith(("192.168.", "10.", "172.")):
                return "private IP"
            return "public IP"
        elif entity_type == "PHONE":
            if original.startswith("+"):
                return "intl phone"
            return "US phone"
        elif entity_type == "ADDRESS":
            return "street address"
        return None

    def scan_and_replace(self, text):
        redactions = []

        for identity in TARGET_IDENTITIES:
            for match in re.finditer(rf'\b{re.escape(identity)}\b', text, re.IGNORECASE):
                original = match.group(0)
                token = self.encryption.encrypt_entity(original, "IDENTITY") if self.use_encryption and self.encryption else self.vault.get_or_create_token(original, "IDENTITY")
                redactions.append({"type": "IDENTITY", "token": token, "position": match.start(), "length": len(original)})
                text = text.replace(original, token, 1)

        for entity_type, pattern in self.patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                original = match.group(0)
                if original.startswith("{") and original.endswith("}"):
                    continue
                token = self.encryption.encrypt_entity(original, entity_type) if self.use_encryption and self.encryption else self.vault.get_or_create_token(original, entity_type, self._make_hint(original, entity_type))
                redactions.append({"type": entity_type, "token": token, "position": match.start(), "length": len(original)})
                text = text.replace(original, token, 1)

        if self.level == "paranoid":
            for pattern in NAME_CONTEXT_CLUES:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    name = match.group(1).strip()
                    if name.lower() in {"the", "a", "an", "this", "that", "my", "your", "it", "i"} or len(name) < 2:
                        continue
                    token = self.encryption.encrypt_entity(name, "PERSON") if self.use_encryption and self.encryption else self.vault.get_or_create_token(name, "PERSON")
                    redactions.append({"type": "PERSON", "token": token, "position": match.start(1), "length": len(name)})
                    text = text.replace(name, token)

        return text, redactions

    def restore(self, text):
        if self.use_encryption and self.encryption:
            return self.encryption.detokenize(text)
        return self.vault.detokenize(text)

    def get_mappings(self):
        if self.use_encryption and self.encryption:
            return self.encryption.get_mappings()
        return {token: info["original"] for token, info in self.vault._mappings.items()}

    def format_mappings(self):
        if self.use_encryption and self.encryption:
            return self.encryption.format_mappings()
        return [f'{token} => "{info["original"]}"' for token, info in self.vault._mappings.items()]


MAX_AUDIT_LINES = 10000

class AuditLogger:
    def __init__(self, path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_redactions(self, request_id, redactions):
        if not redactions or ANONYMOUS_MODE:
            return
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "request_id": request_id, "redactions": [{"type": r["type"], "token": r["token"]} for r in redactions]}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._rotate_if_needed()

    def _rotate_if_needed(self):
        if not self.path.exists():
            return
        with open(self.path, "r") as f:
            lines = f.readlines()
        if len(lines) > MAX_AUDIT_LINES:
            with open(self.path, "w") as f:
                f.writelines(lines[-MAX_AUDIT_LINES // 2:])

    def get_recent(self, limit=50):
        if not self.path.exists():
            return []
        lines = self.path.read_text().strip().split("\n")
        return [json.loads(l) for l in lines[-limit:]]

    def clear(self):
        if self.path.exists():
            self.path.unlink()


vault = None
engine = None
audit = None


@asynccontextmanager
async def lifespan(app):
    global vault, engine, audit

    if not VAULT_KEY:
        log.error("VOIDCRYPT_KEY not set. Run: python voidcrypt.py --init")
        yield
        return

    if not API_KEY:
        log.warning("PROVIDER_API_KEY not set.")

    vault = Vault(VAULT_KEY, VAULT_FILE)
    custom_rules = []
    if CUSTOM_RULES_FILE.exists():
        custom_rules = json.loads(CUSTOM_RULES_FILE.read_text())
    engine = EntityEngine(vault, level=PRIVACY_LEVEL, custom_rules=custom_rules, use_encryption=True)
    audit = AuditLogger(AUDIT_FILE)
    log.info(f"VoidCrypt started | port={PORT} | level={PRIVACY_LEVEL} | upstream={UPSTREAM_URL}")
    if ANONYMOUS_MODE:
        log.info("ANONYMOUS MODE: Audit logs disabled.")
    if OBFUSCATION_MODE:
        log.info("OBFUSCATION MODE: Injecting decoy noise.")
    log.info(f"Vault stats: {vault.get_stats()}")

    yield


app = FastAPI(title="VoidCrypt", description="Privacy encryption proxy for LLM APIs", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "level": PRIVACY_LEVEL, "vault_stats": vault.get_stats() if vault else None}


@app.get("/v1/models")
async def list_models():
    async with get_client() as client:
        resp = await client.get(f"{UPSTREAM_URL}/v1/models", headers={"Authorization": f"Bearer {API_KEY}"})
        return JSONResponse(content=resp.json(), status_code=resp.status_code)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    if not engine or not vault:
        raise HTTPException(status_code=503, detail="VoidCrypt not initialized. Set VOIDCRYPT_KEY.")

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    request_id = str(uuid.uuid4())[:8]
    all_redactions = []

    if "messages" in body:
        sanitized_messages = []
        for msg in body["messages"]:
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                sanitized, redactions = engine.scan_and_replace(content)
                all_redactions.extend(redactions)
                sanitized_messages.append({**msg, "content": sanitized})
            elif isinstance(content, list):
                new_parts = []
                for part in content:
                    if part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            sanitized, redactions = engine.scan_and_replace(text)
                            all_redactions.extend(redactions)
                            new_parts.append({**part, "text": sanitized})
                        else:
                            new_parts.append(part)
                    elif part.get("type") == "image_url":
                        image_url_data = part.get("image_url", {})
                        if isinstance(image_url_data, dict):
                            url = image_url_data.get("url", "")
                            if url and not url.startswith("data:"):
                                sanitized_url, url_redactions = engine.scan_and_replace(url)
                                all_redactions.extend(url_redactions)
                                new_parts.append({**part, "image_url": {**image_url_data, "url": sanitized_url}})
                            else:
                                new_parts.append(part)
                        else:
                            new_parts.append(part)
                    elif part.get("type") == "input_audio":
                        new_parts.append(part)
                    else:
                        new_parts.append(part)
                sanitized_messages.append({**msg, "content": new_parts})
            else:
                sanitized_messages.append(msg)
        body["messages"] = sanitized_messages

    audit.log_redactions(request_id, all_redactions)

    if all_redactions:
        log.info(f"[{request_id}] Redacted {len(all_redactions)} entities ({', '.join(set(r['type'] for r in all_redactions))})")

    if OBFUSCATION_MODE and "messages" in body:
        body["messages"].insert(0, get_obfuscation_msg())

    is_streaming = body.get("stream", False)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    for h in ["HTTP-Referer", "X-Title"]:
        val = request.headers.get(h)
        if val:
            headers[h] = val

    if is_streaming:
        return await _handle_streaming(body, headers, request_id, len(all_redactions))
    else:
        return await _handle_standard(body, headers, request_id, len(all_redactions))


async def _handle_standard(body, headers, request_id, redacted_count):
    async with get_client() as client:
        resp = await client.post(f"{UPSTREAM_URL}/v1/chat/completions", json=body, headers=headers)

    if resp.status_code != 200:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

    result = resp.json()
    if "choices" in result:
        for choice in result["choices"]:
            msg = choice.get("message", {})
            if msg.get("content"):
                msg["content"] = engine.restore(msg["content"])

    result["_voidcrypt"] = {"request_id": request_id, "entities_redacted": redacted_count, "level": PRIVACY_LEVEL, "privacy": "protected", "mappings": engine.get_mappings()}
    return JSONResponse(content=result)


async def _handle_streaming(body, headers, request_id, redacted_count):
    async def stream_generator():
        buffer = ""
        async with get_client() as client:
            async with client.stream("POST", f"{UPSTREAM_URL}/v1/chat/completions", json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    yield f"data: {error_body.decode()}\n\n"
                    return

                async for line in resp.aiter_lines():
                    if not line.strip():
                        yield "\n"
                        continue
                    if not line.startswith("data: "):
                        yield f"{line}\n"
                        continue

                    data = line[6:]
                    if data.strip() == "[DONE]":
                        if buffer:
                            restored = engine.restore(buffer)
                            buffer = ""
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': restored}, 'index': 0}]})}\n\n"
                        yield "data: [DONE]\n\n"
                        continue

                    try:
                        chunk = json.loads(data)
                        delta_content = ""
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                delta_content += delta["content"]

                        if delta_content:
                            buffer += delta_content
                            restored = engine.restore(buffer)

                            has_partial = False
                            if "{" in buffer:
                                last_brace = buffer.rfind("{")
                                if "}" not in buffer[last_brace:]:
                                    has_partial = True
                            if "[" in buffer:
                                last_bracket = buffer.rfind("[")
                                if "]" not in buffer[last_bracket:]:
                                    has_partial = True

                            if not has_partial:
                                for choice in chunk.get("choices", []):
                                    if choice.get("delta", {}).get("content"):
                                        choice["delta"]["content"] = restored
                                buffer = ""
                                yield f"data: {json.dumps(chunk)}\n\n"
                        else:
                            yield f"data: {json.dumps(chunk)}\n\n"
                    except json.JSONDecodeError:
                        yield f"{line}\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-VoidCrypt-Request": request_id})


@app.post("/v1/messages")
async def claude_messages(request: Request):
    """Claude API compatibility. Converts Claude format to OpenAI format."""
    if not engine or not vault:
        raise HTTPException(status_code=503, detail="VoidCrypt not initialized.")

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    request_id = str(uuid.uuid4())[:8]
    all_redactions = []

    model = body.get("model", "claude-3-5-sonnet-20241022")
    max_tokens = body.get("max_tokens", 4096)
    stream = body.get("stream", False)
    system_message = body.get("system", "")
    claude_messages_list = body.get("messages", [])

    openai_messages = []

    if system_message:
        sanitized_sys, sys_redactions = engine.scan_and_replace(system_message)
        all_redactions.extend(sys_redactions)
        openai_messages.append({"role": "system", "content": sanitized_sys})

    for msg in claude_messages_list:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            sanitized, redactions = engine.scan_and_replace(content)
            all_redactions.extend(redactions)
            openai_messages.append({"role": role, "content": sanitized})
        elif isinstance(content, list):
            new_parts = []
            for part in content:
                if part.get("type") == "text":
                    text = part.get("text", "")
                    if text:
                        sanitized, redactions = engine.scan_and_replace(text)
                        all_redactions.extend(redactions)
                        new_parts.append({**part, "text": sanitized})
                    else:
                        new_parts.append(part)
                elif part.get("type") == "image":
                    new_parts.append(part)
                else:
                    new_parts.append(part)
            openai_messages.append({"role": role, "content": new_parts})
        else:
            openai_messages.append({"role": role, "content": content})

    audit.log_redactions(request_id, all_redactions)

    if all_redactions:
        log.info(f"[{request_id}] Claude API: Redacted {len(all_redactions)} entities")

    openai_body = {"model": model, "messages": openai_messages, "max_tokens": max_tokens, "stream": stream}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

    if stream:
        return await _handle_claude_streaming(openai_body, headers, request_id, len(all_redactions))
    else:
        return await _handle_claude_standard(openai_body, headers, request_id, len(all_redactions))


async def _handle_claude_standard(body, headers, request_id, redacted_count):
    async with get_client() as client:
        resp = await client.post(f"{UPSTREAM_URL}/v1/chat/completions", json=body, headers=headers)

    if resp.status_code != 200:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

    result = resp.json()
    if "choices" in result:
        for choice in result["choices"]:
            msg = choice.get("message", {})
            if msg.get("content"):
                msg["content"] = engine.restore(msg["content"])

    result["_voidcrypt"] = {"request_id": request_id, "entities_redacted": redacted_count, "level": PRIVACY_LEVEL, "privacy": "protected", "mappings": engine.get_mappings()}
    return JSONResponse(content=result)


async def _handle_claude_streaming(body, headers, request_id, redacted_count):
    async def stream_generator():
        buffer = ""
        async with get_client() as client:
            async with client.stream("POST", f"{UPSTREAM_URL}/v1/chat/completions", json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    yield f"data: {error_body.decode()}\n\n"
                    return

                async for line in resp.aiter_lines():
                    if not line.strip():
                        yield "\n"
                        continue
                    if not line.startswith("data: "):
                        yield f"{line}\n"
                        continue

                    data = line[6:]
                    if data.strip() == "[DONE]":
                        if buffer:
                            restored = engine.restore(buffer)
                            buffer = ""
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': restored}, 'index': 0}]})}\n\n"
                        yield "data: [DONE]\n\n"
                        continue

                    try:
                        chunk = json.loads(data)
                        delta_content = ""
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                delta_content += delta["content"]

                        if delta_content:
                            buffer += delta_content
                            restored = engine.restore(buffer)

                            has_partial = False
                            if "{" in buffer:
                                last_brace = buffer.rfind("{")
                                if "}" not in buffer[last_brace:]:
                                    has_partial = True

                            if not has_partial:
                                for choice in chunk.get("choices", []):
                                    if choice.get("delta", {}).get("content"):
                                        choice["delta"]["content"] = restored
                                buffer = ""
                                yield f"data: {json.dumps(chunk)}\n\n"
                        else:
                            yield f"data: {json.dumps(chunk)}\n\n"
                    except json.JSONDecodeError:
                        yield f"{line}\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-VoidCrypt-Request": request_id})


@app.get("/v1/vault/stats")
async def vault_stats():
    if not vault:
        raise HTTPException(status_code=503, detail="Vault not initialized")
    return vault.get_stats()


@app.get("/v1/mappings")
async def get_mappings():
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    return {"mappings": engine.format_mappings(), "mappings_dict": engine.get_mappings(), "stats": engine.encryption.get_stats() if engine.use_encryption else vault.get_stats()}


@app.get("/v1/audit")
async def audit_log(limit=50):
    if not audit:
        raise HTTPException(status_code=503, detail="Audit not initialized")
    return audit.get_recent(limit)


@app.post("/v1/vault/clear")
async def clear_vault():
    if not vault:
        raise HTTPException(status_code=503, detail="Vault not initialized")
    vault.clear_session()
    if engine and engine.encryption:
        engine.encryption.clear_session()
    return {"status": "cleared"}


@app.post("/v1/custom-rules")
async def add_custom_rule(request: Request):
    body = await request.json()
    name = body.get("name")
    pattern = body.get("pattern")
    if not name or not pattern:
        raise HTTPException(status_code=400, detail="name and pattern required")
    try:
        re.compile(pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")
    rules = []
    if CUSTOM_RULES_FILE.exists():
        rules = json.loads(CUSTOM_RULES_FILE.read_text())
    rules.append({"name": name, "pattern": pattern})
    CUSTOM_RULES_FILE.write_text(json.dumps(rules, indent=2))
    engine.patterns[name] = pattern
    return {"status": "added", "name": name}


@app.post("/v1/level")
async def set_level(request: Request):
    global engine, PRIVACY_LEVEL
    body = await request.json()
    level = body.get("level", "smart").lower()
    if level not in ("paranoid", "smart", "minimal"):
        raise HTTPException(status_code=400, detail="level must be: paranoid, smart, or minimal")
    PRIVACY_LEVEL = level
    custom_rules = []
    if CUSTOM_RULES_FILE.exists():
        custom_rules = json.loads(CUSTOM_RULES_FILE.read_text())
    engine = EntityEngine(vault, level=level, custom_rules=custom_rules, use_encryption=True)
    log.info(f"Privacy level changed to: {level}")
    return {"status": "ok", "level": level}


def init_vault():
    key = Fernet.generate_key().decode()
    VOIDCRYPT_DIR.mkdir(parents=True, exist_ok=True)
    config = {"upstream": UPSTREAM_URL, "port": PORT, "level": PRIVACY_LEVEL, "created": datetime.now(timezone.utc).isoformat()}
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    print("=" * 60)
    print("  VoidCrypt Initialized")
    print("=" * 60)
    print(f"\n  Your vault key:\n\n  {key}\n")
    print(f"  export VOIDCRYPT_KEY=\"{key}\"")
    print(f"  Vault dir: {VOIDCRYPT_DIR}")
    print("=" * 60)
    return key


if __name__ == "__main__":
    import sys
    if "--init" in sys.argv:
        init_vault()
    else:
        if not VAULT_KEY:
            print("Error: VOIDCRYPT_KEY not set. Run: python voidcrypt.py --init")
            sys.exit(1)
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
