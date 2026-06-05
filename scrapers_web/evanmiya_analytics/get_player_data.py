from pathlib import Path
import json
import re

from playwright.sync_api import sync_playwright


URL = "https://evanmiya.com/?player_ratings"
OUT_DIR = Path("evanmiya_network")
OUT_DIR.mkdir(exist_ok=True)


def safe_filename(s: str, max_len: int = 120) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)
    return s[:max_len]


def sniff_network_and_websockets():
    websocket_frames = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        def handle_response(response):
            url = response.url
            ctype = response.headers.get("content-type", "")
            req = response.request

            if any(x in url.lower() for x in [".png", ".jpg", ".css", ".woff", ".svg", ".ico"]):
                return

            print(f"[{response.status}] {req.resource_type.upper():10} {req.method:4} {url}")

            try:
                body = response.text()
            except Exception:
                return

            if any(term in body.lower() for term in ["player", "bpr", "obpr", "dbpr", "team"]):
                name = safe_filename(url.replace("https://", "").replace("http://", ""))
                path = OUT_DIR / f"{name}.txt"
                path.write_text(body, encoding="utf-8")
                print(f"    SAVED BODY -> {path}")

        def handle_websocket(ws):
            print(f"\n[WEBSOCKET OPENED] {ws.url}\n")

            def frame_sent(payload):
                text = str(payload)
                websocket_frames.append({"direction": "sent", "payload": text})
                if any(x in text.lower() for x in ["player", "bpr", "ratings", "reactable"]):
                    print("\n[WS SENT MATCH]")
                    print(text[:1000])

            def frame_received(payload):
                text = str(payload)
                websocket_frames.append({"direction": "received", "payload": text})
                if any(x in text.lower() for x in ["player", "bpr", "ratings", "reactable"]):
                    print("\n[WS RECEIVED MATCH]")
                    print(text[:1000])

            ws.on("framesent", frame_sent)
            ws.on("framereceived", frame_received)

        page.on("response", handle_response)
        page.on("websocket", handle_websocket)

        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # Let the Shiny app initialize.
        page.wait_for_timeout(20_000)

        # Save rendered HTML and websocket frames.
        (OUT_DIR / "rendered_page.html").write_text(page.content(), encoding="utf-8")
        (OUT_DIR / "websocket_frames.json").write_text(
            json.dumps(websocket_frames, indent=2),
            encoding="utf-8",
        )

        print("\nDone. Check:")
        print("  evanmiya_network/rendered_page.html")
        print("  evanmiya_network/websocket_frames.json")

        browser.close()


if __name__ == "__main__":
    sniff_network_and_websockets()