import * as vscode from 'vscode';
import { execFile } from 'child_process';

export class BranchProvider implements vscode.TreeDataProvider<BranchTreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<BranchTreeItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(private workspaceRoot: string) {}

  refresh(): void {
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: BranchTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<BranchTreeItem[]> {
    try {
      const output = await this.runAgit(['branch', '--json']);
      const data = JSON.parse(output);
      const branches = data.branches || {};
      const current = data.current || 'main';

      return Object.entries(branches).map(
        ([name, hash]) =>
          new BranchTreeItem(name, hash as string, name === current),
      );
    } catch {
      return [new BranchTreeItem('main', '', true)];
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

class BranchTreeItem extends vscode.TreeItem {
  constructor(
    public readonly branchName: string,
    private hash: string,
    private isCurrent: boolean,
  ) {
    super(branchName, vscode.TreeItemCollapsibleState.None);
    this.description = this.hash ? this.hash.substring(0, 12) : '';
    this.tooltip = `${this.branchName}: ${this.hash}`;
    this.iconPath = new vscode.ThemeIcon(
      this.isCurrent ? 'circle-filled' : 'circle-outline',
    );
    if (this.isCurrent) {
      this.label = `${this.branchName} (HEAD)`;
    }

    this.contextValue = this.isCurrent ? 'currentBranch' : 'branch';
    this.command = {
      command: 'agit.checkout',
      title: 'Checkout',
      arguments: [this.branchName],
    };
  }
}
