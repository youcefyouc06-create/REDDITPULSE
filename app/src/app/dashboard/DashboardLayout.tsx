"use client";

import React, { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Dock } from "./components/Dock";
import { TopBar } from "./components/TopBar";
import { FEATURE_FLAGS } from "@/lib/feature-flags";

export function DashboardLayout({
    children,
    userEmail: _userEmail,
    userPlan: _userPlan,
}: {
    children: React.ReactNode;
    userEmail: string;
    userPlan: string;
}) {
    const pathname = usePathname();
    const [ideaCount, setIdeaCount] = useState(0);
    const [postCount, setPostCount] = useState(0);
    const [modelCount, setModelCount] = useState(0);
    const [alertCount, setAlertCount] = useState(0);

    useEffect(() => {
        const refreshMarketSummary = () => {
            fetch("/api/discover", { cache: "no-store" })
                .then((r) => r.ok ? r.json() : Promise.reject(new Error("Failed to load market summary")))
                .then((res) => {
                    setIdeaCount(Number(res.ideaCount || 0));
                    setPostCount(Number(res.trackedPostCount || 0));
                })
                .catch(() => {});
        };

        fetch("/api/settings/ai")
            .then((r) => r.json())
            .then((res) => setModelCount((res.configs || []).filter((config: any) => config.is_active).length))
            .catch(() => {});

        const refreshAlerts = () => {
            if (!FEATURE_FLAGS.ALERTS_ENABLED) {
                setAlertCount(0);
                return;
            }
            fetch("/api/alerts")
                .then((r) => r.ok ? r.json() : { unread_count: 0 })
                .then((res) => setAlertCount(res.unread_count || 0))
                .catch(() => setAlertCount(0));
        };
        const refreshWhenVisible = () => {
            if (typeof document === "undefined" || document.visibilityState === "visible") {
                refreshMarketSummary();
                refreshAlerts();
            }
        };

        refreshMarketSummary();
        refreshAlerts();
        document.addEventListener("visibilitychange", refreshWhenVisible);
        const marketInterval = setInterval(refreshMarketSummary, 60000);
        const alertInterval = FEATURE_FLAGS.ALERTS_ENABLED ? setInterval(refreshAlerts, 60000) : null;

        return () => {
            document.removeEventListener("visibilitychange", refreshWhenVisible);
            clearInterval(marketInterval);
            if (alertInterval) clearInterval(alertInterval);
        };
    }, []);

    return (
        <div className="flex h-screen w-full relative selection:bg-primary/30 overflow-hidden">
            <div className="noise-overlay" />

            <div
                className="fixed pointer-events-none rounded-full"
                style={{
                    top: -200, left: -150, width: 700, height: 700,
                    filter: "blur(140px)", background: "hsla(16, 100%, 50%, 0.07)",
                    animation: "drift 18s ease-in-out infinite alternate", zIndex: 0,
                }}
            />
            <div
                className="fixed pointer-events-none rounded-full"
                style={{
                    bottom: -250, right: -100, width: 600, height: 600,
                    filter: "blur(120px)", background: "hsla(16, 70%, 50%, 0.05)",
                    animation: "drift 24s ease-in-out infinite alternate-reverse", zIndex: 0,
                }}
            />

            <div className="flex flex-col w-full h-full relative z-10">
                <TopBar
                    postCount={postCount}
                    modelCount={modelCount}
                    ideaCount={ideaCount}
                />
                <main className="flex-1 overflow-y-auto relative z-10 p-6 lg:p-8 pb-32">
                    {children}
                </main>
            </div>

            <Dock currentPath={pathname} alertCount={alertCount} />
        </div>
    );
}
