from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
DEFAULT_PRODUCT_CONTEXT_KEY = "blostem_bfsi_security_compliance"


REAL_BFSI_TARGETS: list[dict[str, Any]] = [
    {
        "name": "HDFC Bank",
        "segment": "Private Bank",
        "territory": "India",
        "summary": "Large Indian private-sector bank with broad retail, corporate, and digital banking operations.",
        "shared_email": "shareholder.grievances@hdfcbank.com",
        "contacts": [
            {
                "name": "Sashidhar Jagdishan",
                "role": "Managing Director & Chief Executive Officer",
                "persona": "CEO",
                "influence_level": "high",
                "source_url": "https://www.hdfcbank.com/personal/about-us/investor-relations/disclosures-under-regulation-46-of-the-lodr/authorized-key-managerial-personnel",
            },
            {
                "name": "Srinivasan Vaidyanathan",
                "role": "Chief Financial Officer",
                "persona": "CFO",
                "influence_level": "high",
                "source_url": "https://www.hdfcbank.com/personal/about-us/investor-relations/disclosures-under-regulation-46-of-the-lodr/authorized-key-managerial-personnel",
            },
            {
                "name": "Ramesh Lakshminarayanan",
                "role": "Chief Information Officer",
                "persona": "CTO",
                "influence_level": "high",
                "source_url": "https://www.hdfcbank.com/personal/about-us/news-room/press-release/2023/q1/hdfc-bank-partners-with-microsoft-as-part-of-its-digital-transformation-journey",
            },
        ],
    },
    {
        "name": "ICICI Bank",
        "segment": "Private Bank",
        "territory": "India",
        "summary": "Large Indian private-sector bank with strong retail, corporate, and digital distribution footprint.",
        "shared_email": "companysecretary@icici.bank.in",
        "contacts": [
            {
                "name": "Sandeep Bakhshi",
                "role": "Managing Director & Chief Executive Officer",
                "persona": "CEO",
                "influence_level": "high",
                "source_url": "https://www.icici.bank.in/about-us/bod-1",
            },
            {
                "name": "Anindya Banerjee",
                "role": "Group Chief Financial Officer",
                "persona": "CFO",
                "influence_level": "high",
                "source_url": "https://www.icici.bank.in/ms/aboutus/annual-reports/2024-25/html/corporate-information.html",
            },
            {
                "name": "Subir Saha",
                "role": "Group Chief Compliance Officer",
                "persona": "Legal",
                "influence_level": "high",
                "source_url": "https://www.icici.bank.in/ms/aboutus/annual-reports/2024-25/html/board-report.html",
            },
        ],
    },
    {
        "name": "Axis Bank",
        "segment": "Private Bank",
        "territory": "India",
        "summary": "Large Indian private-sector bank focused on retail, wholesale, and digitally enabled banking growth.",
        "shared_email": "corporate.communication@axis.bank.in",
        "contacts": [
            {
                "name": "Amitabh Chaudhry",
                "role": "Managing Director and Chief Executive Officer",
                "persona": "CEO",
                "influence_level": "high",
                "source_url": "https://www.axis.bank.in/about-us/senior-management/amitabh-chaudhry",
            },
            {
                "name": "Puneet Sharma",
                "role": "Chief Financial Officer",
                "persona": "CFO",
                "influence_level": "high",
                "source_url": "https://www.axis.bank.in/about-us/senior-management",
            },
            {
                "name": "Sameer Shetty",
                "role": "Group Executive - Digital Business & Transformation and Strategic Programs",
                "persona": "CTO",
                "influence_level": "medium",
                "source_url": "https://www.axis.bank.in/about-us/senior-management",
            },
        ],
    },
    {
        "name": "Kotak Mahindra Bank",
        "segment": "Private Bank",
        "territory": "India",
        "summary": "Indian private-sector bank with strong consumer, commercial, and treasury franchises and a tech-led operating agenda.",
        "shared_email": "KotakBank.Secretarial@kotak.com",
        "contacts": [
            {
                "name": "Ashok Vaswani",
                "role": "Managing Director & CEO",
                "persona": "CEO",
                "influence_level": "high",
                "source_url": "https://www.kotak.com/en/investor-relations/governance/bank-committees.html",
            },
            {
                "name": "Devang Gheewalla",
                "role": "Group Chief Financial Officer",
                "persona": "CFO",
                "influence_level": "high",
                "source_url": "https://www.kotak.com/content/dam/Kotak/investor-relation/governance/governance-sebi-tab/2024/change-in-key-managerial-personnel-senior-management/SE-intimation.pdf",
            },
            {
                "name": "N. Chaudhari",
                "role": "Chief Technology Officer",
                "persona": "CTO",
                "influence_level": "high",
                "source_url": "https://www.kotak.bank.in/en/customer-service/important-customer-information/senior-management-contact-details.html",
            },
        ],
    },
    {
        "name": "IDFC FIRST Bank",
        "segment": "Private Bank",
        "territory": "India",
        "summary": "Fast-growing Indian private-sector bank positioning itself around digital, ethical, and mass-affluent banking growth.",
        "shared_email": "secretarial@idfcfirstbank.com",
        "contacts": [
            {
                "name": "V. Vaidyanathan",
                "role": "Managing Director & CEO",
                "persona": "CEO",
                "influence_level": "high",
                "source_url": "https://www.idfcfirstbank.com/about-us/about-md-and-ceo",
            },
            {
                "name": "Sudhanshu Jain",
                "role": "Chief Financial Officer and Head - Corporate Centre",
                "persona": "CFO",
                "influence_level": "high",
                "source_url": "https://www.idfcfirstbank.com/investors/authorized-kmp",
            },
            {
                "name": "Nitin Chauhan",
                "role": "Chief Information Security Officer",
                "persona": "CTO",
                "influence_level": "medium",
                "source_url": "https://www.idfcfirstbank.com/content/dam/idfcfirstbank/pdf/announcements/Change-in-SMP-CISO-29-1-25.pdf",
            },
        ],
    },
]


def brief_derived_product_context() -> dict[str, Any]:
    return {
        "key": DEFAULT_PRODUCT_CONTEXT_KEY,
        "name": "Blostem BFSI Security and Compliance Engine",
        "version": "1.0.0",
        "overview": (
            "Conservative product context derived from the current Blostem pilot brief. "
            "Position Blostem around security, compliance, and activation support for regulated banks and fintechs."
        ),
        "icp_segments": ["Private Bank", "Fintech", "NBFC"],
        "trigger_patterns": [
            "data breach",
            "cyber attack",
            "rbi",
            "regulatory",
            "penalty",
            "fraud",
            "compliance",
            "digital",
            "identity",
            "security",
            "onboarding",
            "hiring",
        ],
        "disqualifiers": [
            "consumer-only promo",
            "retail discount campaign",
        ],
        "approved_claims": [],
        "buyer_personas": [
            {"persona": "CTO", "needs": "security posture, integration risk, operational resilience"},
            {"persona": "CFO", "needs": "risk reduction, control environment, execution confidence"},
            {"persona": "Legal", "needs": "compliance controls, auditability, claim discipline"},
        ],
        "activation_playbook": [
            {"step": "Identify executive sponsor", "window": "Day 1-3"},
            {"step": "Confirm compliance and security review owners", "window": "Day 3-7"},
            {"step": "Run implementation kickoff and milestone plan", "window": "Day 7-14"},
        ],
    }


def strip_html(value: str) -> str:
    return SPACE_RE.sub(" ", TAG_RE.sub(" ", html.unescape(value or ""))).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def parse_google_news_rss(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = strip_html(item.findtext("description") or "")
        source_text = (item.findtext("source") or "").strip()
        published_raw = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        published_at = None
        if published_raw:
            parsed = parsedate_to_datetime(published_raw)
            published_at = parsed.astimezone(UTC)
        items.append(
            {
                "title": title,
                "link": link,
                "description": description,
                "source": source_text or "Google News",
                "published_at": published_at,
            },
        )
    return items


def classify_signal(text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ["breach", "cyber", "phishing", "security", "attack", "ciso"]):
        return "security_event"
    if any(token in normalized for token in ["rbi", "fine", "penalty", "regulatory", "compliance", "audit"]):
        return "regulatory_event"
    if any(token in normalized for token in ["hire", "hiring", "appoint", "joins", "leadership"]):
        return "leadership_change"
    if any(token in normalized for token in ["partnership", "partner", "launch", "digital", "onboarding", "api"]):
        return "digital_initiative"
    return "market_update"


def build_news_query(account_name: str) -> str:
    return (
        f"\"{account_name}\" (RBI OR compliance OR cyber OR fraud OR partnership OR "
        "digital OR onboarding OR technology OR hiring OR leadership) when:30d"
    )


def telemetry_payloads(account_id: str) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    return [
        {
            "account_id": account_id,
            "event_type": "workspace_invite_sent",
            "detected_at": (now - timedelta(days=4)).isoformat(),
            "payload": {
                "synthetic": True,
                "purpose": "coach_phase_test",
                "detail": "Implementation invite sent to customer sponsor.",
            },
        },
        {
            "account_id": account_id,
            "event_type": "admin_setup_started",
            "detected_at": (now - timedelta(days=3)).isoformat(),
            "payload": {
                "synthetic": True,
                "purpose": "coach_phase_test",
                "detail": "Admin setup wizard opened but not completed.",
            },
        },
        {
            "account_id": account_id,
            "event_type": "security_questionnaire_opened",
            "detected_at": (now - timedelta(days=2)).isoformat(),
            "payload": {
                "synthetic": True,
                "purpose": "coach_phase_test",
                "detail": "Security questionnaire viewed without final submission.",
            },
        },
    ]


def json_safe_news_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    published_at = payload.get("published_at")
    if isinstance(published_at, datetime):
        payload["published_at"] = published_at.isoformat()
    return payload


class Seeder:
    def __init__(
        self,
        *,
        api_base_url: str,
        product_context_file: Path | None,
        signals_per_account: int,
        refresh_workflows: bool,
        build_handoffs: bool,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.product_context_file = product_context_file
        self.signals_per_account = signals_per_account
        self.refresh_workflows = refresh_workflows
        self.build_handoffs = build_handoffs

    async def run(self) -> None:
        async with httpx.AsyncClient(base_url=self.api_base_url, timeout=httpx.Timeout(60.0, connect=20.0)) as client:
            await self.ensure_api_ready(client)
            product_context = await self.ensure_product_context(client)
            print(f"[seed] product context ready: {product_context['key']}")

            seeded_account_ids: list[str] = []
            for account_seed in REAL_BFSI_TARGETS:
                account = await self.ensure_account(client, account_seed)
                seeded_account_ids.append(account["id"])
                await self.ensure_contacts(client, account["id"], account_seed)
                await self.ensure_signals(client, account["id"], account_seed)

            if seeded_account_ids:
                await self.ensure_mock_telemetry(client, seeded_account_ids[0])

            if self.refresh_workflows:
                for account_id in seeded_account_ids:
                    await self.refresh_opportunity(client, account_id)

            if self.build_handoffs:
                for account_id in seeded_account_ids:
                    await self.build_handoff(client, account_id)

            queue = await self.get_json(client, "/accounts")
            print("\n[seed] workspace status")
            print(f"  accounts: {len(queue['items'])}")
            for item in queue["items"]:
                print(
                    f"  - {item['name']}: intent={item['intent_score']:.0f} fit={item['fit_score']:.0f} "
                    f"freshness={item['freshness_score']:.0f}",
                )

    async def ensure_api_ready(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")
        response.raise_for_status()

    async def ensure_product_context(self, client: httpx.AsyncClient) -> dict[str, Any]:
        existing = await self.get_json(client, "/product-contexts")
        for item in existing:
            if item["key"] == DEFAULT_PRODUCT_CONTEXT_KEY:
                return item

        payload = brief_derived_product_context()
        if self.product_context_file:
            payload = json.loads(self.product_context_file.read_text(encoding="utf-8"))
        else:
            print(
                "[seed] warning: using a conservative product context derived from the repo brief. "
                "Replace it with --product-context-file when you have the actual Blostem product spec.",
            )
        created = await self.post_json(client, "/product-contexts", payload)
        return created

    async def ensure_account(self, client: httpx.AsyncClient, seed: dict[str, Any]) -> dict[str, Any]:
        queue = await self.get_json(client, "/accounts")
        existing = next((item for item in queue["items"] if item["name"] == seed["name"]), None)
        if existing is not None:
            print(f"[seed] account exists: {seed['name']}")
            return existing

        created = await self.post_json(
            client,
            "/accounts",
            {
                "name": seed["name"],
                "segment": seed["segment"],
                "territory": seed["territory"],
                "pipeline_stage": "Research",
                "summary": seed["summary"],
                "owner_role": "rep",
                "metadata": {
                    "seed_origin": "public_bfsi_targets",
                    "official_shared_email": seed["shared_email"],
                },
            },
        )
        print(f"[seed] created account: {seed['name']}")
        return created

    async def ensure_contacts(self, client: httpx.AsyncClient, account_id: str, seed: dict[str, Any]) -> None:
        brief = await self.get_json(client, f"/accounts/{account_id}/brief")
        existing = {(item["name"], item["role"]) for item in brief["contacts"]}
        for contact in seed["contacts"]:
            key = (contact["name"], contact["role"])
            if key in existing:
                continue
            await self.post_json(
                client,
                f"/accounts/{account_id}/contacts",
                {
                    "name": contact["name"],
                    "role": contact["role"],
                    "persona": contact["persona"],
                    "email": seed["shared_email"],
                    "influence_level": contact["influence_level"],
                    "status": "research",
                    "notes": (
                        f"Seeded from public leadership source: {contact['source_url']}. "
                        "Email is the public shared company mailbox and should be enriched before outbound."
                    ),
                },
            )
            print(f"[seed] added contact: {seed['name']} -> {contact['name']} ({contact['role']})")

    async def ensure_signals(self, client: httpx.AsyncClient, account_id: str, seed: dict[str, Any]) -> None:
        brief = await self.get_json(client, f"/accounts/{account_id}/brief")
        existing = {(item["title"], item["source_url"]) for item in brief["signals"]}

        query = build_news_query(seed["name"])
        rss_items = await self.fetch_google_news(query)
        inserted = 0
        for item in rss_items:
            if inserted >= self.signals_per_account:
                break
            source_url = await self.resolve_article_url(item["link"])
            if len(source_url) > 500:
                continue
            dedupe_key = (item["title"], source_url)
            if dedupe_key in existing:
                continue
            summary = item["description"] or item["title"]
            summary = summary[:320]
            detected_at = item["published_at"] or datetime.now(UTC)
            payload = {
                "account_id": account_id,
                "topic_family": "market-signal.ingested",
                "signal_type": classify_signal(f"{item['title']} {summary}"),
                "source_type": "google_news_rss",
                "title": item["title"],
                "summary": summary,
                "source_url": source_url,
                "detected_at": detected_at.isoformat(),
                "facts": {
                    "publisher": item["source"],
                    "query": query,
                },
                "citations": [
                    {
                        "label": item["source"],
                        "source_url": source_url,
                        "claim": item["title"],
                        "excerpt": summary,
                        "published_at": detected_at.isoformat(),
                    },
                ],
                "raw_payload": {
                    **json_safe_news_item(item),
                    "original_link": item["link"],
                    "resolved_source_url": source_url,
                },
            }
            await self.post_json(client, "/signals/ingest", payload)
            inserted += 1
            print(f"[seed] added signal: {seed['name']} -> {item['title']}")

    async def ensure_mock_telemetry(self, client: httpx.AsyncClient, account_id: str) -> None:
        brief = await self.get_json(client, f"/accounts/{account_id}/brief")
        existing_types = {item["event_type"] for item in brief["telemetry"]}
        for payload in telemetry_payloads(account_id):
            if payload["event_type"] in existing_types:
                continue
            await self.post_json(client, "/telemetry/ingest", payload)
            print(f"[seed] added mock telemetry: {payload['event_type']} -> {account_id}")

    async def refresh_opportunity(self, client: httpx.AsyncClient, account_id: str) -> None:
        response = await self.post_json(client, "/workflows/opportunity-refresh", {"account_id": account_id})
        print(f"[seed] refreshed opportunity: {account_id} -> draft {response['draft']}")

    async def build_handoff(self, client: httpx.AsyncClient, account_id: str) -> None:
        response = await self.post_json(client, f"/deals/{account_id}/handoff", None)
        print(f"[seed] built handoff: {account_id} -> {response['id']}")

    async def fetch_google_news(self, query: str) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en",
        }
        url = f"{GOOGLE_NEWS_RSS}?q={quote_plus(params['q'])}&hl={params['hl']}&gl={params['gl']}&ceid={params['ceid']}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0), follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        seen_titles: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in parse_google_news_rss(response.text):
            title_key = item["title"].lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            deduped.append(item)
        return deduped

    async def resolve_article_url(self, url: str) -> str:
        if len(url) <= 500 and "news.google.com" not in url:
            return url
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=10.0),
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 BlostemSeed/1.0"},
            ) as client:
                response = await client.get(url)
                final_url = str(response.url)
                if final_url:
                    return final_url
        except httpx.HTTPError:
            return url
        return url

    async def get_json(self, client: httpx.AsyncClient, path: str) -> Any:
        response = await client.get(path)
        response.raise_for_status()
        return response.json()

    async def post_json(self, client: httpx.AsyncClient, path: str, payload: Any) -> Any:
        response = await client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed Blostem with real BFSI accounts, public leadership contacts, live Google News RSS signals, "
            "and one explicitly synthetic telemetry stream."
        ),
    )
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000", help="Base URL for the running Blostem API.")
    parser.add_argument(
        "--product-context-file",
        type=Path,
        default=None,
        help="Optional JSON file containing the real Blostem product context to seed.",
    )
    parser.add_argument(
        "--signals-per-account",
        type=int,
        default=2,
        help="How many live Google News RSS signals to seed for each account.",
    )
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Skip the opportunity refresh workflow after seeding accounts and signals.",
    )
    parser.add_argument(
        "--build-handoffs",
        action="store_true",
        help="Build activation handoffs after seeding and refresh.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if args.product_context_file and not args.product_context_file.exists():
        print(f"[seed] product context file not found: {args.product_context_file}", file=sys.stderr)
        return 1

    seeder = Seeder(
        api_base_url=args.api_base_url,
        product_context_file=args.product_context_file,
        signals_per_account=max(1, args.signals_per_account),
        refresh_workflows=not args.skip_refresh,
        build_handoffs=args.build_handoffs,
    )
    await seeder.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
