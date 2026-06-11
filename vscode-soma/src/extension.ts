/**
 * SOMA VS Code Extension — entry point.
 *
 * Registers the sidebar briefing panel and three commands:
 *   SOMA: Copy Context    — pick project → soma context → clipboard
 *   SOMA: Open Briefing   — focus sidebar
 *   SOMA: Refresh Briefing — force re-render
 */
import * as vscode from "vscode";
import { BriefingProvider } from "./BriefingProvider";
import { getContextText, listProjectNames, isSomaAvailable } from "./soma";

export function activate(context: vscode.ExtensionContext): void {
  const provider = new BriefingProvider(context.extensionUri);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(BriefingProvider.viewId, provider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // Command: SOMA: Copy Context
  context.subscriptions.push(
    vscode.commands.registerCommand("soma.copyContext", async () => {
      if (!(await isSomaAvailable())) {
        vscode.window.showErrorMessage("soma not found. Install with: pip install soma-cli");
        return;
      }
      const projects = await listProjectNames();
      if (projects.length === 0) {
        vscode.window.showWarningMessage("No soma projects registered. Run soma init first.");
        return;
      }
      const picked = await vscode.window.showQuickPick(projects, {
        placeHolder: "Select project to copy context for",
        title: "SOMA: Copy Context",
      });
      if (!picked) {
        return;
      }
      const text = await getContextText(picked);
      await vscode.env.clipboard.writeText(text);
      vscode.window.showInformationMessage(`SOMA: context for "${picked}" copied to clipboard.`);
    })
  );

  // Command: SOMA: Open Briefing — focus the sidebar
  context.subscriptions.push(
    vscode.commands.registerCommand("soma.openBriefing", () => {
      vscode.commands.executeCommand("soma.briefing.focus");
    })
  );

  // Command: SOMA: Refresh Briefing
  context.subscriptions.push(
    vscode.commands.registerCommand("soma.refreshBriefing", () => {
      provider.refresh();
    })
  );
}

export function deactivate(): void {
  // Nothing to clean up — subscriptions auto-disposed by VS Code
}
