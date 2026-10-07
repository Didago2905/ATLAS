import { useParams, useNavigate } from "react-router-dom";
import useCatalogSession from "../catalog/useCatalogSession";
import BeerCard from "../components/BeerCard";
import { useState, useEffect, useRef, useLayoutEffect } from "react";
import { useLocation } from "react-router-dom";
import useTutorialImage from "../tutorial/useTutorialImage";
import "./Home.css";

const tritonIntro = "/static/icons/tutorial/triton-beerdetail-intro.webp";
const tritonDetails = "/static/icons/tutorial/triton-beerdetail-details.webp";

export default function BeerDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const location = useLocation();
    const [tutorialCompletedKey, setTutorialCompletedKey] = useState(null);
    const [tutorialClosingKey, setTutorialClosingKey] = useState(null);
    const [tutorialPulseKey, setTutorialPulseKey] = useState(null);
    const [tutorialDialoguePhase, setTutorialDialoguePhase] = useState(() =>
        location.state?.tutorialStep === "beerdetail-vertical-to-art" ? "vertical-to-art"
            : location.state?.tutorialStep === "beerdetail-art-arrived" ? "horizontal-art"
                : location.state?.tutorialStep === "beerdetail-return-to-info" ? "vertical-to-info"
                    : location.state?.tutorialStep === "beerdetail-details" ? "details" : "intro"
    );
    const tutorialVerticalDialogue = ["vertical-crossfade", "vertical-to-art"].includes(tutorialDialoguePhase);
    const tutorialArtDialogue = ["art-crossfade", "horizontal-art", "return-waiting"].includes(tutorialDialoguePhase);
    const tutorialReturnDialogue = ["return-crossfade", "vertical-to-info", "info-arrived"].includes(tutorialDialoguePhase);
    const tutorialDetailsDialogue = ["details-crossfade", "details"].includes(tutorialDialoguePhase);
    const tutorialMirrored = tutorialVerticalDialogue || tutorialArtDialogue || tutorialReturnDialogue;
    const tutorialExploring = !["intro", "crossfade"].includes(tutorialDialoguePhase)
        || ["beerdetail-horizontal", "beerdetail-vertical-to-art", "beerdetail-art-arrived", "beerdetail-return-to-info"].includes(location.state?.tutorialStep);
    const tutorialActive = (location.state?.tutorialStep === "beerdetail-intro"
        || ["beerdetail-horizontal", "beerdetail-vertical-to-art", "beerdetail-art-arrived", "beerdetail-return-to-info", "beerdetail-details"].includes(location.state?.tutorialStep))
        && tutorialCompletedKey !== location.key;
    const tutorialClosing = tutorialClosingKey === location.key;
    const tritonReady = useTutorialImage(tritonIntro, tutorialActive);
    const tritonDetailsReady = useTutorialImage(tritonDetails, tutorialActive
        && (["vertical-to-info", "info-arrived"].includes(tutorialDialoguePhase) || tutorialDetailsDialogue));

    const beersFromState = location.state?.beers;
    const indexFromState = location.state?.currentIndex;

    const [stableBeers, setStableBeers] = useState(null);

    const { beers: fallbackBeers } = useCatalogSession();
    const beers = stableBeers || fallbackBeers;

    const beer = beers.find((b) => String(b.id) === id);

    const index =
        indexFromState !== undefined
            ? indexFromState
            : beers.findIndex((b) => String(b.id) === id);

    const prevBeer = beers[index - 1];
    const nextBeer = beers[index + 1];

    const [visible, setVisible] = useState(false);
    const [direction, setDirection] = useState(null);
    const [animating, setAnimating] = useState(false);

    const [viewMode, setViewMode] = useState("info");
    const [artVisible, setArtVisible] = useState(false);
    const [layoutSnapshot, setLayoutSnapshot] = useState(null);
    const [stageBootstrapped, setStageBootstrapped] = useState(false);
    const [tutorialHorizontalComplete, setTutorialHorizontalComplete] = useState(false);
    const [tutorialHintAnimation, setTutorialHintAnimation] = useState(null);
    const tutorialHintUsedRef = useRef(false);
    const tutorialVerticalHintUsedRef = useRef(false);
    const tutorialVerticalContactsRef = useRef({ touches: 0, pointers: new Set() });
    const tutorialArtHintUsedRef = useRef(false);
    const tutorialReturnHintUsedRef = useRef(false);
    const [tutorialArtHorizontalComplete, setTutorialArtHorizontalComplete] = useState(false);
    const [tutorialArtSettledId, setTutorialArtSettledId] = useState(null);
    const tutorialVerticalIntentRef = useRef(null);
    const [tutorialVerticalComplete, setTutorialVerticalComplete] = useState(false);
    const tutorialVerticalActive = tutorialActive && !tutorialVerticalComplete
        && tutorialDialoguePhase === "vertical-to-art";
    const tutorialReturnActive = tutorialActive && tutorialDialoguePhase === "vertical-to-info";
    const tutorialHorizontalActive = !tutorialHorizontalComplete && (
        (location.state?.tutorialStep === "beerdetail-intro" && tutorialDialoguePhase === "horizontal")
        || location.state?.tutorialStep === "beerdetail-horizontal"
    );
    const tutorialArtHorizontalActive = tutorialActive && !tutorialArtHorizontalComplete
        && tutorialDialoguePhase === "horizontal-art" && viewMode === "art" && artVisible
        && tutorialArtSettledId === id;

    useEffect(() => {
        const accepted = location.state?.tutorialHorizontalSwipe;
        if (!tutorialArtHorizontalComplete && location.state?.tutorialStep === "beerdetail-art-arrived"
            && accepted?.phase === "horizontal-art" && accepted.originMode === "art"
            && (accepted.direction === "prev" || accepted.direction === "next")
            && String(accepted.destinationId) === id && String(accepted.fromId) !== id
            && beer && String(beer.id) === id && viewMode === "art") {
            setTutorialArtHorizontalComplete(true);
            setTutorialHintAnimation(null);
            setTutorialDialoguePhase("return-waiting");
        }
    }, [id, beer, location.state, viewMode, tutorialArtHorizontalComplete]);

    useEffect(() => {
        const accepted = location.state?.tutorialHorizontalSwipe;
        if (!tutorialHorizontalComplete && location.state?.tutorialStep === "beerdetail-horizontal"
            && accepted && accepted.originMode === "info"
            && (accepted.direction === "prev" || accepted.direction === "next")
            && String(accepted.destinationId) === id && String(accepted.fromId) !== id
            && beer && String(beer.id) === id) {
            setTutorialHorizontalComplete(true);
            setTutorialDialoguePhase("vertical-waiting");
        }
    }, [id, beer, location.state, tutorialHorizontalComplete]);

    useEffect(() => {
        if (tutorialDialoguePhase !== "vertical-waiting" && !tutorialVerticalDialogue
            && tutorialDialoguePhase !== "art-waiting" && !tutorialArtDialogue
            && tutorialDialoguePhase !== "return-waiting" && !tutorialReturnDialogue) return;
        const contacts = tutorialVerticalContactsRef.current;
        const waitingForDetails = tutorialDialoguePhase === "info-arrived";
        const waitingForReturn = tutorialDialoguePhase === "return-waiting";
        const waitingForArt = tutorialDialoguePhase === "art-waiting" || waitingForReturn;
        let timer;
        const scheduleEntry = () => {
            window.clearTimeout(timer);
            if ((waitingForDetails ? viewMode !== "info" || !tritonDetailsReady
                : waitingForArt ? viewMode !== "art" : tutorialDialoguePhase !== "vertical-waiting" || viewMode !== "info")
                || (waitingForArt && !artVisible)
                || contacts.touches || contacts.pointers.size) return;
            timer = window.setTimeout(() => {
                if (document.querySelector('[role="dialog"]')) {
                    scheduleEntry();
                    return;
                }
                setTutorialDialoguePhase(waitingForDetails ? "details-crossfade" : waitingForReturn ? "return-crossfade" : waitingForArt ? "art-crossfade" : "vertical-crossfade");
            }, 1200);
        };
        const startContact = (event) => {
            if (event.type === "touchstart") contacts.touches = event.touches.length;
            else contacts.pointers.add(event.pointerId);
            window.clearTimeout(timer);
        };
        const endContact = (event) => {
            if (event.type.startsWith("touch")) contacts.touches = event.touches.length;
            else contacts.pointers.delete(event.pointerId);
            scheduleEntry();
        };
        scheduleEntry();
        const startEvents = ["touchstart", "pointerdown"];
        const endEvents = ["touchend", "touchcancel", "pointerup", "pointercancel"];
        startEvents.forEach(type => window.addEventListener(type, startContact, { passive: true, capture: true }));
        endEvents.forEach(type => window.addEventListener(type, endContact, { passive: true, capture: true }));
        return () => {
            window.clearTimeout(timer);
            startEvents.forEach(type => window.removeEventListener(type, startContact, true));
            endEvents.forEach(type => window.removeEventListener(type, endContact, true));
        };
    }, [tutorialDialoguePhase, tutorialVerticalDialogue, tutorialArtDialogue, tutorialReturnDialogue, viewMode, id, artVisible, tritonDetailsReady]);

    useEffect(() => {
        if ((!tutorialHorizontalActive && !tutorialVerticalActive && !tutorialArtHorizontalActive && !tutorialReturnActive)
            || (tutorialArtHorizontalActive || tutorialReturnActive ? viewMode !== "art" : viewMode !== "info")
            || (!tutorialVerticalActive && !tutorialReturnActive && !prevBeer && !nextBeer)
            || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        let timer;
        let touches = tutorialVerticalActive || tutorialArtHorizontalActive || tutorialReturnActive ? tutorialVerticalContactsRef.current.touches : 0;
        const pointers = new Set(tutorialVerticalActive || tutorialArtHorizontalActive || tutorialReturnActive ? tutorialVerticalContactsRef.current.pointers : []);
        const scheduleHint = (delay = 2000) => {
            window.clearTimeout(timer);
            if (touches || pointers.size) return;
            timer = window.setTimeout(() => {
                if (document.querySelector('[role="dialog"]')) {
                    scheduleHint();
                    return;
                }
                setTutorialHintAnimation(tutorialReturnActive ? "down" : tutorialVerticalActive ? "up" : prevBeer && nextBeer ? "both" : nextBeer ? "next" : "prev");
            }, delay);
        };
        const cancelHint = (event) => {
            if (event.type === "touchstart") touches = event.touches.length;
            else pointers.add(event.pointerId);
            window.clearTimeout(timer);
            setTutorialHintAnimation(null);
        };
        const endContact = (event) => {
            if (event.type.startsWith("touch")) touches = event.touches.length;
            else pointers.delete(event.pointerId);
            scheduleHint();
        };
        const finishHint = (event) => {
            if (event.target === shellRef.current && event.animationName.startsWith("beerdetail-hint-")) {
                scheduleHint();
            }
        };
        const usedRef = tutorialReturnActive ? tutorialReturnHintUsedRef : tutorialVerticalActive ? tutorialVerticalHintUsedRef
            : tutorialArtHorizontalActive ? tutorialArtHintUsedRef : tutorialHintUsedRef;
        scheduleHint(usedRef.current ? 2000 : tutorialVerticalActive || tutorialArtHorizontalActive || tutorialReturnActive ? 1200 : 500);
        usedRef.current = true;
        const shell = shellRef.current;
        shell?.addEventListener("animationend", finishHint);
        window.addEventListener("touchstart", cancelHint, { passive: true, capture: true });
        window.addEventListener("pointerdown", cancelHint, { passive: true, capture: true });
        const endEvents = ["touchend", "touchcancel", "pointerup", "pointercancel"];
        endEvents.forEach(type => window.addEventListener(type, endContact, { passive: true, capture: true }));
        return () => {
            window.clearTimeout(timer);
            shell?.removeEventListener("animationend", finishHint);
            window.removeEventListener("touchstart", cancelHint, true);
            window.removeEventListener("pointerdown", cancelHint, true);
            endEvents.forEach(type => window.removeEventListener(type, endContact, true));
            setTutorialHintAnimation(null);
        };
    }, [tutorialHorizontalActive, tutorialVerticalActive, tutorialArtHorizontalActive, tutorialReturnActive, viewMode, id, prevBeer?.id, nextBeer?.id]);

    const horizontalTutorialState = (acceptedDirection, destination) => tutorialDetailsDialogue || tutorialDialoguePhase === "info-arrived" ? {
        tutorialStep: "beerdetail-details",
    } : tutorialReturnDialogue || tutorialDialoguePhase === "return-waiting" ? {
        tutorialStep: "beerdetail-return-to-info",
    } : tutorialVerticalDialogue || tutorialDialoguePhase === "vertical-waiting" ? {
        tutorialStep: "beerdetail-vertical-to-art",
    } : tutorialActive && !tutorialArtHorizontalComplete
        && tutorialDialoguePhase === "horizontal-art" && viewMode === "art" ? {
        tutorialStep: "beerdetail-art-arrived",
        tutorialHorizontalSwipe: {
            phase: "horizontal-art", originMode: "art", direction: acceptedDirection,
            fromId: id, destinationId: destination.id,
        },
    } : tutorialArtDialogue || tutorialDialoguePhase === "art-waiting" ? {
        tutorialStep: "beerdetail-art-arrived",
    } : tutorialHorizontalActive && viewMode === "info" ? {
        tutorialStep: "beerdetail-horizontal",
        tutorialHorizontalSwipe: { phase: "horizontal-info", direction: acceptedDirection, fromId: id, destinationId: destination.id, originMode: "info" },
    } : tutorialHorizontalActive ? {
        tutorialStep: "beerdetail-horizontal",
    } : {};

    useEffect(() => {
        if (!tutorialActive || !tritonReady || !visible || !beer || tutorialClosing
            || tutorialExploring || tutorialDialoguePhase === "crossfade") return;
        const timer = window.setTimeout(() => setTutorialPulseKey(location.key), 2700);
        return () => window.clearTimeout(timer);
    }, [tutorialActive, tritonReady, visible, beer, tutorialClosing, location.key, tutorialExploring, tutorialDialoguePhase]);

    useEffect(() => {
        const nextPhase = { crossfade: "horizontal", "vertical-crossfade": "vertical-to-art", "art-crossfade": "horizontal-art", "return-crossfade": "vertical-to-info", "details-crossfade": "details" }[tutorialDialoguePhase];
        if (!nextPhase) return;
        const timer = window.setTimeout(() => setTutorialDialoguePhase(nextPhase), 180);
        return () => window.clearTimeout(timer);
    }, [tutorialDialoguePhase]);

    useEffect(() => {
        if (!tutorialClosing) return;
        const timer = window.setTimeout(() => setTutorialCompletedKey(location.key), 300);
        return () => window.clearTimeout(timer);
    }, [tutorialClosing, location.key]);

    const startX = useRef(0);
    const startY = useRef(0);
    const activeTouchId = useRef(null);
    const axisLock = useRef(null);
    const multiTouchActive = useRef(false);
    const outerRef = useRef(null);
    const wrapperRef = useRef(null);
    const shellRef = useRef(null);
    const stageRef = useRef(null);
    const infoLayerRef = useRef(null);
    const beerCardRef = useRef(null);
    const artOverlayRef = useRef(null);
    useEffect(() => {
        setTutorialArtSettledId(null);
        if (!tutorialArtDialogue || viewMode !== "art" || !artVisible) return;
        let cancelled = false;
        const frame = requestAnimationFrame(() => {
            const overlay = artOverlayRef.current;
            if (!overlay) return;
            const transitions = overlay.getAnimations?.() || [];
            Promise.allSettled(transitions.map(animation => animation.finished)).then(() => {
                if (!cancelled) setTutorialArtSettledId(id);
            });
        });
        return () => {
            cancelled = true;
            cancelAnimationFrame(frame);
        };
    }, [id, viewMode, artVisible, tutorialArtDialogue]);
    useEffect(() => {
        const intent = tutorialVerticalIntentRef.current;
        if (!intent) return;
        if (String(intent.beerId) !== id) {
            tutorialVerticalIntentRef.current = null;
            return;
        }
        if (intent.phase === "vertical-to-art" && intent.originMode === "info"
            && intent.destinationMode === "art" && viewMode === "art" && artVisible
            && artOverlayRef.current && tutorialVerticalActive) {
            tutorialVerticalIntentRef.current = null;
            setTutorialVerticalComplete(true);
            setTutorialDialoguePhase("art-waiting");
        }
        if (intent.phase === "vertical-to-info" && intent.originMode === "art"
            && intent.destinationMode === "info" && viewMode === "info" && !artVisible
            && !artOverlayRef.current && tutorialReturnActive) {
            tutorialVerticalIntentRef.current = null;
            setTutorialHintAnimation(null);
            setTutorialDialoguePhase("info-arrived");
        }
    }, [id, viewMode, artVisible, tutorialVerticalActive, tutorialReturnActive]);
    const stageLifecycleStartRef = useRef(performance.now());

    const isMobile = window.innerWidth < 768;
    const spatialDebug = window.__ATLAS_SPATIAL_PROBE__ === true;
    const viewportProbe = window.__ATLAS_VIEWPORT_PROBE__ === true;

    const debugOutline = (color) =>
        spatialDebug
            ? {
                outline: `2px solid ${color}`,
                outlineOffset: "-2px",
            }
            : {};

    const logRootGeometry = (phase, extra = {}) => {
        if (!viewportProbe) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const readStyle = (node) => {
            if (!node) return null;

            const style = window.getComputedStyle(node);

            return {
                height: style.height,
                minHeight: style.minHeight,
                overflow: style.overflow,
                position: style.position,
                transform: style.transform,
            };
        };

        const describeNode = (node) => {
            if (!node) return null;

            return {
                tagName: node.tagName,
                id: node.id || null,
                className:
                    typeof node.className === "string"
                        ? node.className
                        : null,
            };
        };

        const root = document.getElementById("root");
        const outer = outerRef.current;
        const centerX = Math.round(window.innerWidth / 2);

        console.log("[root-geometry]", {
            phase,
            beerId: id,
            viewMode,
            timestamp: Math.round(performance.now()),
            scroll: {
                scrollX: window.scrollX,
                scrollY: window.scrollY,
                pageYOffset: window.pageYOffset,
                documentScrollTop: document.documentElement.scrollTop,
                bodyScrollTop: document.body.scrollTop,
            },
            viewport: {
                innerHeight: window.innerHeight,
                visualViewportHeight: window.visualViewport?.height,
                visualViewportOffsetTop: window.visualViewport?.offsetTop,
                visualViewportPageTop: window.visualViewport?.pageTop,
            },
            rects: {
                html: toRect(document.documentElement),
                body: toRect(document.body),
                root: toRect(root),
                outer: toRect(outer),
            },
            computed: {
                html: readStyle(document.documentElement),
                body: readStyle(document.body),
                root: readStyle(root),
                outer: readStyle(outer),
            },
            outer: {
                offsetTop: outer?.offsetTop ?? null,
                offsetParent: describeNode(outer?.offsetParent),
            },
            elementFromPoint: {
                top: describeNode(document.elementFromPoint(centerX, 0)),
                y56: describeNode(document.elementFromPoint(centerX, 56)),
            },
            ...extra,
        });
    };

    const readBootstrapMetrics = () => {
        const viewportHeight =
            window.visualViewport?.height || window.innerHeight;
        const outerRect = outerRef.current?.getBoundingClientRect();
        const cardRect = beerCardRef.current?.getBoundingClientRect();

        return {
            scrollY: window.scrollY,
            pageYOffset: window.pageYOffset,
            documentScrollTop: document.documentElement.scrollTop,
            outerTop: outerRect ? Math.round(outerRect.top) : null,
            freeTop: cardRect ? Math.round(cardRect.top) : null,
            freeBottom: cardRect
                ? Math.round(viewportHeight - cardRect.bottom)
                : null,
            viewportPageTop: window.visualViewport?.pageTop,
        };
    };

    useLayoutEffect(() => {
        setStageBootstrapped(false);

        const before = readBootstrapMetrics();
        const shouldReset =
            before.scrollY > 0 ||
            before.pageYOffset > 0 ||
            before.documentScrollTop > 0;

        console.log("[immersive-bootstrap]", {
            phase: "before-reset",
            beerId: id,
            viewMode,
            resetNeeded: shouldReset,
            ...before,
        });

        if (shouldReset) {
            window.scrollTo(0, 0);
        }

        const frame = requestAnimationFrame(() => {
            const after = readBootstrapMetrics();

            console.log("[immersive-bootstrap]", {
                phase: "after-reset",
                beerId: id,
                viewMode,
                resetApplied: shouldReset,
                beforeScrollY: before.scrollY,
                afterScrollY: after.scrollY,
                beforeOuterTop: before.outerTop,
                afterOuterTop: after.outerTop,
                beforeFreeTop: before.freeTop,
                afterFreeTop: after.freeTop,
                beforeFreeBottom: before.freeBottom,
                afterFreeBottom: after.freeBottom,
                beforeViewportPageTop: before.viewportPageTop,
                afterViewportPageTop: after.viewportPageTop,
            });

            setStageBootstrapped(true);

            console.log("[immersive-bootstrap]", {
                phase: "ready",
                beerId: id,
                viewMode,
                ...after,
            });
        });

        return () => cancelAnimationFrame(frame);
    }, [id]);

    useEffect(() => {
        const html = document.documentElement;
        const body = document.body;

        html.classList.add("no-scroll");
        body.classList.add("no-scroll");

        return () => {
            html.classList.remove("no-scroll");
            body.classList.remove("no-scroll");
        };
    }, []);

    useEffect(() => {
        if (!viewportProbe || !stageBootstrapped) return;

        const readResetMetrics = () => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const outerRect = outerRef.current?.getBoundingClientRect();
            const stageRect = stageRef.current?.getBoundingClientRect();
            const cardRect = beerCardRef.current?.getBoundingClientRect();

            return {
                scrollY: window.scrollY,
                pageYOffset: window.pageYOffset,
                documentScrollTop: document.documentElement.scrollTop,
                outerTop: outerRect ? Math.round(outerRect.top) : null,
                stageTop: stageRect ? Math.round(stageRect.top) : null,
                freeTop: cardRect ? Math.round(cardRect.top) : null,
                freeBottom: cardRect
                    ? Math.round(viewportHeight - cardRect.bottom)
                    : null,
                viewportPageTop: window.visualViewport?.pageTop,
            };
        };

        const before = readResetMetrics();
        const shouldReset =
            before.scrollY > 0 ||
            before.pageYOffset > 0 ||
            before.documentScrollTop > 0;

        if (!shouldReset) {
            console.log("[root-scroll-reset]", {
                phase: "skipped",
                beerId: id,
                viewMode,
                timestamp: Math.round(performance.now()),
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                beforeScrollY: before.scrollY,
                beforePageYOffset: before.pageYOffset,
                beforeDocumentScrollTop: before.documentScrollTop,
                beforeOuterTop: before.outerTop,
                beforeFreeTop: before.freeTop,
                beforeStageTop: before.stageTop,
                beforeViewportPageTop: before.viewportPageTop,
            });
            return;
        }

        window.scrollTo(0, 0);

        const frame = requestAnimationFrame(() => {
            const after = readResetMetrics();

            console.log("[root-scroll-reset]", {
                phase: "after-scrollTo",
                beerId: id,
                viewMode,
                timestamp: Math.round(performance.now()),
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                beforeScrollY: before.scrollY,
                afterScrollY: after.scrollY,
                beforePageYOffset: before.pageYOffset,
                afterPageYOffset: after.pageYOffset,
                beforeDocumentScrollTop: before.documentScrollTop,
                afterDocumentScrollTop: after.documentScrollTop,
                beforeOuterTop: before.outerTop,
                afterOuterTop: after.outerTop,
                beforeFreeTop: before.freeTop,
                afterFreeTop: after.freeTop,
                beforeFreeBottom: before.freeBottom,
                afterFreeBottom: after.freeBottom,
                beforeStageTop: before.stageTop,
                afterStageTop: after.stageTop,
                beforeViewportPageTop: before.viewportPageTop,
                afterViewportPageTop: after.viewportPageTop,
            });

            logRootGeometry("root-scroll-reset.after");
        });

        return () => cancelAnimationFrame(frame);
    }, [id, viewportProbe, stageBootstrapped]);

    useEffect(() => {
        if (beersFromState && !stableBeers) {
            setStableBeers(beersFromState);
        }
    }, [beersFromState]);

    useEffect(() => {
        const backgroundUrl = beer?.beercard_background_url;
        if (!backgroundUrl) return;

        const img = new Image();

        img.src = backgroundUrl;

        if (img.decode) {
            img.decode().catch(() => {});
        }

        return () => {
            img.onload = null;
            img.onerror = null;
        };
    }, [beer?.beercard_background_url]);

    useEffect(() => {

        [prevBeer, nextBeer].forEach((candidate) => {

            const url = candidate?.beercard_background_url;

            if (!url) return;

            const img = new Image();

            img.src = url;

            if (img.decode) {
                img.decode().catch(() => {});
            }

        });

    }, [
        prevBeer?.beercard_background_url,
        nextBeer?.beercard_background_url
    ]);

    useEffect(() => {
        setVisible(true);
    }, []);

    useEffect(() => {
        setAnimating(false);
        setDirection(null);
    }, [id]);

    useEffect(() => {
        stageLifecycleStartRef.current = performance.now();
    }, [id]);

    useEffect(() => {
        const logViewport = (phase) => {
            console.log("[viewport]", {
                phase,
                innerHeight: window.innerHeight,
                visualViewportHeight: window.visualViewport?.height,
                documentClientHeight: document.documentElement.clientHeight,
            });
        };

        logViewport("mount");

        const handleResize = () => {
            logViewport("resize");
        };

        window.visualViewport?.addEventListener("resize", handleResize);

        return () => {
            window.visualViewport?.removeEventListener("resize", handleResize);
        };
    }, []);

    useEffect(() => {
        if (!stageBootstrapped) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const logLayout = (phase) => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRect = beerCardRef.current?.getBoundingClientRect();

            const snapshot = {
                phase,
                viewport: {
                    innerHeight: window.innerHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    documentClientHeight: document.documentElement.clientHeight,
                },
                outerRect: toRect(outerRef.current),
                wrapperRect: toRect(wrapperRef.current),
                shellRect: toRect(shellRef.current),
                stageRect: toRect(stageRef.current),
                cardRect: toRect(beerCardRef.current),
                artOverlayRect: toRect(artOverlayRef.current),
                freeTop: cardRect ? Math.round(cardRect.top) : null,
                freeBottom: cardRect
                    ? Math.round(viewportHeight - cardRect.bottom)
                    : null,
            };

            console.log("[layout]", snapshot);

            if (spatialDebug) {
                setLayoutSnapshot(snapshot);
            }
        };

        logLayout("mount");

        const frame = requestAnimationFrame(() => {
            logLayout("frame");
        });

        const handleResize = () => {
            logLayout("viewport-resize");
        };

        window.visualViewport?.addEventListener("resize", handleResize);

        return () => {
            cancelAnimationFrame(frame);
            window.visualViewport?.removeEventListener("resize", handleResize);
        };
    }, [id, viewMode, spatialDebug, stageBootstrapped]);

    useEffect(() => {
        console.log("[viewMode]", {
            beerId: id,
            viewMode,
        });
    }, [id, viewMode]);

    useEffect(() => {
        if (!viewportProbe || !stageBootstrapped) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const logViewportLifecycle = (phase, extra = {}) => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRectRaw = beerCardRef.current?.getBoundingClientRect();
            const rootStyle = window.getComputedStyle(document.documentElement);

            console.log("[viewport-probe]", {
                phase,
                beerId: id,
                viewMode,
                timestamp: Math.round(performance.now()),
                viewport: {
                    innerHeight: window.innerHeight,
                    documentClientHeight: document.documentElement.clientHeight,
                    bodyClientHeight: document.body.clientHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    visualViewportOffsetTop: window.visualViewport?.offsetTop,
                    visualViewportPageTop: window.visualViewport?.pageTop,
                    atlasVh: rootStyle.getPropertyValue("--atlas-vh").trim(),
                },
                rects: {
                    outer: toRect(outerRef.current),
                    wrapper: toRect(wrapperRef.current),
                    stage: toRect(stageRef.current),
                    card: toRect(beerCardRef.current),
                },
                freeSpace: {
                    top: cardRectRaw ? Math.round(cardRectRaw.top) : null,
                    bottom: cardRectRaw
                        ? Math.round(viewportHeight - cardRectRaw.bottom)
                        : null,
                },
                body: {
                    noScroll: document.body.classList.contains("no-scroll"),
                },
                ...extra,
            });
        };

        logViewportLifecycle("mount");
        logRootGeometry("mount");

        let secondFrame = null;

        const firstFrame = requestAnimationFrame(() => {
            logViewportLifecycle("first-raf");
            logRootGeometry("first-raf");

            secondFrame = requestAnimationFrame(() => {
                logViewportLifecycle("second-raf");
                logRootGeometry("second-raf");
            });
        });

        const handleVisualViewportResize = () => {
            logViewportLifecycle("visualViewport.resize");
            logRootGeometry("visualViewport.resize");
        };

        const handleVisualViewportScroll = () => {
            logViewportLifecycle("visualViewport.scroll");
            logRootGeometry("visualViewport.scroll");
        };

        const handleWindowResize = () => {
            logViewportLifecycle("window.resize");
            logRootGeometry("window.resize");
        };

        const handleOrientationChange = () => {
            logViewportLifecycle("orientationchange");
        };

        const handlePageShow = (event) => {
            logViewportLifecycle("pageshow", {
                persisted: event.persisted,
            });
        };

        const bodyClassObserver = new MutationObserver(() => {
            const phase = document.body.classList.contains("no-scroll")
                ? "body.no-scroll.add"
                : "body.no-scroll.remove";

            logViewportLifecycle(phase);
            logRootGeometry(phase);
        });

        window.visualViewport?.addEventListener("resize", handleVisualViewportResize);
        window.visualViewport?.addEventListener("scroll", handleVisualViewportScroll);
        window.addEventListener("resize", handleWindowResize);
        window.addEventListener("orientationchange", handleOrientationChange);
        window.addEventListener("pageshow", handlePageShow);
        bodyClassObserver.observe(document.body, {
            attributes: true,
            attributeFilter: ["class"],
        });

        return () => {
            cancelAnimationFrame(firstFrame);
            if (secondFrame) {
                cancelAnimationFrame(secondFrame);
            }
            window.visualViewport?.removeEventListener("resize", handleVisualViewportResize);
            window.visualViewport?.removeEventListener("scroll", handleVisualViewportScroll);
            window.removeEventListener("resize", handleWindowResize);
            window.removeEventListener("orientationchange", handleOrientationChange);
            window.removeEventListener("pageshow", handlePageShow);
            bodyClassObserver.disconnect();
        };
    }, [id, viewMode, viewportProbe, stageBootstrapped]);

    useEffect(() => {
        if ((!viewportProbe && !spatialDebug) || !stageBootstrapped) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const readTransform = (node) =>
            node ? window.getComputedStyle(node).transform : null;

        const getStageSnapshot = (phase, previousRect = null) => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRectRaw = beerCardRef.current?.getBoundingClientRect();
            const stageRect = toRect(stageRef.current);
            const cardRect = toRect(beerCardRef.current);
            const stableRect =
                previousRect && stageRect
                    ? Math.abs(stageRect.top - previousRect.top) <= 1 &&
                    Math.abs(stageRect.height - previousRect.height) <= 1
                    : false;

            return {
                phase,
                beerId: id,
                viewMode,
                visible,
                animating,
                direction,
                artVisible,
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                viewport: {
                    innerHeight: window.innerHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    visualViewportOffsetTop: window.visualViewport?.offsetTop,
                },
                rects: {
                    outer: toRect(outerRef.current),
                    wrapper: toRect(wrapperRef.current),
                    shell: toRect(shellRef.current),
                    stage: stageRect,
                    card: cardRect,
                },
                freeSpace: {
                    top: cardRectRaw ? Math.round(cardRectRaw.top) : null,
                    bottom: cardRectRaw
                        ? Math.round(viewportHeight - cardRectRaw.bottom)
                        : null,
                },
                transforms: {
                    shell: readTransform(shellRef.current),
                    info: readTransform(infoLayerRef.current),
                    art: readTransform(artOverlayRef.current),
                },
                stability: {
                    stableRect,
                    previousStageTop: previousRect?.top ?? null,
                    currentStageTop: stageRect?.top ?? null,
                },
            };
        };

        const logStagePhase = (phase, previousRect = null) => {
            const snapshot = getStageSnapshot(phase, previousRect);
            console.log("[stage-phase]", snapshot);

            if (phase === "ready-check") {
                logRootGeometry("ready-check");
            }

            return snapshot.rects.stage;
        };

        const mountRect = logStagePhase("mounting");
        let secondFrame = null;
        let thirdFrame = null;

        const firstFrame = requestAnimationFrame(() => {
            const firstRect = logStagePhase("settling:first-raf", mountRect);

            secondFrame = requestAnimationFrame(() => {
                const secondRect = logStagePhase(
                    "candidate-ready",
                    firstRect
                );

                thirdFrame = requestAnimationFrame(() => {
                    logStagePhase("ready-check", secondRect);
                });
            });
        });

        return () => {
            cancelAnimationFrame(firstFrame);
            if (secondFrame) {
                cancelAnimationFrame(secondFrame);
            }
            if (thirdFrame) {
                cancelAnimationFrame(thirdFrame);
            }
        };
    }, [
        id,
        viewMode,
        visible,
        animating,
        direction,
        artVisible,
        viewportProbe,
        spatialDebug,
        stageBootstrapped,
    ]);

    useEffect(() => {
        if (viewMode !== "art") {
            setArtVisible(false);
            return;
        }

        console.log("[artTransition]", {
            beerId: id,
            phase: "mount",
        });

        setArtVisible(false);

        const frame = requestAnimationFrame(() => {
            setArtVisible(true);
            console.log("[artTransition]", {
                beerId: id,
                phase: "visible",
            });
        });

        return () => cancelAnimationFrame(frame);
    }, [id, viewMode]);

    const logStageTransitionEnd = (layer, event) => {
        if (!viewportProbe && !spatialDebug) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const getTransform = (node) =>
            node ? window.getComputedStyle(node).transform : null;

        const readPostTransitionSnapshot = () => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRectRaw = beerCardRef.current?.getBoundingClientRect();
            const stageRect = toRect(stageRef.current);

            return {
                phase: "post-transition-ready-check",
                layer,
                propertyName: event.propertyName,
                beerId: id,
                viewMode,
                visible,
                animating,
                direction,
                artVisible,
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                viewport: {
                    innerHeight: window.innerHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    visualViewportOffsetTop: window.visualViewport?.offsetTop,
                },
                rects: {
                    outer: toRect(outerRef.current),
                    wrapper: toRect(wrapperRef.current),
                    shell: toRect(shellRef.current),
                    stage: stageRect,
                    card: toRect(beerCardRef.current),
                },
                freeSpace: {
                    top: cardRectRaw ? Math.round(cardRectRaw.top) : null,
                    bottom: cardRectRaw
                        ? Math.round(viewportHeight - cardRectRaw.bottom)
                        : null,
                },
                transforms: {
                    shell: getTransform(shellRef.current),
                    info: getTransform(infoLayerRef.current),
                    art: getTransform(artOverlayRef.current),
                },
                stability: {
                    currentStageTop: stageRect?.top ?? null,
                    currentStageHeight: stageRect?.height ?? null,
                },
            };
        };

        console.log("[stage-phase]", {
            phase: "transitionend",
            layer,
            propertyName: event.propertyName,
            beerId: id,
            viewMode,
            visible,
            animating,
            direction,
            artVisible,
            elapsed: Math.round(
                performance.now() - stageLifecycleStartRef.current
            ),
            transforms: {
                shell: shellRef.current
                    ? window.getComputedStyle(shellRef.current).transform
                    : null,
                info: infoLayerRef.current
                    ? window.getComputedStyle(infoLayerRef.current).transform
                    : null,
                art: artOverlayRef.current
                    ? window.getComputedStyle(artOverlayRef.current).transform
                    : null,
            },
        });

        if (event.propertyName !== "transform") return;

        requestAnimationFrame(() => {
            console.log("[stage-phase]", readPostTransitionSnapshot());
            logRootGeometry("post-transition-ready-check", {
                layer,
                propertyName: event.propertyName,
            });
        });
    };

    if (!beers.length) {
        return <div style={{ height: "var(--atlas-vh, 100vh)", background: "#000" }} />;
    }

    if (!beer) {
        return <div style={{ height: "var(--atlas-vh, 100vh)", background: "#000" }} />;
    }

    return (
        <div
            ref={outerRef}
            style={{
                height: "var(--atlas-vh, 100vh)",
                background: "#000",
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                position: "relative",
                overflow: "hidden",
                paddingTop: 0,
                paddingBottom: 0,
                boxSizing: "border-box",
                ...debugOutline("rgba(255, 77, 79, 0.9)"),
            }}
        >
            {spatialDebug && (
                <>
                    <div
                        style={{
                            position: "fixed",
                            left: 0,
                            right: 0,
                            top: "50%",
                            height: "1px",
                            background: "rgba(255,255,255,0.55)",
                            zIndex: 999999,
                            pointerEvents: "none",
                        }}
                    />

                    <div
                        style={{
                            position: "fixed",
                            top: "10px",
                            right: "10px",
                            zIndex: 999999,
                            pointerEvents: "none",
                            background: "rgba(0,0,0,0.78)",
                            border: "1px solid rgba(255,255,255,0.25)",
                            borderRadius: "6px",
                            color: "#fff",
                            fontSize: "11px",
                            lineHeight: 1.45,
                            padding: "8px",
                            maxWidth: "210px",
                            fontFamily: "monospace",
                        }}
                    >
                        <div>spatial debug</div>
                        <div>phase: {layoutSnapshot?.phase || "-"}</div>
                        <div>vh: {Math.round(layoutSnapshot?.viewport?.visualViewportHeight || 0)}</div>
                        <div>inner: {layoutSnapshot?.viewport?.innerHeight || "-"}</div>
                        <div>freeTop: {layoutSnapshot?.freeTop ?? "-"}</div>
                        <div>freeBottom: {layoutSnapshot?.freeBottom ?? "-"}</div>
                        <div>cardH: {layoutSnapshot?.cardRect?.height ?? "-"}</div>
                        <div>stageTop: {layoutSnapshot?.stageRect?.top ?? "-"}</div>
                    </div>
                </>
            )}

            {/* BACK */}
            <div
                style={{
                    position: "absolute",
                    top: "20px",
                    left: "50%",
                    transform: "translateX(-50%)",
                    width: "100%",
                    maxWidth: "360px",
                    zIndex: tutorialActive ? 201 : 10,
                }}
            >
                <div
                    onClick={() => navigate("/", { replace: true })}
                    style={{
                        color: "#aaa",
                        cursor: "pointer",
                        fontSize: "16px",
                        opacity: 0.7,
                    }}
                >
                    ← volver
                </div>
            </div>

            {/* WRAPPER */}
            <div
                ref={wrapperRef}
                style={{
                    position: "relative",
                    zIndex: tutorialActive ? 201 : undefined,
                    width: "100%",
                    maxWidth: "600px",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    ...debugOutline("rgba(64, 169, 255, 0.9)"),
                }}
                onTouchStart={(e) => {
                    if (e.touches.length > 1) {
                        multiTouchActive.current = true;
                        axisLock.current = null;
                        console.log("[gesture]", {
                            type: "multiTouchCancel",
                            phase: "start",
                            touches: e.touches.length,
                        });
                        return;
                    }

                    multiTouchActive.current = false;
                    activeTouchId.current = e.touches[0].identifier;
                    startX.current = e.touches[0].clientX;
                    startY.current = e.touches[0].clientY;
                    axisLock.current = null;

                    console.log("[gesture]", {
                        type: "touchStart",
                        beerId: id,
                        startX: startX.current,
                        startY: startY.current,
                        viewMode,
                    });

                    logRootGeometry("gesture.touchStart", {
                        startX: startX.current,
                        startY: startY.current,
                    });
                }}
                onTouchMove={(e) => {
                    const touch = Array.from(e.changedTouches).find(
                        item => item.identifier === activeTouchId.current
                    );
                    if (!touch) return;
                    if (e.touches.length > 1) {
                        if (!multiTouchActive.current) {
                            console.log("[gesture]", {
                                type: "multiTouchCancel",
                                phase: "move",
                                touches: e.touches.length,
                            });
                        }

                        multiTouchActive.current = true;
                        axisLock.current = null;
                        return;
                    }

                    if (multiTouchActive.current) return;

                    if (axisLock.current) return;

                    const currentX = touch.clientX;
                    const currentY = touch.clientY;
                    const deltaX = currentX - startX.current;
                    const deltaY = currentY - startY.current;
                    const absX = Math.abs(deltaX);
                    const absY = Math.abs(deltaY);
                    const lockThreshold = 14;
                    const ambiguityBuffer = 10;

                    if (absX < lockThreshold && absY < lockThreshold) return;

                    if (absX > absY + ambiguityBuffer) {
                        axisLock.current = "horizontal";
                    }

                    if (absY > absX + ambiguityBuffer) {
                        axisLock.current = "vertical";
                    }

                    if (axisLock.current) {
                        console.log("[gesture]", {
                            type: "axisLock",
                            axis: axisLock.current,
                            deltaX,
                            deltaY,
                        });
                    }
                }}
                onTouchEnd={(e) => {
                    const touch = Array.from(e.changedTouches).find(
                        item => item.identifier === activeTouchId.current
                    );
                    if (multiTouchActive.current) {
                        axisLock.current = null;
                        if (touch) {
                            activeTouchId.current = null;
                            startX.current = 0;
                            startY.current = 0;
                        }

                        console.log("[gesture]", {
                            type: "multiTouchEnd",
                            remainingTouches: e.touches.length,
                        });

                        if (e.touches.length === 0) {
                            multiTouchActive.current = false;
                        }

                        return;
                    }

                    if (!touch) return;
                    const endX = touch.clientX;
                    const endY = touch.clientY;
                    const deltaX = endX - startX.current;
                    const deltaY = endY - startY.current;
                    activeTouchId.current = null;
                    startX.current = 0;
                    startY.current = 0;
                    const absX = Math.abs(deltaX);
                    const absY = Math.abs(deltaY);
                    const ambiguityBuffer = 10;
                    let action = "none";

                    if (!axisLock.current) {
                        if (absX > absY + ambiguityBuffer) {
                            axisLock.current = "horizontal";
                        }

                        if (absY > absX + ambiguityBuffer) {
                            axisLock.current = "vertical";
                        }
                    }

                    console.log("[gesture]", {
                        type: "touchEnd",
                        beerId: id,
                        endX,
                        endY,
                        axis: axisLock.current,
                        deltaX,
                        deltaY,
                        viewMode,
                    });

                    if (axisLock.current === "vertical") {
                        if (deltaY < -70 && viewMode !== "art") {
                            action = "art";
                            if (tutorialVerticalActive && viewMode === "info") {
                                tutorialVerticalIntentRef.current = {
                                    phase: "vertical-to-art", beerId: id,
                                    originMode: "info", destinationMode: "art",
                                };
                            }
                            setViewMode("art");
                        }

                        if (deltaY > 70 && viewMode !== "info") {
                            action = "info";
                            if (tutorialReturnActive && viewMode === "art") {
                                tutorialVerticalIntentRef.current = {
                                    phase: "vertical-to-info", beerId: id,
                                    originMode: "art", destinationMode: "info",
                                };
                            }
                            setViewMode("info");
                        }

                        console.log("[gesture]", {
                            type: "action",
                            axis: "vertical",
                            action,
                            deltaX,
                            deltaY,
                        });

                        logRootGeometry("gesture.touchEnd", {
                            axis: "vertical",
                            action,
                            deltaX,
                            deltaY,
                        });

                        axisLock.current = null;
                        return;
                    }

                    if (axisLock.current !== "horizontal") {
                        console.log("[gesture]", {
                            type: "action",
                            axis: axisLock.current,
                            action,
                            deltaX,
                            deltaY,
                        });

                        logRootGeometry("gesture.touchEnd", {
                            axis: axisLock.current,
                            action,
                            deltaX,
                            deltaY,
                        });

                        axisLock.current = null;
                        return;
                    }

                    if (deltaX > 50 && prevBeer) {
                        action = "prev";
                        const tutorialState = horizontalTutorialState("prev", prevBeer);
                        setDirection("right");
                        setAnimating(true);

                        setTimeout(() => {
                            navigate(`/beer/${prevBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index - 1,
                                    ...tutorialState,
                                }
                            });
                        }, 0);
                    }

                    if (deltaX < -50 && nextBeer) {
                        action = "next";
                        const tutorialState = horizontalTutorialState("next", nextBeer);
                        setDirection("left");
                        setAnimating(true);

                        setTimeout(() => {
                            navigate(`/beer/${nextBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index + 1,
                                    ...tutorialState,
                                }
                            });
                        }, 0);
                    }

                    console.log("[gesture]", {
                        type: "action",
                        axis: "horizontal",
                        action,
                        deltaX,
                        deltaY,
                    });

                    logRootGeometry("gesture.touchEnd", {
                        axis: "horizontal",
                        action,
                        deltaX,
                        deltaY,
                    });

                    axisLock.current = null;
                }}
                onTouchCancel={(e) => {
                    if (!Array.from(e.changedTouches).some(
                        item => item.identifier === activeTouchId.current
                    )) return;
                    activeTouchId.current = null;
                    startX.current = 0;
                    startY.current = 0;
                    axisLock.current = null;
                    multiTouchActive.current = false;

                    console.log("[gesture]", {
                        type: "touchCancel",
                        touches: e.touches.length,
                    });
                }}
            >

                {/* FLECHAS */}
                {!isMobile && prevBeer && (
                    <div
                        onClick={() =>
                            navigate(`/beer/${prevBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index - 1
                                }
                            })
                        }
                        style={{
                            position: "absolute",
                            left: 0,
                            top: "50%",
                            transform: "translateY(-50%)",
                            fontSize: "32px",
                            opacity: 0.5,
                            cursor: "pointer",
                        }}
                    >
                        ←
                    </div>
                )}

                {!isMobile && nextBeer && (
                    <div
                        onClick={() =>
                            navigate(`/beer/${nextBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index + 1
                                }
                            })
                        }
                        style={{
                            position: "absolute",
                            right: 0,
                            top: "50%",
                            transform: "translateY(-50%)",
                            fontSize: "32px",
                            opacity: 0.5,
                            cursor: "pointer",
                        }}
                    >
                        →
                    </div>
                )}

                {/* CARD */}
                <div
                    style={{
                        width: "100%",
                        maxWidth: "360px",
                        display: "flex",
                        justifyContent: "center",

                        contain: "layout paint", // 🔥 PASO 2
                    }}
                >
                    <div
                        ref={shellRef}
                        className={tutorialHintAnimation && (viewMode === "info" || tutorialArtHorizontalActive || tutorialReturnActive) ? `beerdetail-tutorial-hint--${tutorialHintAnimation}` : undefined}
                        onAnimationEnd={(event) => {
                            if (event.target === event.currentTarget && event.animationName.startsWith("beerdetail-hint-")) {
                                setTutorialHintAnimation(null);
                            }
                        }}
                        onTransitionEnd={(event) =>
                            logStageTransitionEnd("shell", event)
                        }
                        style={{
                            width: "100%",

                            opacity: animating ? 0.6 : (visible ? 1 : 0.2),

                            transform: (
                                animating
                                    ? direction === "left"
                                        ? "translateX(-20px) scale(0.96)"
                                        : "translateX(20px) scale(0.96)"
                                    : visible
                                        ? "translateY(0px) scale(1)"
                                        : "translateY(30px) scale(0.92)"
                            ) + " translateZ(0)", // 🔥 PASO 1

                            willChange: "transform", // 🔥 PASO 1

                            transition: animating
                                ? "all 0.12s ease"
                                : "all 0.45s cubic-bezier(0.22, 1, 0.36, 1)",
                            ...debugOutline("rgba(115, 209, 61, 0.9)"),
                        }}
                    >
                        <div
                            ref={stageRef}
                            style={{
                                position: "relative",
                                width: "100%",
                                ...debugOutline("rgba(250, 173, 20, 0.9)"),
                            }}
                        >

                            {/* INFO */}
                            <div
                                ref={infoLayerRef}
                                onTransitionEnd={(event) =>
                                    logStageTransitionEnd("info", event)
                                }
                                style={{
                                    opacity: viewMode === "info" ? 1 : 0,
                                    transform: viewMode === "info" ? "scale(1)" : "scale(0.96)",
                                    transition: "all 0.25s ease",
                                }}
                            >
                                <BeerCard
                                    key={beer.id}
                                    beer={beer}
                                    layoutRef={beerCardRef}
                                    spatialDebug={spatialDebug}
                                />
                            </div>

                            {/* ARTE */}
                            {viewMode === "art" && (
                                <div
                                    ref={artOverlayRef}
                                    onTransitionEnd={(event) =>
                                        logStageTransitionEnd("art", event)
                                    }
                                    style={{
                                        position: "absolute",
                                        top: 0,
                                        left: 0,
                                        right: 0,
                                        bottom: 0,
                                        display: "flex",
                                        justifyContent: "center",
                                        alignItems: "center",
                                        background: "#000",
                                        opacity: artVisible ? 1 : 0,
                                        transform: artVisible ? "scale(1)" : "scale(0.985)",
                                        transition: "opacity 0.22s ease, transform 0.22s cubic-bezier(0.22, 1, 0.36, 1)",
                                        ...debugOutline("rgba(235, 47, 150, 0.9)"),
                                    }}
                                >
                                    <img
                                        src={beer.image_url}
                                        draggable={false}
                                        onContextMenu={(e) => e.preventDefault()}
                                        style={{
                                            width: "100%",
                                            height: "100%",
                                            objectFit: "contain",
                                            userSelect: "none",
                                            WebkitUserSelect: "none",
                                            WebkitTouchCallout: "none",
                                            pointerEvents: "auto",
                                        }}
                                    />
                                </div>
                            )}

                        </div>
                    </div>
                </div>

            </div>
            {tutorialActive && !["vertical-waiting", "art-waiting", "info-arrived"].includes(tutorialDialoguePhase) && (
                <>
                    {!tutorialExploring && <div
                        aria-hidden="true"
                        style={{ position: "fixed", inset: 0, zIndex: 203, background: "transparent" }}
                        onTouchStart={(event) => event.stopPropagation()}
                        onTouchMove={(event) => event.stopPropagation()}
                        onTouchEnd={(event) => event.stopPropagation()}
                        onTouchCancel={(event) => event.stopPropagation()}
                        onPointerDown={(event) => event.stopPropagation()}
                        onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            if (!tutorialClosing && tutorialDialoguePhase === "intro") setTutorialDialoguePhase("crossfade");
                        }}
                    />}
                    <div
                        className="home-tutorial-shade beerdetail-tutorial-shade"
                        style={{ opacity: tutorialClosing ? 0 : 1 }}
                        onTransitionEnd={(event) => {
                            if (tutorialClosing && event.propertyName === "opacity") {
                                setTutorialCompletedKey(location.key);
                            }
                        }}
                        aria-hidden="true"
                    />
                    <aside
                        className={`home-tutorial-message beerdetail-tutorial-message${tutorialExploring ? " beerdetail-tutorial-message--exploring" : ""}${tutorialMirrored ? " beerdetail-tutorial-message--mirrored" : ""}${tutorialDetailsDialogue ? " beerdetail-tutorial-message--details" : ""}`}
                        style={{ opacity: tutorialClosing ? 0 : 1 }}
                        aria-live="polite"
                    >
                        <img
                            className="home-tutorial-triton"
                            src={tutorialDetailsDialogue ? tritonDetails : tritonIntro}
                            style={{ visibility: (tutorialDetailsDialogue ? tritonDetailsReady : tritonReady) ? "visible" : "hidden" }}
                            alt=""
                            draggable={false}
                        />
                        <div
                            className={`home-tutorial-dialogue${tutorialPulseKey === location.key && !tutorialClosing && !tutorialExploring && tutorialDialoguePhase === "intro" ? " beerdetail-tutorial-dialogue--waiting" : ""}`}
                        >
                            <div className="beerdetail-tutorial-copy">
                                <div
                                    style={{ opacity: tutorialExploring || tutorialDialoguePhase === "crossfade" ? 0 : 1 }}
                                    aria-hidden={tutorialExploring || tutorialDialoguePhase === "crossfade"}
                                >
                                    <p className="home-tutorial-greeting"><strong>¡Buena elección!</strong></p>
                                    <p>Aquí tienes su ficha completa.</p>
                                    <p>Arriba está lo esencial y abajo las opciones para disfrutarla.</p>
                                </div>
                                <div
                                    className="beerdetail-tutorial-copy-next"
                                    style={{ opacity: (tutorialExploring || tutorialDialoguePhase === "crossfade") && !tutorialVerticalDialogue && !tutorialArtDialogue && !tutorialReturnDialogue && !tutorialDetailsDialogue ? 1 : 0 }}
                                    aria-hidden={(!tutorialExploring && tutorialDialoguePhase !== "crossfade") || tutorialVerticalDialogue || tutorialArtDialogue || tutorialReturnDialogue || tutorialDetailsDialogue}
                                >
                                    <p className="home-tutorial-greeting"><strong>¡Hay mucho más por descubrir!</strong></p>
                                    <p>Explora las cervezas que Tiburón tiene para ti.</p>
                                </div>
                                <div
                                    className="beerdetail-tutorial-copy-next"
                                    style={{ opacity: tutorialVerticalDialogue ? 1 : 0 }}
                                    aria-hidden={!tutorialVerticalDialogue}
                                >
                                    <p className="home-tutorial-greeting"><strong>Cada cerveza tiene algo que contar.</strong></p>
                                    <p>Descubre también su arte.</p>
                                </div>
                                <div
                                    className="beerdetail-tutorial-copy-next"
                                    style={{ opacity: tutorialArtDialogue ? 1 : 0 }}
                                    aria-hidden={!tutorialArtDialogue}
                                >
                                    <p className="home-tutorial-greeting"><strong>También puedes explorar desde aquí.</strong></p>
                                    <p>Descubre el arte de nuestras otras cervezas.</p>
                                </div>
                                <div
                                    className="beerdetail-tutorial-copy-next"
                                    style={{ opacity: tutorialReturnDialogue ? 1 : 0 }}
                                    aria-hidden={!tutorialReturnDialogue}
                                >
                                    <p className="home-tutorial-greeting"><strong>¿Terminaste de explorar?</strong></p>
                                    <p>Siempre puedes volver a la ficha.</p>
                                </div>
                                <div
                                    className="beerdetail-tutorial-copy-next"
                                    style={{ opacity: tutorialDialoguePhase === "details" ? 1 : 0 }}
                                    aria-hidden={tutorialDialoguePhase !== "details"}
                                >
                                    <p className="home-tutorial-greeting"><strong>Ya sabes cómo moverte por aquí.</strong></p>
                                    <p>Ahora mira estos últimos detalles.</p>
                                </div>
                            </div>
                        </div>
                    </aside>
                </>
            )}
        </div>
    );
}
