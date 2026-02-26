import * as vscode from 'vscode';
import { CommitHistoryProvider } from './providers/CommitHistoryProvider';
import { BranchProvider } from './providers/BranchProvider';

let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
  console.log('AgentGit extension activated');

  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';

  // Tree data providers
  const commitProvider = new CommitHistoryProvider(workspaceRoot);
  const branchProvider = new BranchProvider(workspaceRoot);

  vscode.window.registerTreeDataProvider('agitCommitHistory', commitProvider);
  vscode.window.registerTreeDataProvider('agitBranches', branchProvider);

  // Status bar
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.command = 'agit.refresh';
  statusBarItem.text = '$(git-branch) agit';
  statusBarItem.tooltip = 'AgentGit';
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // Commands
  context.subscriptions.push(
    vscode.commands.registerCommand('agit.commit', async () => {
      const message = await vscode.window.showInputBox({
        prompt: 'Commit message',
        placeHolder: 'Describe the agent state change',
      });
      if (message) {
        const result = await runAgit(workspaceRoot, ['commit', '-m', message]);
        vscode.window.showInformationMessage(result || 'Committed');
        commitProvider.refresh();
      }
    }),

    vscode.commands.registerCommand('agit.branch', async () => {
      const name = await vscode.window.showInputBox({
        prompt: 'Branch name',
        placeHolder: 'e.g., retry-1',
      });
      if (name) {
        await runAgit(workspaceRoot, ['branch', name]);
        vscode.window.showInformationMessage(`Created branch: ${name}`);
        branchProvider.refresh();
      }
    }),

    vscode.commands.registerCommand('agit.checkout', async () => {
      const branches = await getBranches(workspaceRoot);
      const target = await vscode.window.showQuickPick(branches, {
        placeHolder: 'Select branch to checkout',
      });
      if (target) {
        await runAgit(workspaceRoot, ['checkout', target]);
        vscode.window.showInformationMessage(`Checked out: ${target}`);
        commitProvider.refresh();
        branchProvider.refresh();
        updateStatusBar(workspaceRoot);
      }
    }),

    vscode.commands.registerCommand('agit.revert', async () => {
      const hash = await vscode.window.showInputBox({
        prompt: 'Commit hash to revert to',
        placeHolder: 'e.g., abc123def456',
      });
      if (hash) {
        await runAgit(workspaceRoot, ['revert', hash]);
        vscode.window.showInformationMessage(`Reverted to: ${hash}`);
        commitProvider.refresh();
      }
    }),

    vscode.commands.registerCommand('agit.refresh', () => {
      commitProvider.refresh();
      branchProvider.refresh();
      updateStatusBar(workspaceRoot);
    }),
  );

  // Initial status bar update
  updateStatusBar(workspaceRoot);
}

export function deactivate() {
  statusBarItem?.dispose();
}

async function runAgit(cwd: string, args: string[]): Promise<string> {
  const { execFile } = require('child_process');
  return new Promise((resolve, reject) => {
    execFile('agit', args, { cwd }, (error: Error | null, stdout: string, stderr: string) => {
      if (error) {
        reject(new Error(stderr || error.message));
      } else {
        resolve(stdout.trim());
      }
    });
  });
}

async function getBranches(cwd: string): Promise<string[]> {
  try {
    const output = await runAgit(cwd, ['branch', '--json']);
    const data = JSON.parse(output);
    return Object.keys(data.branches || {});
  } catch {
    return ['main'];
  }
}

async function updateStatusBar(cwd: string) {
  try {
    const output = await runAgit(cwd, ['status', '--json']);
    const data = JSON.parse(output);
    statusBarItem.text = `$(git-branch) agit: ${data.branch || 'main'}`;
  } catch {
    statusBarItem.text = '$(git-branch) agit';
  }
}
