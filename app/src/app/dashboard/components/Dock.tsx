"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
    BarChart3, Bell, BookOpen, Compass, FileText,
    Lightbulb, Mail, Settings,
} from "lucide-react";

/* ─── Nav groups ─────────────────────────────────────────────── */

interface DockNavItem {
    name: string;
    path: string;
    icon: typeof BarChart3;
    exact?: boolean;
}

const marketItems: DockNavItem[] = [
    { name: "Market", path: "/dashboard", icon: BarChart3, exact: true },
    { name: "Explore", path: "/dashboard/explore", icon: Compass },
];

const validateItems: DockNavItem[] = [
    { name: "Validate", path: "/dashboard/validate", icon: Lightbulb },
    { name: "Reports", path: "/dashboard/reports", icon: FileText },
];

const monitorItems: DockNavItem[] = [
    { name: "Saved", path: "/dashboard/saved", icon: BookOpen },
    { name: "Alerts", path: "/dashboard/alerts", icon: Bell },
    { name: "Digest", path: "/dashboard/digest", icon: Mail },
];

const groups = [marketItems, validateItems, monitorItems];

const ACTIVE_VALIDATION_ID_KEY = "activeValidationId";
const ACTIVE_VALIDATION_IDEA_KEY = "activeValidationIdea";
const COMPLETED_VALIDATION_ID_KEY = "completedValidationId";
const VALIDATION_STORAGE_EVENT = "validation-storage";

/* ─── Divider ────────────────────────────────────────────────── */

function DockDivider() {
    return (
        <div
            style={{
                width: 1,
                height: 28,
                background: "hsl(0 0% 100% / 0.08)",
                margin: "0 4px",
                flexShrink: 0,
            }}
        />
    );
}

/* ─── Dock ───────────────────────────────────────────────────── */

export function Dock({
    currentPath,
    alertCount,
}: {
    currentPath: string;
    alertCount: number;
}) {
    const [hasCompletedValidation, setHasCompletedValidation] = useState(false);

    const emitValidationStorageChange = useCallback(() => {
        if (typeof window === "undefined") return;
        window.dispatchEvent(new Event(VALIDATION_STORAGE_EVENT));
    }, []);

    const syncValidationBadge = useCallback(() => {
        if (typeof window === "undefined") return;
        setHasCompletedValidation(Boolean(window.localStorage.getItem(COMPLETED_VALIDATION_ID_KEY)));
    }, []);

    useEffect(() => {
        if (typeof window === "undefined") return;

        const onStorageChange = () => syncValidationBadge();
        syncValidationBadge();

        window.addEventListener("storage", onStorageChange);
        window.addEventListener(VALIDATION_STORAGE_EVENT, onStorageChange);
        return () => {
            window.removeEventListener("storage", onStorageChange);
            window.removeEventListener(VALIDATION_STORAGE_EVENT, onStorageChange);
        };
    }, [syncValidationBadge]);

    useEffect(() => {
        if (typeof window === "undefined") return;

        if (currentPath?.startsWith("/dashboard/validate")) {
            window.localStorage.removeItem(COMPLETED_VALIDATION_ID_KEY);
            emitValidationStorageChange();
        }

        const checkValidationStatus = async () => {
            const activeValidationId = window.localStorage.getItem(ACTIVE_VALIDATION_ID_KEY);
            if (!activeValidationId) return;

            try {
                const response = await fetch(`/api/validate/${activeValidationId}/status`, { cache: "no-store" });
                if (!response.ok) return;

                const data = await response.json();
                const status = data?.validation?.status;
                if (status === "done") {
                    window.localStorage.removeItem(ACTIVE_VALIDATION_ID_KEY);
                    window.localStorage.removeItem(ACTIVE_VALIDATION_IDEA_KEY);
                    window.localStorage.setItem(COMPLETED_VALIDATION_ID_KEY, activeValidationId);
                    emitValidationStorageChange();
                } else if (status === "failed" || status === "error") {
                    window.localStorage.removeItem(ACTIVE_VALIDATION_ID_KEY);
                    window.localStorage.removeItem(ACTIVE_VALIDATION_IDEA_KEY);
                    emitValidationStorageChange();
                }
            } catch {
                // Best-effort dock polling only.
            }
        };

        void checkValidationStatus();
        const interval = window.setInterval(checkValidationStatus, 10000);
        return () => window.clearInterval(interval);
    }, [currentPath, emitValidationStorageChange]);

    return (
        <div
            className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[1000] w-[calc(100vw-1rem)] max-w-[980px] overflow-x-auto"
            style={{ scrollbarWidth: "none" }}
        >
            <nav
                className="mx-auto flex min-w-max items-center gap-1"
                style={{
                    background: "hsla(0,0%,4%,0.85)",
                    border: "1px solid hsl(0 0% 100% / 0.07)",
                    borderRadius: 16,
                    padding: "8px 12px",
                    backdropFilter: "blur(40px) saturate(200%)",
                    boxShadow: "0 0 0 1px hsl(0 0% 100% / 0.05), 0 24px 64px rgba(0,0,0,0.7), 0 0 40px hsla(16,100%,50%,0.05)",
                }}
            >
                {groups.map((group, gi) => (
                    <span key={gi} className="contents">
                        {gi > 0 && <DockDivider />}
                        {group.map((item) => {
                            const isActive = item.exact
                                ? currentPath === item.path
                                : currentPath === item.path || currentPath?.startsWith(item.path + "/");
                            const Icon = item.icon;
                            const badgeCount = item.path === "/dashboard/alerts" ? alertCount : 0;
                            const showValidationBadge = item.path === "/dashboard/validate" && hasCompletedValidation;
                            return (
                                <Link
                                    key={item.path}
                                    href={item.path}
                                    onClick={() => {
                                        if (item.path === "/dashboard/validate" && typeof window !== "undefined") {
                                            window.localStorage.removeItem(COMPLETED_VALIDATION_ID_KEY);
                                            emitValidationStorageChange();
                                        }
                                    }}
                                    className={`relative flex flex-col items-center gap-[3px] px-4 py-2 rounded-xl min-w-[60px] transition-all duration-150 text-[10px] tracking-wider ${
                                        isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
                                    }`}
                                    style={isActive ? { background: "hsl(16 100% 50% / 0.12)", border: "1px solid hsl(16 100% 50% / 0.2)" } : { border: "1px solid transparent" }}
                                >
                                    <div className="relative">
                                        <Icon className="w-[18px] h-[18px]" />
                                        {badgeCount > 0 && (
                                            <span className="absolute -top-2 -right-2 min-w-[16px] h-[16px] px-1 rounded-full bg-primary text-primary-foreground text-[9px] font-mono flex items-center justify-center">
                                                {badgeCount > 99 ? "99+" : badgeCount}
                                            </span>
                                        )}
                                        {showValidationBadge && (
                                            <span className="absolute -top-1.5 -right-1.5 w-[10px] h-[10px] rounded-full bg-primary border border-background shadow-[0_0_8px_hsl(16_100%_50%)]" />
                                        )}
                                    </div>
                                    <span className="font-medium">{item.name}</span>
                                    {isActive && (
                                        <span className="absolute bottom-1 w-1 h-1 rounded-full bg-primary" style={{ boxShadow: "0 0 6px hsl(16 100% 50%)" }} />
                                    )}
                                </Link>
                            );
                        })}
                    </span>
                ))}

                {/* Settings — utility icon at dock end */}
                <DockDivider />
                <Link
                    href="/dashboard/settings"
                    className={`relative flex flex-col items-center gap-[3px] px-4 py-2 rounded-xl min-w-[60px] transition-all duration-150 text-[10px] tracking-wider ${
                        currentPath?.startsWith("/dashboard/settings") ? "text-primary" : "text-muted-foreground hover:text-foreground"
                    }`}
                    style={currentPath?.startsWith("/dashboard/settings") ? { background: "hsl(16 100% 50% / 0.12)", border: "1px solid hsl(16 100% 50% / 0.2)" } : { border: "1px solid transparent" }}
                >
                    <Settings className="w-[18px] h-[18px]" />
                    <span className="font-medium">Settings</span>
                    {currentPath?.startsWith("/dashboard/settings") && (
                        <span className="absolute bottom-1 w-1 h-1 rounded-full bg-primary" style={{ boxShadow: "0 0 6px hsl(16 100% 50%)" }} />
                    )}
                </Link>
            </nav>
        </div>
    );
}
