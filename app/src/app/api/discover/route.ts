import { createClient } from "@/lib/supabase-server";
import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import path from "path";
import { checkProcessLimit, trackProcess, releaseProcess } from "@/lib/process-limiter";
import { checkPremium } from "@/lib/check-premium";

// ── Rate Limiting ──
const discoverTimestamps = new Map<string, number[]>();
const MAX_DISCOVERS_PER_HOUR = 3;

function checkRateLimit(userId: string): boolean {
    const now = Date.now();
    const hourAgo = now - 3600_000;
    const stamps = (discoverTimestamps.get(userId) || []).filter(t => t > hourAgo);
    if (stamps.length >= MAX_DISCOVERS_PER_HOUR) return false;
    stamps.push(now);
    discoverTimestamps.set(userId, stamps);
    return true;
}

// POST — launch opportunity discovery scan (no specific idea needed)
export async function POST(req: NextRequest) {
    try {
        const supabase = await createClient();
        const { data: { user } } = await supabase.auth.getUser();
        if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

        if (!checkRateLimit(user.id)) {
            return NextResponse.json({ error: "Rate limit exceeded — max 3 discovery scans per hour" }, { status: 429 });
        }

        const { isPremium } = await checkPremium(supabase, user.id);
        if (!isPremium) {
            return NextResponse.json({ error: "Premium subscription required" }, { status: 403 });
        }

        // Optional: filter sources
        const body = await req.json().catch(() => ({}));
        const sources = body.sources || ["reddit", "hackernews", "producthunt", "indiehackers"];
        const validSources = sources.filter((s: string) =>
            ["reddit", "hackernews", "producthunt", "indiehackers"].includes(s)
        );

        if (!checkProcessLimit(user.id)) {
            return NextResponse.json({ error: "Too many active processes — please wait" }, { status: 429 });
        }

        trackProcess(user.id);

        const projectRoot = path.resolve(process.cwd(), "..");
        const sourcesArg = validSources.join(" ");
        const cmd = `python scraper_job.py --sources ${sourcesArg}`;

        const env = {
            ...process.env,
            PYTHONIOENCODING: "utf-8",
            SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL || "",
            SUPABASE_SERVICE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY || "",
            SUPABASE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "",
        };

        exec(cmd, { cwd: projectRoot, env, timeout: 600_000 }, (error, stdout, stderr) => {
            releaseProcess(user.id);
            if (error) {
                console.error(`Discovery scan error:`, error.message);
                console.error(stderr);
            }
            console.log(`Discovery scan output:`, stdout?.slice(0, 2000));
        });

        return NextResponse.json({ status: "started", sources: validSources });
    } catch (err) {
        console.error("Discover POST error:", err);
        return NextResponse.json({ error: "Internal server error" }, { status: 500 });
    }
}

// GET — check latest scraper run status
export async function GET() {
    try {
        const supabase = await createClient();
        const { data: { user } } = await supabase.auth.getUser();
        if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

        // Get the latest scraper run
        const { data: runs } = await supabase
            .from("scraper_runs")
            .select("*")
            .order("started_at", { ascending: false })
            .limit(1);

        const latestRun = runs?.[0] || null;

        // Get current market snapshot counts used by the board.
        const { count } = await supabase
            .from("ideas")
            .select("*", { count: "exact", head: true })
            .neq("confidence_level", "INSUFFICIENT");

        const { data: ideaRows } = await supabase
            .from("ideas")
            .select("post_count_total")
            .neq("confidence_level", "INSUFFICIENT");

        const trackedPostCount = Array.isArray(ideaRows)
            ? ideaRows.reduce((sum, row) => sum + Number(row.post_count_total || 0), 0)
            : 0;

        return NextResponse.json({
            latestRun,
            ideaCount: count || 0,
            trackedPostCount,
        });
    } catch {
        return NextResponse.json({ latestRun: null, ideaCount: 0, trackedPostCount: 0 });
    }
}
