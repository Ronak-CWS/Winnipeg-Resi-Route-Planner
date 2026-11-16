"""Replay the existing OpenFreeMap overview cache in the app; no upstream allowed."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from verify_partitioner_ui import AUDIT, BASE, wait_for


def main():
    report={"external_attempts":[],"page_errors":[]}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True,args=["--enable-unsafe-swiftshader"])
        context=browser.new_context(viewport={"width":1512,"height":1050},device_scale_factor=1)
        def guard(route):
            if route.request.url.startswith(BASE+"/") or route.request.url.startswith("data:"):
                route.continue_()
            else:
                report["external_attempts"].append(route.request.url)
                route.abort()
        context.route("**/*",guard)
        page=context.new_page()
        page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
        page.goto(BASE,wait_until="domcontentloaded")
        wait_for(page,"window.partitionApp.initialised && window.partitionApp.ready && !window.partitionApp.activeJob",timeout=600000)
        # The Leaflet bridge uses GL's 512 px tiles, one zoom below Leaflet.
        page.evaluate("window.partitionMap.setView([49.87,-97.20],11,{animate:false})")
        page.locator("#basemap-button").click()
        wait_for(page,"window.partitionBasemap && (window.partitionBasemap.policy.stopped || (window.partitionBasemap.map.isStyleLoaded() && window.partitionBasemap.map.areTilesLoaded()))",timeout=30000)
        report["policy"]=page.evaluate("window.partitionBasemap.policy.snapshot()")
        report["ready"]=page.evaluate("window.partitionBasemap.map.isStyleLoaded() && window.partitionBasemap.map.areTilesLoaded()")
        assert not report["policy"]["stopped"],report
        assert report["ready"] and not report["external_attempts"] and not report["page_errors"],report
        page.evaluate("window.__idleFrames=0;window.partitionBasemap.map.on('render',()=>window.__idleFrames++)")
        page.wait_for_timeout(1500)
        report["stationary_render_frames"]=page.evaluate("window.__idleFrames")
        report["stationary_policy"]=page.evaluate("window.partitionBasemap.policy.snapshot()")
        assert report["stationary_policy"]["started"]==report["policy"]["started"]
        assert report["stationary_render_frames"]==0,report
        assert page.evaluate("window.partitionApp.mapInstances===1 && window.partitionApp.basemapInstances===1")
        page.locator("#basemap-button").click()
        page.locator("#basemap-button").click()
        assert page.evaluate("window.partitionApp.basemapInstances===1")
        report["single_map_and_basemap"]=True
        report["upstream_requests"]=0
        page.screenshot(path=str(AUDIT/"ui-cached-basemap.png"),full_page=True)
        browser.close()
    (AUDIT/"basemap-integration-validation.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
