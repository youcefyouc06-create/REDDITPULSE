import { PgBoss, type JobWithMetadata } from "pg-boss";
import { createClient as createAdminClient } from "@supabase/supabase-js";
import { type ValidationDepth, DEPTH_TIMEOUTS, DEFAULT_DEPTH } from "@/lib/validation-depth";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export const VALIDATION_QUEUE = "idea-validation";
const VALIDATION_RETRY_LIMIT = 2;
const DEFAULT_VALIDATION_TIMEOUT_SECONDS = DEPTH_TIMEOUTS[DEFAULT_DEPTH];

export interface ValidationJobPayload {
    validationId: string;
    userId: string;
    idea: string;
    depth: ValidationDepth;
}

export interface ValidationJobSnapshot {
    id: string;
    state: JobWithMetadata<ValidationJobPayload>["state"];
    retryCount: number;
    retryLimit: number;
    startedOn: string | null;
    createdOn: string | null;
    completedOn: string | null;
}

type ValidationProgressLine = {
    id: number;
    at: string;
    stream: "stdout" | "stderr";
    message: string;
};

let supabaseAdminClient: ReturnType<typeof createAdminClient<any>> | null = null;

let bossPromise: Promise<PgBoss> | null = null;

function getValidationTimeoutSeconds(depth: ValidationDepth = DEFAULT_DEPTH) {
    return DEPTH_TIMEOUTS[depth] || DEPTH_TIMEOUTS[DEFAULT_DEPTH];
}

function getQueueConnectionString() {
    const connectionString =
        process.env.SUPABASE_DB_POOLER_URL ||
        process.env.SUPABASE_POOLER_URL ||
        process.env.SUPABASE_DB_URL ||
        process.env.POSTGRES_URL_NON_POOLING ||
        process.env.DATABASE_URL ||
        process.env.POSTGRES_URL;

    if (!connectionString) {
        throw new Error("Missing Supabase Postgres connection string for pg-boss. Set SUPABASE_DB_URL or DATABASE_URL.");
    }

    return connectionString;
}

function getSupabaseKey() {
    return (
        process.env.SUPABASE_SECRET_KEY ||
        process.env.SUPABASE_SERVICE_ROLE_KEY ||
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
    );
}

function getAIEncryptionKey() {
    const encryptionKey = process.env.AI_ENCRYPTION_KEY?.trim();
    if (!encryptionKey) {
        throw new Error(
            "Missing AI_ENCRYPTION_KEY for validation worker. " +
            "Encrypted AI settings are required before queued validations can run.",
        );
    }
    return encryptionKey;
}

async function initQueue() {
    const connectionString = getQueueConnectionString();
    const boss = new PgBoss(connectionString);

    boss.on("error", (error: Error) => {
        console.error("[Queue] pg-boss error:", error);
    });

    try {
        await boss.start();
    } catch (error) {
        if (error instanceof Error && /ENOTFOUND|getaddrinfo/i.test(error.message) && /db\./i.test(connectionString)) {
            throw new Error(
                "Could not reach the direct Supabase database host. " +
                "This environment likely needs the Supabase Session Pooler connection string instead of the IPv6-only direct db host.",
            );
        }

        throw error;
    }

    try {
        await boss.createQueue(VALIDATION_QUEUE, {
            retryLimit: VALIDATION_RETRY_LIMIT,
            expireInSeconds: getValidationTimeoutSeconds(DEFAULT_DEPTH),
        });
    } catch {
        await boss.updateQueue(VALIDATION_QUEUE, {
            retryLimit: VALIDATION_RETRY_LIMIT,
            expireInSeconds: getValidationTimeoutSeconds(DEFAULT_DEPTH),
        }).catch(() => {});
    }

    return boss;
}

export async function getQueue() {
    if (!bossPromise) {
        bossPromise = initQueue().catch((error) => {
            bossPromise = null;
            throw error;
        });
    }

    return bossPromise;
}

export async function stopQueue() {
    if (!bossPromise) return;
    const boss = await bossPromise;
    await boss.stop().catch(() => {});
    bossPromise = null;
}

export async function enqueueValidationJob(payload: ValidationJobPayload) {
    const boss = await getQueue();
    const timeout = getValidationTimeoutSeconds(payload.depth);
    const jobId = await boss.send(VALIDATION_QUEUE, payload, {
        id: payload.validationId,
        retryLimit: VALIDATION_RETRY_LIMIT,
        expireInSeconds: timeout,
    });

    if (!jobId) {
        throw new Error("Queue rejected validation job");
    }

    console.log(`[Queue] Enqueued validation ${payload.validationId} for user ${payload.userId}`);
    return jobId;
}

export async function getValidationJobStatus(jobId: string): Promise<ValidationJobSnapshot | null> {
    const boss = await getQueue();
    const job = await boss.getJobById<ValidationJobPayload>(VALIDATION_QUEUE, jobId);

    if (!job) return null;

    return {
        id: job.id,
        state: job.state,
        retryCount: job.retryCount,
        retryLimit: job.retryLimit,
        startedOn: job.startedOn ? job.startedOn.toISOString() : null,
        createdOn: job.createdOn ? job.createdOn.toISOString() : null,
        completedOn: job.completedOn ? job.completedOn.toISOString() : null,
    };
}

async function updateValidation(validationId: string, updates: Record<string, unknown>) {
    const supabaseAdmin = getSupabaseAdmin();
    const { data, error } = await supabaseAdmin
        .from("idea_validations")
        .update(updates)
        .eq("id", validationId)
        .select("id")
        .single();

    if (error || !data) {
        throw new Error(
            `Could not persist validation ${validationId}: ${error?.message || "row not found after update"}`,
        );
    }
}

async function updateValidationProgress(validationId: string, lines: ValidationProgressLine[]) {
    const supabaseAdmin = getSupabaseAdmin();
    const latest = lines[lines.length - 1];
    const { data: current, error: currentError } = await supabaseAdmin
        .from("idea_validations")
        .select("status, report")
        .eq("id", validationId)
        .single();

    if (currentError) {
        throw new Error(
            `Could not load validation ${validationId} before progress update: ${currentError.message}`,
        );
    }

    if (current?.status === "done" || current?.status === "failed") {
        return;
    }

    const existingReport =
        current?.report && typeof current.report === "object" && !Array.isArray(current.report)
            ? current.report as Record<string, unknown>
            : {};

    const report = {
        ...existingReport,
        live_progress: {
            lines,
            latest_message: latest?.message || "",
            updated_at: new Date().toISOString(),
        },
    };

    const { data, error } = await supabaseAdmin
        .from("idea_validations")
        .update({ report })
        .eq("id", validationId)
        .neq("status", "done")
        .neq("status", "failed")
        .select("id")
        .maybeSingle();

    if (error) {
        throw new Error(
            `Could not persist validation progress ${validationId}: ${error.message}`,
        );
    }
}

function getSupabaseAdmin() {
    if (!supabaseAdminClient) {
        const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
        const supabaseKey = getSupabaseKey();

        if (!supabaseUrl || !supabaseKey) {
            throw new Error("Missing Supabase API env for queue worker. Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY.");
        }

        supabaseAdminClient = createAdminClient(supabaseUrl, supabaseKey);
    }

    return supabaseAdminClient;
}

function getPythonEnv() {
    const supabaseKey = getSupabaseKey() || "";
    const encryptionKey = getAIEncryptionKey();

    return {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL || "",
        SUPABASE_SERVICE_KEY: supabaseKey,
        SUPABASE_KEY: supabaseKey,
        AI_ENCRYPTION_KEY: encryptionKey,
    };
}

async function runValidationCommand(payload: ValidationJobPayload, signal: AbortSignal) {
    const configPath = path.join(os.tmpdir(), `validate_${payload.validationId}.json`);
    const projectRoot = path.resolve(process.cwd(), "..");
    const timeoutSeconds = getValidationTimeoutSeconds(payload.depth);
    const progressLines: ValidationProgressLine[] = [];
    let progressLineId = 0;
    let stdoutBuffer = "";
    let stderrBuffer = "";
    let progressFlushTimer: ReturnType<typeof setTimeout> | null = null;
    let progressWritesEnabled = true;

    const normalizeProgressLine = (line: string) => line.replace(/\r/g, "").trim();

    const persistProgressSoon = () => {
        if (!progressWritesEnabled || progressFlushTimer) return;
        progressFlushTimer = setTimeout(() => {
            progressFlushTimer = null;
            if (!progressWritesEnabled || progressLines.length === 0) return;
            const snapshot = progressLines.slice(-80);
            void updateValidationProgress(payload.validationId, snapshot).catch((error) => {
                console.error(`[Queue] Validation ${payload.validationId} progress persistence failed:`, error);
            });
        }, 750);
    };

    const pushProgressLine = (stream: "stdout" | "stderr", rawLine: string) => {
        const message = normalizeProgressLine(rawLine);
        if (!message) return;
        progressLineId += 1;
        progressLines.push({
            id: progressLineId,
            at: new Date().toISOString(),
            stream,
            message,
        });
        if (progressLines.length > 80) {
            progressLines.splice(0, progressLines.length - 80);
        }
        persistProgressSoon();
    };

    const flushBufferedProgress = () => {
        if (stdoutBuffer.trim()) {
            pushProgressLine("stdout", stdoutBuffer);
            stdoutBuffer = "";
        }
        if (stderrBuffer.trim()) {
            pushProgressLine("stderr", stderrBuffer);
            stderrBuffer = "";
        }
    };

    await fs.writeFile(configPath, JSON.stringify({
        validation_id: payload.validationId,
        idea: payload.idea,
        user_id: payload.userId,
        depth: payload.depth || DEFAULT_DEPTH,
    }));

    try {
        await new Promise<void>((resolve, reject) => {
            const child = spawn("python", ["validate_idea.py", "--config-file", configPath], {
                cwd: projectRoot,
                env: getPythonEnv(),
                stdio: ["ignore", "pipe", "pipe"],
                detached: false,
            });

            let settled = false;

            const finish = (callback: () => void) => {
                if (settled) return;
                settled = true;
                clearTimeout(timeoutHandle);
                if (progressFlushTimer) {
                    clearTimeout(progressFlushTimer);
                    progressFlushTimer = null;
                }
                progressWritesEnabled = false;
                signal.removeEventListener("abort", onAbort);
                callback();
            };

            const onAbort = () => {
                child.kill();
                finish(() => reject(new Error(
                    `Validation job aborted by queue (worker shutdown or ${timeoutSeconds}s queue timeout)`,
                )));
            };

            const timeoutHandle = setTimeout(() => {
                child.kill();
                finish(() => reject(new Error(`Validation exceeded ${timeoutSeconds}s timeout`)));
            }, timeoutSeconds * 1000);

            signal.addEventListener("abort", onAbort, { once: true });

            child.stdout?.on("data", (data: Buffer) => {
                const text = data.toString();
                console.log(`[Queue Validate ${payload.validationId}] ${text.trim()}`);
                stdoutBuffer += text;
                const lines = stdoutBuffer.split(/\r?\n/);
                stdoutBuffer = lines.pop() || "";
                for (const line of lines) {
                    pushProgressLine("stdout", line);
                }
            });

            child.stderr?.on("data", (data: Buffer) => {
                const text = data.toString();
                console.error(`[Queue Validate ${payload.validationId} ERR] ${text.trim()}`);
                stderrBuffer += text;
                const lines = stderrBuffer.split(/\r?\n/);
                stderrBuffer = lines.pop() || "";
                for (const line of lines) {
                    pushProgressLine("stderr", line);
                }
            });

            child.on("error", (error) => {
                finish(() => reject(error));
            });

            child.on("close", (code) => {
                flushBufferedProgress();
                if (code === 0) {
                    finish(resolve);
                    return;
                }

                finish(() => reject(new Error(`Validation process exited with code ${code}`)));
            });
        });
    } finally {
        await fs.unlink(configPath).catch(() => {});
    }
}

export async function startValidationWorker() {
    const boss = await getQueue();

    const workerId = await boss.work<ValidationJobPayload>(VALIDATION_QUEUE, { includeMetadata: true, batchSize: 1, localConcurrency: 1 }, async (jobs) => {
        const [job] = jobs;
        if (!job) {
            return { ok: true };
        }
        const willRetry = job.retryCount < job.retryLimit;

        console.log(
            `[Queue] Starting validation ${job.data.validationId} ` +
            `(attempt ${job.retryCount + 1} of ${job.retryLimit + 1}, timeout ${getValidationTimeoutSeconds(job.data.depth)}s, depth ${job.data.depth})`,
        );

        try {
            await updateValidation(job.data.validationId, {
                status: "starting",
                completed_at: null,
            });
        } catch (error) {
            console.error(
                `[Queue] Validation ${job.data.validationId} could not enter starting state:`,
                error,
            );
            throw error;
        }

        try {
            await runValidationCommand(job.data, job.signal);
            console.log(`[Queue] Validation ${job.data.validationId} completed successfully`);
            return { ok: true };
        } catch (error) {
            const message = error instanceof Error ? error.message : "Validation worker failed";
            const failurePayload = willRetry
                ? {
                    status: "queued",
                    report: JSON.stringify({
                        error: message,
                        retrying: true,
                        failure_stage: "worker",
                    }),
                }
                : {
                    status: "failed",
                    report: JSON.stringify({
                        error: message,
                        failure_stage: "worker",
                    }),
                    completed_at: new Date().toISOString(),
                };

            try {
                await updateValidation(job.data.validationId, failurePayload);
            } catch (persistError) {
                console.error(
                    `[Queue] Validation ${job.data.validationId} status persistence failed after worker error:`,
                    persistError,
                );
            }

            console.error(
                `[Queue] Validation ${job.data.validationId} failed: ${message}` +
                (willRetry ? " — retry scheduled" : " — no retries remaining"),
            );
            throw error;
        }
    });

    return { boss, workerId };
}
