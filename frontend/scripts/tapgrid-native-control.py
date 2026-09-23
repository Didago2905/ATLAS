"""One native two-finger double tap; standard-library HTTP only.

Without --run: print the plan, make NO requests and create NO files.
With --run: one Safari session, one W3C actions request, no gesture retries.
Credentials: BROWSERSTACK_USERNAME / BROWSERSTACK_ACCESS_KEY (environment only).
ATLAS_PUBLIC_URL or --url supplies the current public origin.

Public references:
https://www.browserstack.com/docs/automate/api-reference/selenium/browser
https://www.browserstack.com/docs/automate/selenium/test-file-upload
https://www.browserstack.com/docs/automate/selenium/handle-permission-pop-ups
https://github.com/appium/appium/blob/master/packages/base-driver/docs/mjsonwp/protocol-methods.md
https://github.com/appium/appium-xcuitest-driver/blob/master/docs/guides/gestures.md
https://www.w3.org/TR/webdriver/#actions

DOM/native image identity and safe geometry must survive revalidation.
This is a restricted mapping, not a general coordinate calibration. Uncertainty
about delivery or infrastructure always makes the result INCONCLUSIVE.
"""

import argparse
import base64
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


HUB = "https://hub.browserstack.com/wd/hub"
CATALOG = "https://api.browserstack.com/automate/browsers.json"
DEVICE = "iPhone 13 Pro Max"
IOS = "18"  # Exact os_version returned by Automate's catalog; not a patch version.
ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"

READY = """
const lab = window.ATLAS_TAP_TIMING_LAB;
if (!lab || !lab.exportSession || !lab.reset) return null;
const mode = localStorage.getItem('tap_grid_mode');
if (!['focus', 'gallery'].includes(mode)) return null;
const vv = window.visualViewport;
if (vv && (Math.abs(vv.scale - 1) > .01 || Math.abs(vv.offsetTop) > 1 ||
           Math.abs(vv.offsetLeft) > 1)) return null;
for (const card of document.querySelectorAll('[data-atlas-tap-card]')) {
  const r = card.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = (Math.max(0, r.top) + Math.min(innerHeight, r.bottom)) / 2;
  const points = [{x: x - 24, y}, {x: x + 24, y}];
  if (points.every(p => p.x > Math.max(0, r.left) + 16 &&
      p.x < Math.min(innerWidth, r.right) - 16 &&
      p.y > Math.max(0, r.top) + 16 && p.y < Math.min(innerHeight, r.bottom) - 16 &&
      [-8, 0, 8].every(dx => [-8, 0, 8].every(dy =>
        document.elementFromPoint(p.x + dx, p.y + dy)?.closest('[data-atlas-tap-card]') === card)))) {
    const cardImage = card.querySelector(':scope > img');
    const imageRect = cardImage?.getBoundingClientRect();
    const flowElements = ['.home-controls__museum img', 'img.home-catalog-icon'].map(selector => {
      const matches = document.querySelectorAll(selector);
      const element = matches.length === 1 ? matches[0] : null;
      const bounds = element?.getBoundingClientRect();
      return {selector, matchCount: matches.length, complete: element?.complete ?? null,
        naturalWidth: element?.naturalWidth ?? null, naturalHeight: element?.naturalHeight ?? null,
        rect: bounds ? {x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height} : null};
    });
    const flowResources = {elements: flowElements, ready: flowElements.every(element =>
      element.matchCount === 1 && element.complete === true &&
      element.naturalWidth > 0 && element.naturalHeight > 0 && element.rect &&
      Object.values(element.rect).every(Number.isFinite) &&
      element.rect.width > 0 && element.rect.height > 0)};
    return {mode, points, cardId: card.dataset.atlasTapCard,
      flowResources,
      width: innerWidth, height: innerHeight, url: location.href,
      cardRect: {x: r.x, y: r.y, width: r.width, height: r.height},
      cardImageRect: imageRect ? {x: imageRect.x, y: imageRect.y, width: imageRect.width, height: imageRect.height} : null,
      cardImageAlt: cardImage?.alt ?? null,
      userAgent: navigator.userAgent, dpr: devicePixelRatio,
      visualViewport: vv ? {width: vv.width, height: vv.height, scale: vv.scale} : null};
  }
}
return null;
"""
EXPORT = """
const session = window.ATLAS_TAP_TIMING_LAB?.exportSession() || null;
const primitive = value => value === null || typeof value === 'string' || typeof value === 'boolean'
  || (typeof value === 'number' && Number.isFinite(value)) ? value : null;
const pick = (source, fields) => Object.fromEntries(fields.map(key => [key, primitive(source?.[key])]));
const touchFields = ['identifier', 'clientX', 'clientY', 'pageX', 'pageY', 'screenX', 'screenY'];
const eventFields = ['type', 'at', 'raw', 'sequence', 'eventType', 'eventTimeStamp',
  'dateNowRelativeMs', 'touchesLength', 'changedTouchesLength', 'rawEventSequence',
  'classification', 'recognized', 'deltaMs', 'lastTouchTimeBefore', 'lastTouchTimeAfter',
  'thresholdMs', 'modeBefore', 'modeAfter'];
const trace = Array.isArray(session?.trace) ? session.trace.map(event => {
  const plain = pick(event, eventFields);
  for (const key of ['touches', 'changedTouches']) {
    plain[key] = Array.isArray(event?.[key]) ? event[key].map(touch => pick(touch, touchFields)) : null;
  }
  plain.identifiers = Array.isArray(event?.identifiers) ? event.identifiers.map(primitive) : null;
  return plain;
}) : null;
return {mode: localStorage.getItem('tap_grid_mode'), url: location.href,
  lab: session ? {meta: pick(session.meta,
    ['lab', 'version', 'exportedAt', 'location', 'userAgent', 'thresholdMs']), trace} : null};
"""


def gesture(points):
    return {"actions": [
        {"type": "pointer", "id": f"finger-{i + 1}",
         "parameters": {"pointerType": "touch"}, "actions": [
             {"type": "pointerMove", "duration": 0, "origin": "viewport",
              "x": round(p["x"]), "y": round(p["y"])},
             {"type": "pointerDown", "button": 0},
             {"type": "pause", "duration": 60},
             {"type": "pointerUp", "button": 0},
             {"type": "pause", "duration": 140},
             {"type": "pointerDown", "button": 0},
             {"type": "pause", "duration": 60},
             {"type": "pointerUp", "button": 0},
         ]} for i, p in enumerate(points)
    ]}


def assess_input(trace):
    """Reconstruct contact episodes from raw touches, not RAW event counts."""
    evidence = {"episodes": [], "rawEvents": [], "physicalChordEvents": [],
                "fullReleaseEvents": [], "problems": [], "chordToChordMs": None}
    active = None
    last_at = -1
    for event in trace:
        kind = event.get("type")
        if kind in ("NEW_PHYSICAL_CHORD", "SAME_PHYSICAL_CHORD"):
            evidence["physicalChordEvents"].append(event)
        if kind == "FULL_RELEASE":
            evidence["fullReleaseEvents"].append(event)
        if kind == "CANCEL":
            evidence["problems"].append("Touch cancellation observed")
        if kind not in ("TOUCHSTART", "TOUCHEND"):
            continue
        evidence["rawEvents"].append(event)
        at = event.get("at")
        touches = event.get("touches")
        if (not isinstance(at, (int, float)) or at < last_at or
                not isinstance(touches, list) or len(touches) != event.get("touchesLength")):
            evidence["problems"].append("Missing/inconsistent raw timestamp or touch list")
            continue
        last_at = at
        identifiers = [t.get("identifier") for t in touches]
        if any(not isinstance(i, (int, float)) for i in identifiers) or len(set(identifiers)) != len(identifiers):
            evidence["problems"].append("Missing or duplicate contact identifiers")
            continue
        if len(touches) > 2:
            evidence["problems"].append("More than two simultaneous contacts")
        if touches and active is None:
            if kind != "TOUCHSTART":
                evidence["problems"].append("Episode starts without TOUCHSTART")
            active = {"start": event, "chord": None, "release": None}
        if active is not None and len(touches) == 2:
            if active["chord"] is None:
                if kind != "TOUCHSTART":
                    evidence["problems"].append("Two-contact chord lacks TOUCHSTART")
                active["chord"] = event
            elif set(identifiers) != {t["identifier"] for t in active["chord"]["touches"]}:
                evidence["problems"].append("Contacts changed before full release")
        if kind == "TOUCHEND" and not touches and active is not None:
            active["release"] = event
            evidence["episodes"].append(active)
            active = None
    episodes = evidence["episodes"]
    if active is not None:
        evidence["problems"].append("Last contact episode was not fully released")
    if len(episodes) != 2 or any(e["chord"] is None for e in episodes):
        evidence["problems"].append("Expected two complete two-contact episodes")
    else:
        first, second = episodes
        delta = second["chord"]["at"] - first["chord"]["at"]
        evidence["chordToChordMs"] = delta
        if not (first["chord"]["at"] < first["release"]["at"] < second["start"]["at"]
                <= second["chord"]["at"] < second["release"]["at"]):
            evidence["problems"].append("Chords are not separated by complete releases")
        # A delivered but out-of-window gesture cannot judge the recognizer.
        if not 0 < delta < 350:
            evidence["problems"].append("Observed chord-to-chord interval is outside the productive window")
        for episode in episodes:
            release_at = episode["release"]["at"]
            if not any(e.get("at") == release_at for e in evidence["fullReleaseEvents"]):
                evidence["problems"].append("Missing FULL_RELEASE evidence")
    return not evidence["problems"], evidence


def main():
    username = os.environ.get("BROWSERSTACK_USERNAME", "")
    key = os.environ.get("BROWSERSTACK_ACCESS_KEY", "")
    token = base64.b64encode(f"{username}:{key}".encode()).decode() if username and key else ""
    auth = "Basic " + token if token else ""
    secrets = {s for s in (username, key, token, auth, f"{username}:{key}" if token else "") if s}
    for _ in range(2):
        for secret in list(secrets):
            for encoded in (urllib.parse.quote(secret, safe=""), urllib.parse.quote_plus(secret, safe="")):
                secrets.add(encoded)
                # Percent escapes are case-insensitive; providers may lowercase them.
                secrets.add(re.sub(r"%[0-9A-Fa-f]{2}", lambda m: m.group().lower(), encoded))
    secrets = sorted(secrets, key=len, reverse=True)

    def sanitize(value):
        if isinstance(value, dict):
            return {sanitize(str(k)): ("[REDACTED]" if any(part in str(k).lower()
                    for part in ("accesskey", "access_key", "username", "authorization")) else sanitize(v))
                    for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [sanitize(v) for v in value]
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]")
            return value
        return value

    def emit(value):
        print(json.dumps(sanitize(value), indent=2, ensure_ascii=False))

    preflight_failure = {"result": "INCONCLUSIVE", "reason": "preflight failure",
                         "inputValid": None, "gestureSent": False, "recognizerEvaluated": False,
                         "toggleRecognized": None, "modeBefore": None, "modeAfter": None}
    parser = argparse.ArgumentParser(description=__doc__, exit_on_error=False)
    parser.add_argument("--url", default=os.environ.get("ATLAS_PUBLIC_URL"))
    parser.add_argument("--run", action="store_true", help="Create ONE paid/limited remote session")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default=DEVICE)
    parser.add_argument("--ios", default=IOS)
    try:
        args, unknown = parser.parse_known_args()
        if unknown:
            emit({**preflight_failure, "reason": "preflight failure: unrecognized arguments"})
            return 1
    except argparse.ArgumentError as error:
        emit({**preflight_failure, "reason": "preflight failure: " + str(error)})
        return 1
    try:
        origin = urllib.parse.urlsplit(args.url or "")
        origin.port  # Validate the port before any request.
    except ValueError:
        emit({**preflight_failure, "reason": "preflight failure: invalid ATLAS URL"})
        return 1
    if origin.scheme not in ("http", "https") or not origin.hostname or origin.username or origin.password:
        emit({**preflight_failure, "reason": "preflight failure: provide a public HTTP(S) origin without embedded credentials"})
        return 1
    target = urllib.parse.urlunsplit((origin.scheme, origin.netloc, "/", "tapTimingLab=1", ""))
    caps = {"platformName": "iOS", "browserName": "Safari",
            "appium:automationName": "XCUITest", "appium:newCommandTimeout": 60,
            "bstack:options": {"deviceName": args.device, "osVersion": args.ios,
                               "realMobile": True, "deviceOrientation": "portrait",
                               "local": False, "idleTimeout": 60,
                               "projectName": "ATLAS", "sessionName": "TapGrid native control: one gesture"}}
    if not args.run:
        emit({"createsSession": False, "target": target, "endpoint": HUB,
                          "capabilities": caps, "chordToChordMs": 200,
                          "gestureAtExampleCoordinates": gesture([{"x": 100, "y": 300}, {"x": 148, "y": 300}])})
        return 0
    if not username or not key:
        emit({**preflight_failure, "reason": "preflight failure: BrowserStack credentials missing; no session created"})
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        output = args.output or Path(__file__).resolve().parents[1] / "tests/results/tapgrid-native-control" / f"{stamp}.json"
    except Exception as error:
        emit({**preflight_failure, "reason": "preflight failure: " + str(error)})
        return 1
    result = {"startedAt": stamp, "target": target, "endpoint": HUB,
              "requestedCapabilities": caps, "contexts": [], "errors": [],
              "result": "INCONCLUSIVE", "reason": "Preparation not completed",
              "inputValid": None, "gestureSent": False, "recognizerEvaluated": False,
              "toggleRecognized": None, "modeBefore": None, "modeAfter": None,
              "sessionId": None, "sessionDeleted": False}
    sid = None
    web_context = None
    stage = "preflight"
    output_reserved = False

    def request(method, url, body=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": auth, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"{method} {url}: HTTP {error.code}: {sanitize(detail)}") from None
        value = payload.get("value") if isinstance(payload, dict) else payload
        if isinstance(value, dict) and value.get("error"):
            raise RuntimeError(f"{method} {url}: {json.dumps(sanitize(value))}")
        return payload

    def command(method, path, body=None, timeout=10):
        return request(method, f"{HUB}/session/{sid}{path}", body, timeout).get("value")

    def script(code):
        return command("POST", "/execute/sync", {"script": code, "args": []})

    def context(name):
        command("POST", "/context", {"name": name})
        actual = command("GET", "/context")
        result["contexts"].append({"requested": name, "actual": actual})
        if actual != name:
            raise RuntimeError(f"Context switch failed: {name} -> {actual}")

    def geometry_metrics(sample):
        if sample is None:
            return None
        metrics = []
        for name in ("cardRect", "cardImageRect"):
            box = sample.get(name)
            if (not isinstance(box, dict) or
                    not all(isinstance(box.get(k), (int, float)) and not isinstance(box[k], bool)
                            and math.isfinite(box[k]) for k in ("x", "y", "width", "height")) or
                    box["width"] <= 0 or box["height"] <= 0):
                return None
            metrics.extend((box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                            box["width"], box["height"]))
        sample_points = sample.get("points")
        if not isinstance(sample_points, list) or len(sample_points) != 2:
            return None
        for point in sample_points:
            if (not isinstance(point, dict) or
                    not all(isinstance(point.get(k), (int, float)) and not isinstance(point[k], bool)
                            and math.isfinite(point[k]) for k in ("x", "y"))):
                return None
            metrics.extend((point["x"], point["y"]))
        return metrics if all(math.isfinite(v) for v in metrics) else None

    def native_geometry(page):
        contexts = command("GET", "/contexts")
        current = command("GET", "/context")
        if current != "NATIVE_APP" or web_context not in contexts:
            raise RuntimeError("Native/web contexts not confirmed before gesture")
        window = command("GET", "/window/rect")
        snapshot = {"contexts": sorted(contexts), "context": current, "window": window}
        result.setdefault("geometryChecks", []).append(snapshot)
        try:
            raw_source = command("GET", "/source", timeout=8)
            root = ET.fromstring(raw_source)
        except (Exception, KeyboardInterrupt) as error:
            snapshot["sourceError"] = sanitize(str(error))
            raise
        alt = page.get("cardImageAlt")
        dom = page.get("cardImageRect")
        if not isinstance(alt, str) or not alt.strip() or not isinstance(dom, dict):
            raise RuntimeError("DOM image identity/rectangle missing")
        matches = [node for node in root.iter() if node.tag == "XCUIElementTypeImage"
                   and (node.get("name") == alt or node.get("label") == alt)
                   and node.get("visible", "").lower() == "true"]
        snapshot["imageCandidates"] = [dict(node.attrib) for node in matches]
        if len(matches) != 1:
            raise RuntimeError("Native image correspondence is ambiguous or missing")
        node = matches[0]
        if any(node.get(k) not in (None, "", alt) for k in ("name", "label")):
            raise RuntimeError("Native image name/label contradict DOM alt")
        rect = {k: float(node.attrib[k]) for k in ("x", "y", "width", "height")}
        for box in (dom, rect, window):
            if (not all(isinstance(box.get(k), (int, float)) and not isinstance(box[k], bool)
                        and math.isfinite(box[k]) for k in ("x", "y", "width", "height"))
                    or box["width"] <= 0 or box["height"] <= 0):
                raise RuntimeError("Invalid image/window rectangle")
        sx, sy = rect["width"] / dom["width"], rect["height"] / dom["height"]
        mapping = {"sx": sx, "sy": sy, "ox": rect["x"] - sx * dom["x"],
                   "oy": rect["y"] - sy * dom["y"]}
        if not all(math.isfinite(v) for v in mapping.values()) or sx <= 0 or sy <= 0:
            raise RuntimeError("Invalid image calibration")
        calibration = {"alt": alt, "domRect": dom, "nativeRect": rect, **mapping,
                       "webPoints": page["points"], "touchMappingValidated": False}
        snapshot["calibration"] = calibration
        return snapshot, calibration

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(sanitize(result), ensure_ascii=False) + "\n")
        output_reserved = True
        result["atlasPreflight"] = []
        for url in dict.fromkeys((args.url, target)):
            # Never send BrowserStack authentication to ATLAS.
            req = urllib.request.Request(url, headers={"Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=8) as response:
                status = response.status
                result["atlasPreflight"].append({"url": url, "resolvedUrl": response.geturl(), "status": status})
                if not 200 <= status < 300:
                    raise RuntimeError("ATLAS preflight returned a non-success HTTP status")
                if url == target:
                    html = response.read(262144)
                    if b'id="root"' not in html and b"id='root'" not in html:
                        raise RuntimeError("ATLAS probe route did not return the expected frontend HTML")
        stage = "catalog"
        rows = request("GET", CATALOG)
        matches = [r for r in rows if r.get("device") == args.device and r.get("os_version") == args.ios
                   and r.get("browser") in ("iphone", "safari") and r.get("real_mobile") is True]
        result["catalogMatch"] = matches
        if not matches:
            raise RuntimeError("Requested control absent from public Automate catalog; no session created")
        # Never retry this POST: a timeout can leave an unknown session on the provider.
        stage = "session creation"
        created = request("POST", HUB + "/session", {"capabilities": {"alwaysMatch": caps}}, timeout=60)
        value = created.get("value") or {}
        sid = value.get("sessionId") or created.get("sessionId")
        result["sessionId"] = sid
        returned = value.get("capabilities", value)
        result["returnedCapabilities"] = sanitize(returned)
        if not sid:
            raise RuntimeError("Session response omitted sessionId; cannot address cleanup")
        stage = "capabilities"
        options = returned.get("bstack:options", {})
        fields = {
            "device": [returned.get(k) for k in ("deviceName", "appium:deviceName", "device", "deviceModel")] + [options.get("deviceName")],
            "ios": [returned.get(k) for k in ("platformVersion", "appium:platformVersion", "os_version", "osVersion")] + [options.get("osVersion")],
            "browser": [returned.get("browserName")],
            "platform": [returned.get("platformName"), returned.get("platform")],
            "automation": [returned.get("appium:automationName"), returned.get("automationName")],
        }
        checks = {}
        for field, values in fields.items():
            values = [str(v).strip() for v in values if v not in (None, "")]
            valid = {
                "device": lambda v: v.lower() == args.device.lower() or
                    (args.device.lower() == DEVICE.lower() and v.lower() == "iphone14,3"),
                "ios": lambda v: v == args.ios or v.startswith(args.ios + "."),
                "browser": lambda v: v.lower() in ("safari", "iphone", "mobile safari"),
                "platform": lambda v: v.lower() == "ios",
                "automation": lambda v: v.lower() == "xcuitest",
            }[field]
            checks[field] = {"values": values, "status": "not reported" if not values else
                             "confirmed" if all(valid(v) for v in values) else "contradiction"}
        if (str(returned.get("platformName", "")).lower() == "ios" and
                str(returned.get("deviceName", "")).lower() == args.device.lower() and
                str(returned.get("platform", "")).lower() == "mac" and
                all(checks[k]["status"] == "confirmed" for k in ("device", "browser", "automation"))):
            checks["platform"]["status"] = "confirmed"
            checks["platform"]["acceptedRepresentation"] = f"platform=MAC alongside confirmed iOS/{args.device}/Safari/XCUITest"
        if checks["ios"]["status"] == "not reported":
            checks["ios"]["status"] = "unconfirmed"
        result["requestedOsVersion"] = args.ios
        result["returnedOsVersion"] = checks["ios"]["values"] or None
        result["osVersionStatus"] = checks["ios"]["status"]
        result["capabilityChecks"] = checks
        if any(c["status"] == "contradiction" for c in checks.values()):
            raise RuntimeError("Returned capabilities contradict the requested control")
        if any(checks[k]["status"] != "confirmed" for k in ("device", "platform", "browser", "automation")):
            raise RuntimeError("Returned capabilities do not report enough information to confirm device/iOS platform/Safari/XCUITest")
        stage = "web readiness"
        result["availableContexts"] = command("GET", "/contexts")
        current = command("GET", "/context")
        web_context = current if current != "NATIVE_APP" else next(
            (c for c in result["availableContexts"] if c.startswith("WEBVIEW")), None)
        if not web_context:
            raise RuntimeError("No Safari web context available")
        context(web_context)
        result["webReadinessSubstep"] = "navigate"
        command("POST", "/url", {"url": target})
        sampling_started = time.monotonic()
        deadline = sampling_started + 15
        stability_started = None
        page = None
        result["readiness"] = {"sampleCount": 0, "resourcesReadyAtMs": None, "lastSample": None}
        stability_window = []
        exact_fields = ("mode", "cardId", "cardImageAlt", "width", "height", "visualViewport")
        while time.monotonic() < deadline:
            result["webReadinessSubstep"] = "ready.executeSync"
            before_ms = (time.monotonic() - sampling_started) * 1000
            sample = script(READY)
            sampled_at = time.monotonic()
            after_ms = (sampled_at - sampling_started) * 1000
            diagnostic = {
                "beforeMs": before_ms, "afterMs": after_ms,
                "flowResources": sample.get("flowResources") if sample is not None else None,
                "ready": {k: sample.get(k) for k in (
                    "cardRect", "cardImageRect", "points", "width", "height",
                    "visualViewport", "mode", "cardId", "cardImageAlt")} if sample is not None else None,
            }
            result["readiness"]["sampleCount"] += 1
            result["readiness"]["lastSample"] = diagnostic
            if sampled_at >= deadline:
                break
            if (stability_started is None and sample is not None and
                    sample.get("flowResources", {}).get("ready") is True):
                stability_started = sampled_at
                deadline = stability_started + 15
                result["readiness"]["resourcesReadyAtMs"] = after_ms
            diagnostic["phase"] = "flow resources" if stability_started is None else "geometry stability"
            metrics = geometry_metrics(sample)
            if metrics is None:
                stability_window = []
                diagnostic["windowReset"] = "READY null or invalid geometry"
            elif sample.get("flowResources", {}).get("ready") is not True:
                stability_window = []
                diagnostic["windowReset"] = "Flow resources not ready"
            else:
                entry = {"sample": sample, "metrics": metrics, "afterMs": after_ms}
                stability_window.append(entry)
                limits = (1, 1, 7, 7, 1, 1, 7, 7, 1, 1, 1, 1)
                if (any(item["sample"][k] != sample[k] for item in stability_window for k in exact_fields) or
                        any(max(item["metrics"][i] for item in stability_window) -
                            min(item["metrics"][i] for item in stability_window) > limit
                            for i, limit in enumerate(limits))):
                    stability_window = [entry]
                    diagnostic["windowReset"] = "Identity/viewport changed or geometry range exceeded"
                diagnostic["windowCount"] = len(stability_window)
                diagnostic["windowSpanMs"] = after_ms - stability_window[0]["afterMs"]
                if (len(stability_window) >= 4 and diagnostic["windowSpanMs"] >= 2000 and
                        time.monotonic() < deadline):
                    page = sample
                    break
            if "windowReset" in diagnostic:
                result["readiness"]["lastReset"] = {"atMs": after_ms, "reason": diagnostic["windowReset"]}
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(.2, remaining))
        if page is None:
            if stability_started is None:
                raise RuntimeError("Flow resources/readiness did not resolve within 15 s")
            raise RuntimeError("TapGrid geometry did not stabilize within 15 s after flow resources became ready")
        result["initial"] = page
        result["modeBefore"] = page["mode"]
        result["webReadinessSubstep"] = "complete"
        stage = "geometry"
        context("NATIVE_APP")
        geometry, mapping = native_geometry(page)
        points = [{"x": round(mapping["ox"] + mapping["sx"] * p["x"]),
                   "y": round(mapping["oy"] + mapping["sy"] * p["y"])} for p in page["points"]]
        result["calibration"] = {**mapping, "nativePoints": points}
        context(web_context)
        fresh = script(READY)
        fields = ("points", "width", "height", "mode", "cardId", "cardRect", "cardImageRect", "cardImageAlt", "visualViewport")
        # The first measurement is already retained in initial.
        result["geometryRevalidation"] = {
            "second": {k: fresh.get(k) for k in (*fields, "flowResources")} if fresh is not None else None}
        first_metrics = geometry_metrics(page)
        second_metrics = geometry_metrics(fresh)
        if (first_metrics is None or second_metrics is None or
                fresh.get("flowResources", {}).get("ready") is not True or
                any(fresh[k] != page[k] for k in exact_fields) or
                any(abs(a - b) > limit for a, b, limit in zip(first_metrics, second_metrics, limits))):
            raise RuntimeError("TapGrid geometry changed during preparation; gesture NOT sent")
        script("window.ATLAS_TAP_TIMING_LAB.reset(); return true;")
        context("NATIVE_APP")
        final_geometry, final_mapping = native_geometry(fresh)
        if (any(final_geometry[k] != geometry[k] for k in ("contexts", "context", "window"))
                or final_mapping["alt"] != mapping["alt"]):
            raise RuntimeError("Native context/window/image identity changed; gesture NOT sent")
        # Use the latest validated image pair; shake may change scale/offset without moving its center.
        points = [{"x": final_mapping["ox"] + final_mapping["sx"] * p["x"],
                   "y": final_mapping["oy"] + final_mapping["sy"] * p["y"]} for p in fresh["points"]]
        if not all(math.isfinite(p[k]) for p in points for k in ("x", "y")):
            raise RuntimeError("Fresh native points are not finite; gesture NOT sent")
        points = [{"x": round(p["x"]), "y": round(p["y"])} for p in points]
        result["finalCalibration"] = {**final_mapping, "nativePoints": points}
        for box in (final_mapping["nativeRect"], final_geometry["window"]):
            if not all(box["x"] + 12 < p["x"] < box["x"] + box["width"] - 12 and
                       box["y"] + 12 < p["y"] < box["y"] + box["height"] - 12 for p in points):
                raise RuntimeError("Native points are outside the safe image/window interior")
        # The rounded native points must project back into the verified safe card interior.
        card = fresh["cardRect"]
        projected = [{"x": (p["x"] - final_mapping["ox"]) / final_mapping["sx"],
                      "y": (p["y"] - final_mapping["oy"]) / final_mapping["sy"]} for p in points]
        if not all(card["x"] + 12 < p["x"] < card["x"] + card["width"] - 12 and
                   card["y"] + 12 < p["y"] < card["y"] + card["height"] - 12 and
                   12 < p["x"] < fresh["width"] - 12 and 12 < p["y"] < fresh["height"] - 12
                   for p in projected):
            raise RuntimeError("Projected native points are outside the verified TapGrid safe area")
        result["projectedWebPoints"] = projected
        result["nativePoints"] = points
        result["actions"] = gesture(points)
        stage = "gesture delivery"
        command("POST", "/actions", result["actions"])
        result["gestureSent"] = True
        result["actionsCompleted"] = True
        stage = "evidence export"
        context(web_context)
        time.sleep(.2)
        result["final"] = script(EXPORT)
        result["modeAfter"] = result["final"].get("mode")
        lab = result["final"].get("lab")
        if not isinstance(lab, dict) or not isinstance(lab.get("trace"), list):
            raise RuntimeError("Timing Lab export missing; recognizer cannot be evaluated")
        trace = lab["trace"]
        result["inputValid"], evidence = assess_input(trace)
        result["inputEvidence"] = evidence
        # Confirm received contacts landed where the native mapping predicted.
        for episode in evidence["episodes"]:
            chord = episode["chord"]
            if chord:
                received = sorted(chord["touches"], key=lambda t: t.get("clientX", -1))
                if any(not isinstance(t.get(k), (int, float)) for t in received for k in ("clientX", "clientY")) or any(
                        abs(t["clientX"] - p["x"]) > 8 or abs(t["clientY"] - p["y"]) > 8
                        for t, p in zip(received, sorted(projected, key=lambda p: p["x"]))):
                    evidence["problems"].append("Received touch coordinates do not confirm native/web mapping")
                    result["inputValid"] = False
        decisions = [e for e in trace if e.get("type") == "PRODUCTIVE_DECISION"]
        result["productiveDecisions"] = decisions
        if not result["inputValid"]:
            result["reason"] = "Input not valid for evaluating the recognizer: " + "; ".join(evidence["problems"])
        elif result["modeAfter"] not in ("focus", "gallery"):
            result["reason"] = "Final TapGrid mode is unavailable"
        else:
            second = evidence["episodes"][1]
            second_raw_sequences = {e.get("sequence") for e in evidence["rawEvents"]
                                    if second["start"]["at"] <= e["at"] <= second["release"]["at"]
                                    and e.get("touchesLength") == 2 and e.get("type") == "TOUCHSTART"}
            second_decisions = [e for e in decisions if e.get("rawEventSequence") in second_raw_sequences]
            evidence["secondChordDecisions"] = second_decisions
            if not second_decisions or any(not isinstance(e.get("recognized"), bool) for e in second_decisions):
                result["reason"] = "Valid input but missing productive decision evidence for the second chord"
            elif any(not isinstance(e.get("deltaMs"), (int, float)) or not 0 <= e["deltaMs"] < 350 for e in second_decisions):
                result["reason"] = "Recognizer clock interval does not confirm an in-window trial"
            else:
                result["recognizerEvaluated"] = True
                result["toggleRecognized"] = any(e["recognized"] for e in second_decisions)
                expected = "gallery" if page["mode"] == "focus" else "focus"
                passed = result["toggleRecognized"] and result["modeAfter"] == expected
                result["result"] = "PASS" if passed else "RECOGNIZER_FAIL"
                result["reason"] = ("Two complete, in-window native chords confirmed; expected toggle observed" if passed else
                                    "Valid complete in-window input confirmed, but recognition/mode toggle was not as expected")
    except (Exception, KeyboardInterrupt) as error:
        result["result"] = "INCONCLUSIVE"
        result["reason"] = f"{stage} failure: {sanitize(str(error))}"
        result["recognizerEvaluated"] = False
        result["errors"].append({"stage": stage, "type": type(error).__name__, "message": sanitize(str(error))})
    finally:
        if sid:
            try:
                # No optional exports/context switches before cleanup on a failed trial.
                command("DELETE", "", timeout=8)
                result["sessionDeleted"] = True
            except (Exception, KeyboardInterrupt) as error:
                result["result"] = "INCONCLUSIVE"
                result["reason"] = "Session deletion could not be confirmed"
                result["errors"].append({"stage": "session deletion", "message": sanitize(str(error))})
        result["finishedAt"] = datetime.now(timezone.utc).isoformat()
        if output_reserved:
            try:
                output.write_text(json.dumps(sanitize(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except Exception as error:
                result["result"] = "INCONCLUSIVE"
                result["reason"] = "Diagnostic JSON could not be persisted"
                result["errors"].append({"stage": "persistence", "message": sanitize(str(error))})
        emit({"diagnostic": str(output), **{k: result[k] for k in (
            "result", "reason", "inputValid", "gestureSent", "recognizerEvaluated",
            "toggleRecognized", "modeBefore", "modeAfter", "sessionDeleted", "errors")}})
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
