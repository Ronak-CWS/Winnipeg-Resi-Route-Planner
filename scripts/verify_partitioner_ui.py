"""Local UI checks. External HTTP is blocked; optional basemap uses frozen QA cache."""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "outputs/2026-11-04_monday_map/audit/partition_app"
BASE = "http://127.0.0.1:8765"


def wait_for(page, expression, timeout=30000):
    # DevTools evaluation avoids Playwright's in-page eval poller, which this
    # application's strict production CSP correctly blocks.
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if page.evaluate(expression):
            return
        page.wait_for_timeout(150)
    raise TimeoutError(expression)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int)
    args = parser.parse_args()
    report = {"external_requests": [], "page_errors": [], "console_errors": [], "checks": {}}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe", headless=True, args=["--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1512, "height": 1050}, device_scale_factor=1)
        page = context.new_page()
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)

        def route_external(route):
            if route.request.url.startswith(BASE + "/") or route.request.url.startswith("data:"):
                route.continue_()
            else:
                report["external_requests"].append(route.request.url)
                route.abort()

        context.route("**/*", route_external)
        page.goto(BASE, wait_until="domcontentloaded")
        wait_for(page, "window.partitionApp.initialised && window.partitionApp.ready", timeout=90000)
        report["checks"]["initial_rows"] = page.evaluate("window.partitionApp.result.summary.addresses")
        assert report["checks"]["initial_rows"] == 21507
        page.locator("#demo-button").click()
        wait_for(page, "!document.getElementById('run-button').disabled", timeout=30000)
        assert "21,507" in page.locator("#input-receipt").inner_text()
        report["checks"]["demo_input"] = True
        # Duplicate service IDs fail while the previous valid input/result remain visible.
        page.locator("#file-input").set_input_files({"name": "duplicate.csv", "mimeType": "text/csv", "buffer": b"AddressId,Latitude,Longitude,Day\n7,49.85,-97.2,MONDAY\n7,49.85,-97.2,MONDAY\n"})
        wait_for(page, "document.getElementById('notice').classList.contains('error')")
        assert "duplicated" in page.locator("#notice").inner_text()
        assert page.evaluate("window.partitionApp.result.summary.addresses") == 21507
        report["checks"]["invalid_upload_preserves_result"] = True
        # Delivered Excel uses a title/summary block and a Monday sheet; no Sheet1 union.
        page.locator("#file-input").set_input_files(str(ROOT / "outputs/2026-11-04_monday_map/Monday_addresses_lat_long.xlsx"))
        wait_for(page, "!document.getElementById('run-button').disabled && document.getElementById('input-receipt').textContent.includes('.xlsx')", timeout=45000)
        assert "21,507" in page.locator("#input-receipt").inner_text()
        report["checks"]["xlsx_upload"] = True
        page.locator("#demo-button").click()
        wait_for(page, "!document.getElementById('run-button').disabled && document.getElementById('input-receipt').textContent.includes('.csv')")
        if args.target:
            page.locator("#target-mode").click()
            page.locator("#target-input").fill(str(args.target))
        else:
            page.locator("#natural-mode").click()
        page.locator("#run-button").click()
        wait_for(page, "window.partitionApp.activeJob", timeout=5000)
        print("Waiting for the actual Monday partition...", flush=True)
        wait_for(page, "!window.partitionApp.activeJob", timeout=600000)
        result = page.evaluate("window.partitionApp.result")
        assert result["summary"]["addresses"] == 21507
        assert result["status"] == "PROVISIONAL", result["findings"]
        assert result["validation"]["exactly_once"]
        assert not result["summary"]["errors"]
        if args.target:
            assert result["settings"]["target_addresses"] == args.target
        report["result"] = {"key": result["key"], "hash": result["partition_hash"], "summary": result["summary"], "validation": result["validation"]}
        print(json.dumps(report["result"], indent=2), flush=True)
        page.locator("#area-search").fill("49738")
        page.locator(".record-match").first.click()
        assert "2194 WEST TAYLOR BLVD" in page.locator(".leaflet-popup").inner_text()
        assert "User supplied" in page.locator(".leaflet-popup").inner_text()
        page.locator(".leaflet-popup-close-button").click()
        page.locator("#area-search").fill("")
        page.locator(".area-row").first.click()
        assert not page.locator("#selected-detail").is_hidden()
        page.locator("#clear-selection").click()
        page.locator("#fit-button").click()
        page.locator("#points-button").click()
        assert page.locator("#points-button").get_attribute("aria-pressed") == "false"
        page.locator("#points-button").click()
        page.locator("#checks-tab").click()
        assert "Source coverage" in page.locator("#checks-list").inner_text()
        page.locator("#sources-tab").click()
        assert "City of Winnipeg" in page.locator("#sources-list").inner_text()
        page.locator("#areas-tab").click()
        report["checks"]["search_selection_layers_tabs"] = True
        page.screenshot(path=str(AUDIT / "ui-desktop.png"), full_page=True)
        report["checks"]["desktop_overflow"] = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        assert not report["checks"]["desktop_overflow"]
        assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight + 2")
        request_count = len(report["external_requests"])
        # This is a stationary local canvas check; no public basemap has been created.
        page.wait_for_timeout(1500)
        assert len(report["external_requests"]) == request_count == 0
        assert page.evaluate("window.partitionApp.mapInstances") == 1
        assert page.evaluate("window.partitionApp.basemapInstances") == 0
        report["checks"]["stationary_external_requests"] = 0
        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        mobile.goto(BASE, wait_until="domcontentloaded")
        wait_for(mobile, "window.partitionApp.initialised && window.partitionApp.ready", timeout=60000)
        assert not mobile.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        mobile.screenshot(path=str(AUDIT / "ui-mobile.png"), full_page=True)
        report["checks"]["mobile_overflow"] = False
        browser.close()
    key = report["result"]["key"]
    response = requests.get(BASE + f"/api/download?key={key}&kind=assignments", timeout=20)
    response.raise_for_status()
    assignments = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(assignments) == 21507 and len({r["AddressId"] for r in assignments}) == 21507
    assert all(row["GarbageCollectionDay"] == "MONDAY" and row["PartitionAreaId"] for row in assignments)
    report["checks"]["export_rows_and_ids"] = len(assignments)
    assert not report["page_errors"], report["page_errors"]
    assert not report["external_requests"], report["external_requests"]
    (AUDIT / f"ui-validation-{'target' if args.target else 'natural'}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Local UI checks passed; zero external requests.", flush=True)


if __name__ == "__main__":
    main()
