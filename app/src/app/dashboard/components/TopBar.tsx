"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, ChevronDown, LoaderCircle, PlugZap, RefreshCw } from "lucide-react";
import { FEATURE_FLAGS } from "@/lib/feature-flags";
import type { RedditConnectionSummary, RedditSourcePack } from "@/lib/reddit-lab";

type RedditLabTopbarState = {
    oauth_configured: boolean;
    connection: RedditConnectionSummary | null;
    source_packs: RedditSourcePack[];
};

export function TopBar({
    postCount,
    modelCount,
    ideaCount,
}: {
    postCount: number;
    modelCount: number;
    ideaCount: number;
}) {
    const [clock, setClock] = useState("");
    const [redditState, setRedditState] = useState<RedditLabTopbarState | null>(null);
    const [redditLoading, setRedditLoading] = useState(false);
    const [redditActionError, setRedditActionError] = useState<string | null>(null);
    const [redditMenuOpen, setRedditMenuOpen] = useState(false);
    const redditMenuRef = useRef<HTMLDivElement | null>(null);

    const redditConnection = redditState?.connection ?? null;
    const redditConnected = Boolean(redditConnection?.id);
    const defaultPack = useMemo(
        () => redditState?.source_packs?.find((pack) => pack.is_default_for_validation) || redditState?.source_packs?.[0] || null,
        [redditState],
    );

    const lastSyncedText = useMemo(() => {
        if (!redditConnection?.last_synced_at) return "Not synced yet";
        const date = new Date(redditConnection.last_synced_at);
        if (Number.isNaN(date.valueOf())) return "Not synced yet";
        return `Synced ${date.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
        })} ${date.toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
        })}`;
    }, [redditConnection?.last_synced_at]);

    const loadRedditState = async () => {
        setRedditActionError(null);
        try {
            const response = await fetch("/api/settings/lab/reddit/connection", { cache: "no-store" });
            if (!response.ok) {
                throw new Error("Could not load Reddit connection.");
            }
            const payload = await response.json();
            setRedditState({
                oauth_configured: Boolean(payload?.oauth_configured),
                connection: payload?.connection ?? null,
                source_packs: Array.isArray(payload?.source_packs) ? payload.source_packs : [],
            });
        } catch (error) {
            setRedditState({
                oauth_configured: false,
                connection: null,
                source_packs: [],
            });
            setRedditActionError(error instanceof Error ? error.message : "Could not load Reddit connection.");
        }
    };

    useEffect(() => {
        const formatClock = () => new Date().toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
        setClock(formatClock());
        const interval = setInterval(() => setClock(formatClock()), 1000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (!FEATURE_FLAGS.REDDIT_CONNECTION_LAB_ENABLED) return;
        void loadRedditState();
    }, []);

    useEffect(() => {
        if (!redditMenuOpen) return;

        const handlePointerDown = (event: MouseEvent) => {
            if (!redditMenuRef.current?.contains(event.target as Node)) {
                setRedditMenuOpen(false);
            }
        };

        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                setRedditMenuOpen(false);
            }
        };

        document.addEventListener("mousedown", handlePointerDown);
        document.addEventListener("keydown", handleEscape);
        return () => {
            document.removeEventListener("mousedown", handlePointerDown);
            document.removeEventListener("keydown", handleEscape);
        };
    }, [redditMenuOpen]);

    const syncReddit = async () => {
        setRedditLoading(true);
        setRedditActionError(null);
        try {
            const response = await fetch("/api/settings/lab/reddit/sync", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({}),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload?.error || "Could not sync Reddit.");
            }
            await loadRedditState();
        } catch (error) {
            setRedditActionError(error instanceof Error ? error.message : "Could not sync Reddit.");
        } finally {
            setRedditLoading(false);
        }
    };

    return (
        <header
            className="sticky top-0 z-50 flex h-11 items-center justify-between px-6"
            style={{
                background: "hsla(0,0%,4%,0.7)",
                borderBottom: "1px solid hsl(0 0% 100% / 0.07)",
                backdropFilter: "blur(20px)",
            }}
        >
            <div className="flex items-center gap-4">
                <span className="font-display text-[15px] font-bold tracking-[0.08em]">
                    <span className="text-muted-foreground">O</span>{" "}
                    <span className="text-foreground">REDDIT</span>
                    <span className="text-primary">PULSE</span>
                </span>

                <div className="hidden h-3 w-px bg-border sm:block" />

                <div
                    className="hidden items-center gap-1.5 rounded-full px-2.5 py-0.5 sm:flex"
                    style={{ background: "hsla(134,61%,55%,0.08)", border: "1px solid hsla(134,61%,55%,0.2)" }}
                >
                    <span className="status-live h-[5px] w-[5px] rounded-full bg-build" style={{ animation: "pulse-green 2s ease infinite" }} />
                    <span className="text-[11px] font-mono font-medium text-build">LIVE</span>
                </div>

                <div className="hidden h-3 w-px bg-border md:block" />

                <span className="hidden text-[11px] font-mono text-muted-foreground md:inline">
                    {ideaCount.toLocaleString()} ideas discovered · {postCount.toLocaleString()} posts archived
                </span>
            </div>

            <div className="flex items-center gap-3">
                {FEATURE_FLAGS.REDDIT_CONNECTION_LAB_ENABLED && (
                    <div className="relative" ref={redditMenuRef}>
                        <button
                            type="button"
                            onClick={() => {
                                setRedditActionError(null);
                                setRedditMenuOpen((open) => {
                                    const next = !open;
                                    if (next) void loadRedditState();
                                    return next;
                                });
                            }}
                            className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
                                redditConnected ? "text-foreground" : "text-primary"
                            }`}
                            style={redditConnected
                                ? { background: "hsl(0 0% 100% / 0.04)", borderColor: "hsl(0 0% 100% / 0.08)" }
                                : { background: "hsl(var(--orange-dim))", borderColor: "hsl(16 100% 50% / 0.2)" }}
                            aria-haspopup="menu"
                            aria-expanded={redditMenuOpen}
                        >
                            <span className={`h-2 w-2 rounded-full ${redditConnected ? "bg-build" : "bg-primary"}`} />
                            {redditConnected ? <CheckCircle2 className="h-3.5 w-3.5 text-build" /> : <PlugZap className="h-3.5 w-3.5" />}
                            <span className="hidden sm:inline">Reddit</span>
                            {redditConnected && redditConnection?.reddit_username ? (
                                <span className="hidden max-w-[120px] truncate text-muted-foreground lg:inline">
                                    u/{redditConnection.reddit_username}
                                </span>
                            ) : (
                                <span className="hidden md:inline">Connect</span>
                            )}
                            <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${redditMenuOpen ? "rotate-180" : ""}`} />
                        </button>

                        {redditMenuOpen && (
                            <div
                                className="absolute right-0 top-[calc(100%+8px)] w-[340px] rounded-2xl border p-3 shadow-2xl"
                                style={{
                                    background: "hsla(0,0%,5%,0.96)",
                                    borderColor: "hsl(0 0% 100% / 0.08)",
                                    backdropFilter: "blur(20px)",
                                }}
                            >
                                <div className="flex items-start justify-between gap-3 border-b pb-3" style={{ borderColor: "hsl(0 0% 100% / 0.06)" }}>
                                    <div>
                                        <p className="text-[11px] font-mono uppercase tracking-[0.14em] text-muted-foreground">
                                            Reddit
                                        </p>
                                        <p className="mt-1 text-sm font-semibold text-foreground">
                                            {redditConnected
                                                ? `Connected as u/${redditConnection?.reddit_username || "reddit"}`
                                                : "Connect Reddit to personalize validation"}
                                        </p>
                                        <p className="mt-1 text-xs text-muted-foreground">
                                            {redditConnected
                                                ? `${defaultPack ? `${defaultPack.subreddits.length} subs in ${defaultPack.name}` : "Connected and ready for validation"}`
                                                : "Use your Reddit account to sync communities and improve source targeting automatically."}
                                        </p>
                                    </div>
                                    <span
                                        className={`inline-flex items-center rounded-full px-2 py-1 text-[10px] font-mono uppercase tracking-[0.12em] ${
                                            redditConnected ? "text-build" : "text-primary"
                                        }`}
                                        style={redditConnected
                                            ? { background: "hsla(134,61%,55%,0.08)", border: "1px solid hsla(134,61%,55%,0.18)" }
                                            : { background: "hsl(var(--orange-dim))", border: "1px solid hsl(16 100% 50% / 0.2)" }}
                                    >
                                        {redditConnected ? "Connected" : "Optional"}
                                    </span>
                                </div>

                                {redditActionError ? (
                                    <div
                                        className="mt-3 rounded-xl px-3 py-2 text-xs text-destructive"
                                        style={{ background: "hsla(0,84%,60%,0.08)", border: "1px solid hsla(0,84%,60%,0.16)" }}
                                    >
                                        {redditActionError}
                                    </div>
                                ) : null}

                                {redditConnected ? (
                                    <div className="mt-3 grid grid-cols-2 gap-2">
                                        <div
                                            className="rounded-xl border px-3 py-2"
                                            style={{ borderColor: "hsl(0 0% 100% / 0.06)", background: "hsl(0 0% 100% / 0.02)" }}
                                        >
                                            <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-muted-foreground">Default pack</p>
                                            <p className="mt-1 text-sm font-semibold text-white">{defaultPack?.name || "No pack yet"}</p>
                                        </div>
                                        <div
                                            className="rounded-xl border px-3 py-2"
                                            style={{ borderColor: "hsl(0 0% 100% / 0.06)", background: "hsl(0 0% 100% / 0.02)" }}
                                        >
                                            <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-muted-foreground">Last sync</p>
                                            <p className="mt-1 text-sm font-semibold text-white">{lastSyncedText}</p>
                                        </div>
                                    </div>
                                ) : null}

                                <div className="mt-3 grid gap-2">
                                    {redditConnected ? (
                                        <>
                                            <button
                                                type="button"
                                                onClick={() => void syncReddit()}
                                                disabled={redditLoading}
                                                className="inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-white/5 disabled:opacity-60"
                                                style={{ borderColor: "hsl(0 0% 100% / 0.08)" }}
                                            >
                                                {redditLoading ? (
                                                    <LoaderCircle className="h-4 w-4 animate-spin" />
                                                ) : (
                                                    <RefreshCw className="h-4 w-4" />
                                                )}
                                                <span>{redditLoading ? "Syncing..." : "Refresh Reddit Data"}</span>
                                            </button>
                                            <div className="grid grid-cols-2 gap-2">
                                                <Link
                                                    href="/dashboard/validate"
                                                    onClick={() => setRedditMenuOpen(false)}
                                                    className="inline-flex items-center justify-center rounded-xl border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-white/5"
                                                    style={{ borderColor: "hsl(0 0% 100% / 0.08)" }}
                                                >
                                                    Go to Validate
                                                </Link>
                                                <Link
                                                    href="/dashboard/settings/reddit-lab"
                                                    onClick={() => setRedditMenuOpen(false)}
                                                    className="inline-flex items-center justify-center rounded-xl border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-white/5"
                                                    style={{ borderColor: "hsl(0 0% 100% / 0.08)" }}
                                                >
                                                    Manage Packs
                                                </Link>
                                            </div>
                                            <p className="px-1 text-[11px] leading-5 text-muted-foreground">
                                                Normal validations will automatically use this Reddit connection when available.
                                            </p>
                                        </>
                                    ) : (
                                        <>
                                            <Link
                                                href={redditState?.oauth_configured === false ? "/dashboard/settings/reddit-lab" : "/api/settings/lab/reddit/oauth/start"}
                                                onClick={() => setRedditMenuOpen(false)}
                                                className="inline-flex items-center justify-center rounded-xl border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-white/5"
                                                style={{ borderColor: "hsl(0 0% 100% / 0.08)" }}
                                            >
                                                {redditState?.oauth_configured === false ? "Finish OAuth Setup" : "Connect Reddit"}
                                            </Link>
                                            <Link
                                                href="/dashboard/settings/reddit-lab"
                                                onClick={() => setRedditMenuOpen(false)}
                                                className="inline-flex items-center justify-center rounded-xl border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-white/5"
                                                style={{ borderColor: "hsl(0 0% 100% / 0.08)" }}
                                            >
                                                Open Reddit Settings
                                            </Link>
                                            <p className="px-1 text-[11px] leading-5 text-muted-foreground">
                                                {redditState?.oauth_configured === false
                                                    ? "OAuth is not configured locally yet. Add Reddit OAuth keys first, then connect."
                                                    : "After connection, the normal Validate page will use your Reddit context automatically."}
                                            </p>
                                        </>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                <div className="flex items-center gap-1.5">
                    {Array.from({ length: Math.max(modelCount, 1) }).slice(0, 5).map((_, index) => (
                        <div
                            key={index}
                            className="h-[7px] w-[7px] rounded-full"
                            style={{ background: index === 0 ? "#ff4500" : index === 1 ? "#ff6534" : "hsla(16,100%,50%,0.5)" }}
                        />
                    ))}
                </div>
                <div className="h-3 w-px bg-border" />
                <span className="tabular-nums text-[11px] font-mono text-muted-foreground">{clock}</span>
            </div>
        </header>
    );
}
