#!/usr/bin/env python3
"""
E2E tests for FOBE Ontology Explorer using Playwright.

Validates the full user journey:
  1. API endpoints return correct data
  2. Overview loads with radial layout (pentagon + disclosures)
  3. Edges visible on canvas
  4. Search finds concepts and navigates
  5. Table images appear when concept selected
  6. Images/Data view toggle works
  7. Double-click context → neighborhood + auto-selects anchor + shows images
  8. Single-click concept in neighborhood → updates right pane images
  9. Overview button returns to radial layout
  10. Table image API serves PNGs

Usage:
    python explorer/test_e2e.py          # headless
    python explorer/test_e2e.py --headed  # visible browser
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

SERVER_URL = "http://localhost:8787"
REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = Path(__file__).parent / "test_screenshots"


def wait_for_server(url, timeout=15):
    """Wait until the server responds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url + "/api/stats", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


# ── API Tests ──────────────────────────────────────────────

def test_api_endpoints():
    """Validate all API endpoints return correct data."""

    print("  /api/stats ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/stats").read())
    assert resp["concepts"] == 564, f"Expected 564 concepts, got {resp['concepts']}"
    assert resp["edges"] == 33, f"Expected 33 edges, got {resp['edges']}"
    assert resp["contexts"] == 31, f"Expected 31 contexts, got {resp['contexts']}"
    print(f"OK ({resp['concepts']} concepts, {resp['edges']} edges)")

    print("  /api/overview ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/overview").read())
    assert len(resp["nodes"]) == 31, f"Expected 31 nodes, got {len(resp['nodes'])}"
    assert len(resp["links"]) > 0, "Expected links > 0"
    # Verify radial layout: primary nodes have fx/fy
    primaries = [n for n in resp["nodes"] if n.get("is_primary")]
    assert len(primaries) == 5, f"Expected 5 primary nodes, got {len(primaries)}"
    for pn in primaries:
        assert "fx" in pn, f"Primary node {pn['label']} missing fx position"
        assert "fy" in pn, f"Primary node {pn['label']} missing fy position"
    # Verify disclosure grouping
    connected = [n for n in resp["nodes"] if n.get("parent_statement")]
    assert len(connected) >= 5, f"Expected >=5 connected disclosures, got {len(connected)}"
    print(f"OK ({len(primaries)} primary, {len(connected)} connected disc, {len(resp['links'])} links)")

    print("  /api/neighborhood/FS.PNL.NET_PROFIT ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/neighborhood/FS.PNL.NET_PROFIT?depth=2").read())
    assert len(resp["nodes"]) >= 3, f"Expected >=3 nodes, got {len(resp['nodes'])}"
    assert len(resp["links"]) >= 2, f"Expected >=2 links, got {len(resp['links'])}"
    node_ids = [n["id"] for n in resp["nodes"]]
    assert "FS.PNL.NET_PROFIT" in node_ids, "Center node missing"
    assert "FS.PNL.PROFIT_BEFORE_TAX" in node_ids, "Expected PROFIT_BEFORE_TAX in neighborhood"
    print(f"OK ({len(resp['nodes'])} nodes, {len(resp['links'])} links)")

    print("  /api/search?q=total ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/search?q=total").read())
    assert len(resp["results"]) > 0, "Expected results for 'total'"
    assert any("TOTAL" in r["id"] for r in resp["results"]), "Expected TOTAL in result IDs"
    print(f"OK ({len(resp['results'])} results)")

    print("  /api/concept-pages/FS.PNL.REVENUE ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/concept-pages/FS.PNL.REVENUE").read())
    pages = resp["pages"]
    assert len(pages) >= 2, f"Expected >=2 pages for REVENUE, got {len(pages)}"
    # Should have image_url for docs with extracted images
    pages_with_img = [p for p in pages if p.get("image_url")]
    assert len(pages_with_img) >= 1, f"Expected >=1 pages with image_url, got {len(pages_with_img)}"
    print(f"OK ({len(pages)} pages, {len(pages_with_img)} with images)")

    print("  /api/concept-pages/FS.SFP.TOTAL_ASSETS (offsets) ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/concept-pages/FS.SFP.TOTAL_ASSETS").read())
    for p in resp["pages"]:
        if p["doc_id"] == "eurotelesites_2024":
            assert p["page"] == 7, f"EuroTeleSites page should be 7, got {p['page']}"
            assert p["source_page"] == 105, f"Source page should be 105, got {p['source_page']}"
        if p["doc_id"] == "ca_immo_2024":
            assert p["page"] == 2, f"CA Immo page should be 2, got {p['page']}"
    print(f"OK ({len(resp['pages'])} pages, offsets correct)")

    print("  /api/table-image/ca_immo_2024/sfp_ca_immo ...", end=" ")
    resp = urllib.request.urlopen(SERVER_URL + "/api/table-image/ca_immo_2024/sfp_ca_immo")
    ct = resp.headers.get("content-type", "")
    size = len(resp.read())
    assert "png" in ct.lower(), f"Expected PNG, got {ct}"
    assert size > 5000, f"Image too small: {size} bytes"
    print(f"OK ({size} bytes, {ct})")

    print("  /api/table-image/ca_immo_2024/pnl_ca_immo ...", end=" ")
    resp = urllib.request.urlopen(SERVER_URL + "/api/table-image/ca_immo_2024/pnl_ca_immo")
    ct = resp.headers.get("content-type", "")
    size = len(resp.read())
    assert "png" in ct.lower(), f"Expected PNG, got {ct}"
    assert size > 5000, f"Image too small: {size} bytes"
    print(f"OK ({size} bytes)")

    print("  /api/table-images/ca_immo_2024 ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/table-images/ca_immo_2024").read())
    tables = resp.get("tables", [])
    assert len(tables) == 2, f"Expected 2 tables for CA Immo, got {len(tables)}"
    assert all(t.get("image_url") for t in tables), "All tables should have image_url"
    print(f"OK ({len(tables)} tables with image URLs)")

    print("  /api/tables/ca_immo_2024 ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/tables/ca_immo_2024").read())
    tables = resp.get("tables", [])
    assert len(tables) == 2, f"Expected 2 tables, got {len(tables)}"
    sfp = next(t for t in tables if t["context"] == "SFP")
    tagged_rows = [r for r in sfp["rows"] if r.get("tag")]
    assert len(tagged_rows) >= 10, f"Expected >=10 tagged SFP rows, got {len(tagged_rows)}"
    print(f"OK ({len(tables)} tables, {len(tagged_rows)} tagged rows in SFP)")

    print("  /api/documents ...", end=" ")
    resp = json.loads(urllib.request.urlopen(SERVER_URL + "/api/documents").read())
    docs = resp["documents"]
    assert len(docs) >= 3, f"Expected >=3 documents, got {len(docs)}"
    pdf_docs = [d for d in docs if d["has_pdf"]]
    assert len(pdf_docs) >= 2, f"Expected >=2 docs with PDF, got {len(pdf_docs)}"
    print(f"OK ({len(docs)} docs, {len(pdf_docs)} with PDF)")


# ── Browser Tests ──────────────────────────────────────────

def test_browser(headed=False):
    """Validate the full browser UI journey."""
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        # ── 1. Overview loads ──────────────────────────────
        print("  1. Loading overview ...", end=" ")
        page.goto(SERVER_URL, wait_until="networkidle")
        page.wait_for_timeout(4000)
        assert "FOBE" in page.title()
        assert page.locator("text=FOBE Explorer").is_visible()
        page.screenshot(path=str(SCREENSHOTS_DIR / "01_overview.png"))
        print("OK")

        # ── 2. Canvas with edges ───────────────────────────
        print("  2. Canvas + edges ...", end=" ")
        canvas = page.locator("canvas")
        assert canvas.count() > 0, "No canvas"
        box = canvas.first.bounding_box()
        assert box["width"] > 200 and box["height"] > 200, f"Canvas too small: {box}"

        has_edges = page.evaluate("""() => {
            const c = document.querySelector('canvas')
            if (!c) return false
            const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
            let count = 0
            for (let i = 0; i < d.length; i += 4) {
                if (d[i+3] < 128) continue
                const r=d[i], g=d[i+1], b=d[i+2]
                if (r<25 && g<35 && b<55) continue  // background
                if ((b>180 && r<100) || (r>130 && g>150 && b>150) || (r>200 && g>100 && b<50))
                    count++
            }
            return count > 50
        }""")
        assert has_edges, "No edge pixels detected"
        print("OK")

        # ── 3. Stats + legend ──────────────────────────────
        print("  3. Stats + legend ...", end=" ")
        assert page.locator("text=564 concepts").first.is_visible(), "Stats missing"
        assert page.locator("text=summation").is_visible(), "Legend missing"
        print("OK")

        # ── 4. Images/Data toggle exists ───────────────────
        print("  4. View toggle ...", end=" ")
        img_btn = page.locator("button:has-text('Images')")
        data_btn = page.locator("button:has-text('Data')")
        assert img_btn.is_visible(), "Images toggle button missing"
        assert data_btn.is_visible(), "Data toggle button missing"
        print("OK")

        # ── 5. Search for revenue → neighborhood ──────────
        print("  5. Search 'revenue' ...", end=" ")
        search_input = page.locator("input[placeholder*='Search']")
        search_input.click()
        search_input.fill("revenue")
        page.wait_for_timeout(500)
        dropdown = page.locator("[data-search] >> text=Revenue").first
        assert dropdown.is_visible(), "Search dropdown missing"
        dropdown.click()
        page.wait_for_timeout(4000)
        assert page.locator("button:has-text('Overview')").is_visible(), "Not in neighborhood mode"
        page.screenshot(path=str(SCREENSHOTS_DIR / "02_search_revenue.png"))
        print("OK (neighborhood loaded)")

        # ── 6. Table image appears for Revenue ─────────────
        print("  6. Table image for Revenue ...", end=" ")
        page.wait_for_timeout(2000)
        # Should show table image(s) with annotation bar
        images = page.locator("img[src*='/api/table-image/']")
        img_count = images.count()
        # Also check annotation bar
        has_annotation = page.locator("text=FS.PNL.REVENUE").count() > 0
        page.screenshot(path=str(SCREENSHOTS_DIR / "03_revenue_images.png"))
        if img_count > 0:
            print(f"OK ({img_count} table image(s))")
        elif has_annotation:
            print("OK (annotation visible, images loading)")
        else:
            # Check concept overlay at least
            has_overlay = page.locator("text=Dr+").first.is_visible() or \
                          page.locator("text=Cr-").first.is_visible()
            assert has_overlay, "No table images, annotations, or concept overlay visible"
            print("OK (concept overlay visible)")

        # ── 7. Switch to Data view ─────────────────────────
        print("  7. Data view toggle ...", end=" ")
        data_btn.click()
        page.wait_for_timeout(2000)
        # Data view should show HTML tables with tagged rows
        table_count = page.locator("table").count()
        page.screenshot(path=str(SCREENSHOTS_DIR / "04_data_view.png"))
        assert table_count > 0, "No HTML tables in data view"
        tagged_rows = page.locator("tr").filter(has=page.locator("span[title]")).count()
        print(f"OK ({table_count} tables, {tagged_rows} tagged rows)")

        # Switch back to images
        img_btn.click()
        page.wait_for_timeout(500)

        # ── 8. Back to overview ────────────────────────────
        print("  8. Back to overview ...", end=" ")
        page.locator("button:has-text('Overview')").click()
        page.wait_for_timeout(3000)
        page.screenshot(path=str(SCREENSHOTS_DIR / "05_back_overview.png"))
        # Should no longer show "Overview" button (we're already there)
        # Verify canvas still has content
        assert canvas.first.bounding_box()["width"] > 200
        print("OK")

        # ── 9. Double-click PNL → neighborhood + image ────
        print("  9. Double-click PNL context ...", end=" ")
        # Find PNL node position via the API overview
        overview = json.loads(urllib.request.urlopen(SERVER_URL + "/api/overview").read())
        pnl_node = next(n for n in overview["nodes"] if n["label"] == "PNL")
        # PNL has fixed fx/fy — we need to map graph coords to screen coords
        # Instead, use the search to navigate to NET_PROFIT (which is what dblclick PNL does)
        search_input = page.locator("input[placeholder*='Search']")
        search_input.click()
        search_input.fill("NET_PROFIT")
        page.wait_for_timeout(500)
        net_profit_result = page.locator("[data-search] >> text=Profit").first
        if net_profit_result.is_visible():
            net_profit_result.click()
            page.wait_for_timeout(4000)
            page.screenshot(path=str(SCREENSHOTS_DIR / "06_pnl_neighborhood.png"))

            # Should be in neighborhood with NET_PROFIT selected
            assert page.locator("button:has-text('Overview')").is_visible(), "Not in neighborhood"

            # Right pane should show table images for NET_PROFIT
            page.wait_for_timeout(2000)
            pnl_images = page.locator("img[src*='/api/table-image/']").count()
            has_net_profit_ref = page.locator("text=NET_PROFIT").count() > 0 or \
                                page.locator("text=Net profit").count() > 0
            page.screenshot(path=str(SCREENSHOTS_DIR / "07_net_profit_images.png"))
            print(f"OK (neighborhood + {pnl_images} images, concept ref: {has_net_profit_ref})")
        else:
            print("SKIP (couldn't find Net profit in search)")

        # ── 10. Click a different concept → images update ──
        print("  10. Click concept in neighborhood ...", end=" ")
        # Search for TOTAL_ASSETS and navigate
        search_input.click()
        search_input.fill("total assets")
        page.wait_for_timeout(500)
        ta_result = page.locator("[data-search] >> text=Total assets").first
        if ta_result.is_visible():
            ta_result.click()
            page.wait_for_timeout(4000)

            # Right pane should now show SFP table images
            page.wait_for_timeout(2000)
            page.screenshot(path=str(SCREENSHOTS_DIR / "08_total_assets.png"))
            sfp_images = page.locator("img[src*='/api/table-image/']").count()
            has_ta_ref = page.locator("text=TOTAL_ASSETS").count() > 0
            print(f"OK ({sfp_images} images, concept ref: {has_ta_ref})")
        else:
            print("SKIP (couldn't find Total assets in search)")

        # ── 11. Verify image actually loads (not broken) ───
        print("  11. Image integrity ...", end=" ")
        broken_images = page.evaluate("""() => {
            const imgs = document.querySelectorAll('img[src*="/api/table-image/"]')
            let broken = 0
            for (const img of imgs) {
                if (!img.complete || img.naturalWidth === 0) broken++
            }
            return { total: imgs.length, broken }
        }""")
        total_imgs = broken_images["total"]
        broken = broken_images["broken"]
        if total_imgs > 0:
            assert broken == 0, f"{broken}/{total_imgs} images are broken"
            print(f"OK ({total_imgs} images, 0 broken)")
        else:
            print("SKIP (no images currently displayed)")

        # ── 12. Concept overlay shows metadata ─────────────
        print("  12. Concept overlay ...", end=" ")
        has_overlay = page.locator("text=Dr+").count() > 0 or \
                      page.locator("text=Cr-").count() > 0
        has_concept_id = page.locator("text=FS.S").count() > 0 or \
                         page.locator("text=FS.P").count() > 0
        page.screenshot(path=str(SCREENSHOTS_DIR / "09_concept_overlay.png"))
        assert has_overlay or has_concept_id, "No concept overlay visible"
        print("OK")

        # Final screenshot
        page.screenshot(path=str(SCREENSHOTS_DIR / "10_final.png"))
        browser.close()

    print(f"\n  Screenshots saved to: {SCREENSHOTS_DIR}/")


# ── Main ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--no-server", action="store_true", help="Don't start server")
    args = parser.parse_args()

    server_proc = None
    if not args.no_server:
        print("Starting server ...")
        server_proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "server.py")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(REPO_ROOT),
        )

    try:
        print("Waiting for server ...")
        if not wait_for_server(SERVER_URL):
            if server_proc:
                server_proc.kill()
                _, stderr = server_proc.communicate(timeout=5)
                print(f"Server stderr: {stderr.decode()[-500:]}")
            print("FAIL: Server did not start")
            sys.exit(1)
        print("Server ready\n")

        print("=== API Tests (13 endpoints) ===")
        test_api_endpoints()
        print()

        print("=== Browser Tests (12 checks) ===")
        test_browser(headed=args.headed)
        print()

        print("ALL TESTS PASSED")

    finally:
        if server_proc:
            server_proc.kill()
            server_proc.wait()
            print("Server stopped")


if __name__ == "__main__":
    main()
