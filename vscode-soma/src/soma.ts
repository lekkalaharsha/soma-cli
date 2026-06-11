/**
 * Child-process wrapper for the soma CLI.
 * All commands run synchronously (spawnSync) — context generation is < 500ms.
 */
import { spawnSync } from "child_process";
import * as vscode from "vscode";

function somaPath(): string {
  return vscode.workspace
    .getConfiguration("soma")
    .get<string>("executablePath", "soma");
}

export interface Project {
  name: string;
  branch: string;
  lastActive: string;
  commits7d: number;
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

function run(args: string[]): { stdout: string; stderr: string; ok: boolean } {
  const result = spawnSync(somaPath(), args, {
    encoding: "utf8",
    timeout: 10_000,
    windowsHide: true,
  });
  return {
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
    ok: result.status === 0 && !result.error,
  };
}

export function getBriefingText(): string {
  const r = run(["briefing"]);
  if (!r.ok) {
    return r.stderr || "soma briefing failed — is soma installed?";
  }
  return r.stdout;
}

export function getContextJson(project: string): ContextData | null {
  const r = run(["context", project, "--format", "json"]);
  if (!r.ok) {
    return null;
  }
  try {
    return JSON.parse(r.stdout) as ContextData;
  } catch {
    return null;
  }
}

export function getContextText(project: string): string {
  const r = run(["context", project]);
  return r.ok ? r.stdout : `Error getting context for ${project}`;
}

export function listProjectNames(): string[] {
  const r = run(["status", "--json"]);
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

export function isSomaAvailable(): boolean {
  const r = run(["--version"]);
  return r.ok;
}
