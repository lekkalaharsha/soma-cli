/**
 * WebviewViewProvider for the SOMA sidebar panel.
 *
 * Renders soma briefing output as styled HTML. Each project row has a
 * "Copy context" button that calls soma context <name> and writes to clipboard.
 */
import * as vscode from "vscode";
import { getBriefingText, getContextText, listProjectNames, isSomaAvailable } from "./soma";

export class BriefingProvider implements vscode.WebviewViewProvider {
  public static readonly viewId = "soma.briefing";
  private _view?: vscode.WebviewView;
  private _disposables: vscode.Disposable[] = [];

  constructor(private readonly _extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this._buildHtml(webviewView.webview);

    // Handle messages from webview
    webviewView.webview.onDidReceiveMessage(
      (message: { command: string; project?: string }) => {
        if (message.command === "copyContext" && message.project) {
          this._copyContext(message.project);
        } else if (message.command === "refresh") {
          this.refresh();
        }
      },
      undefined,
      this._disposables
    );

    // Auto-refresh on file save
    const saveListener = vscode.workspace.onDidSaveTextDocument(() => {
      this.refresh();
    });
    this._disposables.push(saveListener);
  }

  refresh(): void {
    if (!this._view) {
      return;
    }
    this._view.webview.html = this._buildHtml(this._view.webview);
  }

  dispose(): void {
    this._disposables.forEach((d) => d.dispose());
    this._disposables = [];
  }

  private _copyContext(project: string): void {
    const text = getContextText(project);
    vscode.env.clipboard.writeText(text).then(() => {
      vscode.window.showInformationMessage(
        `SOMA: context for "${project}" copied to clipboard.`
      );
    });
  }

  private _buildHtml(webview: vscode.Webview): string {
    const nonce = _nonce();

    if (!isSomaAvailable()) {
      return _page(nonce, `
        <div class="error">
          <p><strong>soma not found.</strong></p>
          <p>Install via: <code>pip install soma-cli</code></p>
          <p>Or set <code>soma.executablePath</code> in settings.</p>
        </div>
      `);
    }

    const briefing = getBriefingText();
    const projects = listProjectNames();

    const projectButtons = projects.length > 0
      ? projects
          .map(
            (name) =>
              `<button class="copy-btn" onclick="copyContext('${_esc(name)}')" title="Copy context for ${_esc(name)}">
                📋 ${_esc(name)}
              </button>`
          )
          .join("\n")
      : "<p class='dim'>No projects registered. Run <code>soma init</code>.</p>";

    const briefingHtml = briefing
      .split("\n")
      .map((line) => {
        const escaped = _esc(line);
        if (line.startsWith("Active") || line.startsWith("SOMA Briefing")) {
          return `<p class="section-header">${escaped}</p>`;
        }
        if (line.startsWith("Quiet") || line.startsWith("Dormant")) {
          return `<p class="section-quiet">${escaped}</p>`;
        }
        if (line.trim().startsWith("-") || line.trim().startsWith("↳")) {
          return `<p class="note-line">${escaped}</p>`;
        }
        return line.trim() ? `<p>${escaped}</p>` : "<br>";
      })
      .join("\n");

    return _page(nonce, `
      <div class="toolbar">
        <span class="title">SOMA</span>
        <button class="icon-btn" onclick="refresh()" title="Refresh">↺</button>
      </div>

      <section>
        <h3>Quick Copy</h3>
        <div class="project-grid">${projectButtons}</div>
      </section>

      <section>
        <h3>Briefing</h3>
        <div class="briefing">${briefingHtml}</div>
      </section>
    `);
  }
}

function _nonce(): string {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}

function _esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _page(nonce: string, body: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style nonce="${nonce}">
    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      padding: 8px;
      margin: 0;
    }
    h3 { font-size: 11px; text-transform: uppercase; opacity: 0.6; margin: 12px 0 4px; }
    .toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .title { font-weight: bold; font-size: 13px; }
    .icon-btn {
      background: none; border: none; cursor: pointer;
      color: var(--vscode-foreground); font-size: 14px; padding: 2px 6px;
      opacity: 0.7;
    }
    .icon-btn:hover { opacity: 1; }
    .project-grid { display: flex; flex-direction: column; gap: 3px; }
    .copy-btn {
      background: var(--vscode-button-secondaryBackground, #3a3d41);
      color: var(--vscode-button-secondaryForeground, #ccc);
      border: none; border-radius: 3px; padding: 5px 8px;
      cursor: pointer; text-align: left; font-size: 12px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .copy-btn:hover { background: var(--vscode-button-secondaryHoverBackground, #494d52); }
    .briefing { font-size: 11px; line-height: 1.5; }
    .briefing p { margin: 1px 0; }
    .section-header { color: var(--vscode-charts-green, #4ec9b0); font-weight: bold; margin-top: 6px !important; }
    .section-quiet { color: var(--vscode-charts-yellow, #dcdcaa); font-weight: bold; margin-top: 6px !important; }
    .note-line { opacity: 0.75; padding-left: 8px; }
    .dim { opacity: 0.5; font-size: 11px; }
    .error { background: var(--vscode-inputValidation-errorBackground); padding: 8px; border-radius: 4px; }
    code { font-family: var(--vscode-editor-font-family); font-size: 11px; }
  </style>
</head>
<body>
  ${body}
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    function copyContext(project) {
      vscode.postMessage({ command: 'copyContext', project });
    }
    function refresh() {
      vscode.postMessage({ command: 'refresh' });
    }
  </script>
</body>
</html>`;
}
