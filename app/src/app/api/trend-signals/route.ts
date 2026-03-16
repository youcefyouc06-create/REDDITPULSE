import { NextResponse } from "next/server";
import { createClient as createAdminClient } from "@supabase/supabase-js";
import { createClient as createServerClient } from "@/lib/supabase-server";

const supabaseAdmin = createAdminClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);

type TrendTier = "EXPLODING" | "GROWING" | "STABLE" | "DECLINING";

interface PlatformWarning {
    platform: string;
    issue: string;
    status?: string;
    error_code?: string | null;
    error_detail?: string | null;
}

function safeParseJson(value: unknown) {
    if (typeof value === "string") {
        try {
            return JSON.parse(value);
        } catch {
            return value;
        }
    }
    return value;
}

function normalizeSources(value: unknown) {
    const parsed = safeParseJson(value);
    if (!Array.isArray(parsed)) return [];

    return parsed
        .map((item) => {
            if (typeof item === "string") {
                return { platform: item, count: 0 };
            }
            if (item && typeof item === "object") {
                const row = item as { platform?: unknown; count?: unknown };
                return {
                    platform: String(row.platform || "unknown"),
                    count: Number(row.count || 0),
                };
            }
            return null;
        })
        .filter(Boolean) as Array<{ platform: string; count: number }>;
}

function normalizePosts(value: unknown) {
    const parsed = safeParseJson(value);
    return Array.isArray(parsed) ? parsed : [];
}

function estimatePostCount24h(row: Record<string, unknown>) {
    const direct = Number(row.post_count_24h || 0);
    if (direct > 0) return direct;

    const sevenDay = Number(row.post_count_7d || 0);
    if (sevenDay <= 0) return 0;
    return Math.max(1, Math.round(sevenDay / 7));
}

function isFreshIdea(row: Record<string, unknown>, maxAgeHours = 48) {
    const lastUpdated = String(row.last_updated || "");
    if (!lastUpdated) return false;

    const updatedAt = Date.parse(lastUpdated);
    if (Number.isNaN(updatedAt)) return false;

    return Date.now() - updatedAt <= maxAgeHours * 60 * 60 * 1000;
}

function classifyTrend(row: Record<string, unknown>, sourceCount: number, postCount24h: number): TrendTier | null {
    const postCount7d = Number(row.post_count_7d || 0);
    const currentScore = Number(row.current_score || 0);
    const change24h = Number(row.change_24h || 0);

    if (postCount7d < 20) return null;
    if (sourceCount < 2 && postCount7d < 40) return null;

    if (postCount24h >= 15 && change24h >= 8 && currentScore >= 55) {
        return "EXPLODING";
    }
    if (postCount24h >= 8 && change24h >= 2 && currentScore >= 45) {
        return "GROWING";
    }
    if (change24h <= -6 && postCount7d >= 25) {
        return "DECLINING";
    }
    if (postCount7d >= 25 && currentScore >= 40) {
        return "STABLE";
    }

    return null;
}

function tierWeight(tier: TrendTier) {
    switch (tier) {
        case "EXPLODING":
            return 4;
        case "GROWING":
            return 3;
        case "STABLE":
            return 2;
        case "DECLINING":
            return 1;
        default:
            return 0;
    }
}

export async function GET() {
    const supabase = await createServerClient();
    const {
        data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const [{ data, error }, { data: validations }] = await Promise.all([
        supabaseAdmin
            .from("ideas")
            .select("*")
            .neq("confidence_level", "INSUFFICIENT")
            .order("last_updated", { ascending: false })
            .limit(300),
        supabaseAdmin
            .from("idea_validations")
            .select("report")
            .eq("user_id", user.id)
            .eq("status", "done")
            .order("created_at", { ascending: false })
            .limit(1),
    ]);

    if (error) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }

    const latestReport = validations?.[0]?.report;
    const parsedReport = typeof latestReport === "string" ? JSON.parse(latestReport) : latestReport || {};
    const platformWarnings = (parsedReport?.data_quality?.platform_warnings ||
        parsedReport?.platform_warnings ||
        []) as PlatformWarning[];

    const trends = (data || [])
        .filter((row: Record<string, unknown>) => isFreshIdea(row))
        .map((row: Record<string, unknown>) => {
            const sources = normalizeSources(row.sources);
            const sourceCount = Number(row.source_count || sources.length || 0);
            const postCount24h = estimatePostCount24h(row);
            const tier = classifyTrend(row, sourceCount, postCount24h);

            if (!tier) {
                return null;
            }

            return {
                id: String(row.id || row.slug || row.topic),
                slug: String(row.slug || ""),
                topic: String(row.topic || "Unknown theme"),
                category: String(row.category || "general"),
                tier,
                current_score: Number(row.current_score || 0),
                change_24h: Number(row.change_24h || 0),
                change_7d: Number(row.change_7d || 0),
                post_count_24h: postCount24h,
                post_count_7d: Number(row.post_count_7d || 0),
                post_count_total: Number(row.post_count_total || 0),
                source_count: sourceCount,
                sources,
                confidence_level: String(row.confidence_level || "UNKNOWN"),
                pain_count: Number(row.pain_count || 0),
                pain_summary: String(row.pain_summary || ""),
                top_posts: normalizePosts(row.top_posts),
                last_updated: String(row.last_updated || ""),
            };
        })
        .filter(Boolean)
        .sort((a, b) => {
            if (!a || !b) return 0;
            return (
                tierWeight(b.tier) - tierWeight(a.tier) ||
                b.post_count_24h - a.post_count_24h ||
                b.change_24h - a.change_24h ||
                b.current_score - a.current_score
            );
        })
        .slice(0, 24);

    return NextResponse.json({
        trends,
        platform_warnings: platformWarnings,
        source: "ideas",
    });
}
