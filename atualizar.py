#!/usr/bin/env python3
# Gerador de M3U - TV Garden Brasil
# A página do TV Garden usa IPTV-org como uma de suas principais fontes.
# O projeto mantém a página TV Garden como fonte declarada e usa a playlist
# pública do IPTV-org para obter os streams, aplicando filtros semelhantes:
# somente Brasil + HTTPS + teste de disponibilidade.

from __future__ import annotations

import concurrent.futures
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent

TVGARDEN_URL = "https://tvgarden.world/tv/br"
UPSTREAM_URL = "https://iptv-org.github.io/iptv/countries/br.m3u"

OUTPUT_M3U = ROOT / "lista.m3u"
OUTPUT_JSON = ROOT / "descoberto.json"
OUTPUT_STATUS = ROOT / "status.json"

TIMEOUT = 12
MAX_WORKERS = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
)

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Connection": "keep-alive",
})

def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())

def attrs_from_extinf(line: str) -> dict:
    attrs = {}
    for key, value in re.findall(r'([\w-]+)="([^"]*)"', line):
        attrs[key] = value
    return attrs

def parse_m3u(text: str) -> list[dict]:
    entries = []
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    current = None

    for line in lines:
        if line.startswith("#EXTINF:"):
            current = {
                "extinf": line,
                "attrs": attrs_from_extinf(line),
                "name": clean(line.rsplit(",", 1)[-1] if "," in line else "Canal"),
            }
        elif current and not line.startswith("#"):
            current["url"] = line
            entries.append(current)
            current = None

    return entries

def stream_is_valid(url: str) -> bool:
    # TV Garden informa que prioriza HTTPS; mantemos esse critério.
    if not url.lower().startswith("https://"):
        return False

    try:
        r = session.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
            headers={
                "Range": "bytes=0-8191",
                "Accept": "*/*",
            },
        )
        if r.status_code >= 400:
            r.close()
            return False

        content_type = (r.headers.get("content-type") or "").lower()

        # Lê somente uma pequena quantidade para não consumir a transmissão.
        sample = b""
        try:
            sample = next(r.iter_content(chunk_size=8192), b"")
        except Exception:
            pass
        finally:
            r.close()

        text_sample = sample.decode("utf-8", errors="ignore").upper()

        # HLS/M3U8: manifesto normalmente contém EXTM3U ou EXT-X.
        if ".m3u8" in url.lower() or "mpegurl" in content_type:
            return "#EXTM3U" in text_sample or "#EXT-X-" in text_sample

        # Alguns servidores entregam o manifesto sem informar corretamente o MIME.
        if "#EXTM3U" in text_sample or "#EXT-X-" in text_sample:
            return True

        # Se o servidor respondeu com mídia, aceitamos.
        media_types = ("video/", "audio/", "application/octet-stream")
        return any(t in content_type for t in media_types)

    except requests.RequestException:
        return False

def make_extinf(entry: dict) -> str:
    attrs = dict(entry.get("attrs") or {})

    # Mantém metadados úteis e garante tvg-name/group-title.
    name = entry.get("name") or attrs.get("tvg-name") or "Canal Brasil"
    tvg_name = attrs.get("tvg-name") or name
    group = attrs.get("group-title") or "Brasil"

    # Remove atributos potencialmente inconsistentes e recria os principais.
    out = ['#EXTINF:-1']
    if attrs.get("tvg-id"):
        out.append(f'tvg-id="{attrs["tvg-id"]}"')
    if attrs.get("tvg-logo"):
        out.append(f'tvg-logo="{attrs["tvg-logo"]}"')
    out.append(f'tvg-name="{tvg_name}"')
    out.append(f'group-title="{group}"')
    out.append(f",{name}")
    return " ".join(out)

def main() -> int:
    started = time.time()
    now = datetime.now(timezone.utc).isoformat()

    try:
        response = session.get(UPSTREAM_URL, timeout=30)
        response.raise_for_status()
        source_text = response.text
    except Exception as exc:
        status = {
            "ok": False,
            "updated_at_utc": now,
            "source": TVGARDEN_URL,
            "upstream": UPSTREAM_URL,
            "erro": f"Falha ao baixar a fonte: {exc}",
        }
        OUTPUT_STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(status["erro"], file=sys.stderr)
        return 1

    entries = parse_m3u(source_text)

    # Deduplicação por canal + URL.
    seen = set()
    candidates = []
    for e in entries:
        url = e.get("url", "").strip()
        name = e.get("name", "").strip()
        key = (name.lower(), url.lower())
        if not url or key in seen:
            continue
        seen.add(key)
        candidates.append(e)

    # Mantém somente HTTPS, alinhado ao critério declarado pelo TV Garden.
    candidates = [e for e in candidates if e["url"].lower().startswith("https://")]

    approved = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(stream_is_valid, e["url"]): e for e in candidates}
        for future in concurrent.futures.as_completed(futures):
            entry = futures[future]
            try:
                if future.result():
                    approved.append(entry)
            except Exception:
                pass

    # Ordenação por categoria e nome.
    approved.sort(
        key=lambda e: (
            clean((e.get("attrs") or {}).get("group-title", "Brasil")).lower(),
            clean(e.get("name", "")).lower(),
        )
    )

    lines = ["#EXTM3U"]
    for entry in approved:
        lines.append(make_extinf(entry))
        lines.append(entry["url"])

    OUTPUT_M3U.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = {
        "fonte": TVGARDEN_URL,
        "fonte_dados": UPSTREAM_URL,
        "atualizado_em_utc": now,
        "total_encontrados": len(entries),
        "total_https": len(candidates),
        "total_aprovados": len(approved),
        "total_removidos_por_teste": len(candidates) - len(approved),
        "arquivos_gerados_na_raiz": ["lista.m3u", "descoberto.json", "status.json"],
        "categorias": sorted({
            clean((e.get("attrs") or {}).get("group-title", "Brasil"))
            for e in approved
        }),
        "canais": [
            {
                "nome": e.get("name"),
                "tvg-name": (e.get("attrs") or {}).get("tvg-name") or e.get("name"),
                "categoria": (e.get("attrs") or {}).get("group-title") or "Brasil",
                "url": e.get("url"),
            }
            for e in approved
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    status = {
        "ok": True,
        "atualizado_em_utc": now,
        "duracao_segundos": round(time.time() - started, 2),
        "canais_gerados": len(approved),
        "fonte": TVGARDEN_URL,
        "fonte_dados": UPSTREAM_URL,
        "playlist": "lista.m3u",
    }
    OUTPUT_STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Gerados {len(approved)} canais em lista.m3u")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
