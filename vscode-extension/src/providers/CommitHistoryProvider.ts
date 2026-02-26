import * as vscode from 'vscode';
import { execFile } from 'child_process';

interface CommitItem {
  hash: string;
  message: string;
  author: string;
  timestamp: string;
  action_type: string;
}

export class CommitHistoryProvider implements vscode.TreeDataProvider<CommitTreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<CommitTreeItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(private workspaceRoot: string) {}

  refresh(): void {
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: CommitTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<CommitTreeItem[]> {
    try {
      const output = await this.runAgit(['log', '--json', '-n', '50']);
      const commits: CommitItem[] = JSON.parse(output);
      return commits.map(
        (c) =>
          new CommitTreeItem(
            `${c.hash.substring(0, 8)} ${c.message}`,
            c.action_type,
            c.hash,
            c.timestamp,
          ),
      );
    } catch {
      return [new CommitTreeItem('No commits yet', '', '', '')];
    }
  }

  private runAgit(args: string[]): Promise<string> {
    return new Promise((resolve, reject) => {
      execFile('agit', args, { cwd: this.workspaceRoot }, (error, stdout, stderr) => {
        if (error) reject(new Error(stderr || error.message));
        else resolve(stdout.trim());
      });
    });
  }
}

class CommitTreeItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    private actionType: string,
    public readonly hash: string,
    private timestamp: string,
  ) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.tooltip = `${this.hash}\n${this.actionType}\n${this.timestamp}`;
    this.description = this.actionType;

    const iconMap: Record<string, string> = {
      tool_call: 'wrench',
      llm_response: 'comment',
      checkpoint: 'check',
      rollback: 'history',
      merge: 'git-merge',
      user_input: 'account',
    };
    this.iconPath = new vscode.ThemeIcon(iconMap[this.actionType] || 'circle-outline');
  }
}
