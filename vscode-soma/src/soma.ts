/**
 * Async child-process wrapper for the soma CLI.
 *
 * Uses child_process.spawn (non-blocking) so the extension host UI thread is
 * never stalled — important because the briefing refreshes on every file save.
 */
import { spawn } from "child_process";
import * as vscode from "vscode";

function somaPath(): string {
  return vscode.workspace
    .getConfiguration("soma")
    .get<string>("executablePath", "soma");
}

export interface ContextData {
  project: string;
  branch: string;
  confidence: string;
  commits7d: number;
  filesChanged: number;
  recentCommits: Array<{ message: string; when: string }>;
  filesInMotion: Array<{ path: string; modified: string }>;
  blockers: string[];
  focus: string;
  description: string;
}

interface RunResult {
  stdout: string;
  stderr: string;
  ok: boolean;
}

function run(args: string[]): Promise<RunResult> {
  return new Promise((resolve) => {
    let proc;
    try {
      proc = spawn(somaPath(), args, { windowsHide: true });
    } catch {
      resolve({ stdout: "", stderr: "spawn failed", ok: false });
      return;
    }

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => proc.kill(), 10_000);

    proc.stdout?.on("data", (d) => (stdout += d.toString()));
    proc.stderr?.on("data", (d) => (stderr += d.toString()));
    proc.on("error", () => {
      clearTimeout(timer);
      resolve({ stdout: "", stderr: "soma not found", ok: false });
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      resolve({ stdout, stderr, ok: code === 0 });
    });
  });
}

export async function getBriefingText(): Promise<string> {
  const r = await run(["briefing"]);
  return r.ok ? r.stdout : r.stderr || "soma briefing failed — is soma installed?";
}

export async function getContextText(project: string): Promise<string> {
  const r = await run(["context", project]);
  return r.ok ? r.stdout : `Error getting context for ${project}`;
}

export async function getContextJson(project: string): Promise<ContextData | null> {
  const r = await run(["context", project, "--format", "json"]);
  if (!r.ok) {
    return null;
  }
  try {
    return JSON.parse(r.stdout) as ContextData;
  } catch {
    return null;
  }
}

export async function listProjectNames(): Promise<string[]> {
  const r = await run(["status", "--json"]);
  if (!r.ok) {
    return [];
  }
  try {
    const data = JSON.parse(r.stdout) as Array<{ name: string }>;
    return data.map((p) => p.name);
  } catch {
    return [];
  }
}

export async function isSomaAvailable(): Promise<boolean> {
  const r = await run(["--version"]);
  return r.ok;
}
