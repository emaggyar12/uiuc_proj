from playwright.sync_api import sync_playwright

URL = "https://evanmiya.com/?player_ratings"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1400, "height": 1200})

    page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(12_000)

    print("\n--- INPUTS ---")
    inputs = page.locator("input").all()
    for i, el in enumerate(inputs):
        try:
            print(i, {
                "type": el.get_attribute("type"),
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "value": el.get_attribute("value"),
                "class": el.get_attribute("class"),
                "checked": el.is_checked() if el.get_attribute("type") == "radio" else None,
            })
        except Exception as e:
            print(i, "ERR", e)

    print("\n--- SELECTS ---")
    selects = page.locator("select").all()
    for i, el in enumerate(selects):
        try:
            print(i, {
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "class": el.get_attribute("class"),
                "text": el.inner_text()[:500],
            })
        except Exception as e:
            print(i, "ERR", e)

    print("\n--- SELECTIZE CONTROLS ---")
    controls = page.locator(".selectize-control, .selectize-input").all()
    for i, el in enumerate(controls):
        try:
            print(i, {
                "class": el.get_attribute("class"),
                "text": el.inner_text()[:300],
                "html": el.evaluate("e => e.outerHTML").replace("\n", " ")[:1000],
            })
        except Exception as e:
            print(i, "ERR", e)

    print("\n--- LABELS ---")
    labels = page.locator("label").all()
    for i, el in enumerate(labels):
        try:
            text = el.inner_text().strip()
            if text:
                print(i, {
                    "text": text,
                    "for": el.get_attribute("for"),
                    "html": el.evaluate("e => e.outerHTML").replace("\n", " ")[:800],
                })
        except Exception as e:
            print(i, "ERR", e)

    browser.close()